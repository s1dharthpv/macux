"""MacUX component watchdog — monitors child processes and restarts them on failure."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from threading import Lock, Thread
from typing import Callable

logger = logging.getLogger(__name__)


class ComponentState(Enum):
    STOPPED = auto()
    STARTING = auto()
    RUNNING = auto()
    CRASHED = auto()
    RESTARTING = auto()
    DISABLED = auto()


@dataclass
class ComponentConfig:
    name: str
    command: list[str]
    restart_on_crash: bool = True
    max_restarts: int = 5
    restart_delay: float = 2.0       # seconds between restarts
    backoff_multiplier: float = 1.5  # exponential backoff
    max_restart_delay: float = 30.0
    startup_timeout: float = 10.0    # seconds to wait for DBus name acquisition


@dataclass
class ComponentStatus:
    config: ComponentConfig
    state: ComponentState = ComponentState.STOPPED
    pid: int | None = None
    restarts: int = 0
    last_crash_at: float = 0.0
    current_restart_delay: float = 0.0
    _process: subprocess.Popen | None = field(default=None, repr=False, compare=False)


class ComponentWatchdog:
    """
    Starts, monitors, and restarts MacUX component processes.

    Each component runs as a separate OS process. The watchdog polls
    process health and restarts crashed components with exponential backoff.
    """

    def __init__(
        self,
        state_change_callback: Callable[[str, ComponentState], None] | None = None,
    ) -> None:
        self._components: dict[str, ComponentStatus] = {}
        self._lock = Lock()
        self._running = False
        self._poll_thread: Thread | None = None
        self._state_change_cb = state_change_callback

    def register(self, config: ComponentConfig) -> None:
        with self._lock:
            self._components[config.name] = ComponentStatus(config=config)
        logger.info("Registered component: %s", config.name)

    def start_all(self) -> None:
        self._running = True
        for name in list(self._components):
            self.start(name)
        self._poll_thread = Thread(target=self._poll_loop, daemon=True, name="macux-watchdog")
        self._poll_thread.start()

    def stop_all(self) -> None:
        self._running = False
        for name in list(self._components):
            self.stop(name)
        if self._poll_thread:
            self._poll_thread.join(timeout=10)

    def start(self, name: str) -> bool:
        with self._lock:
            status = self._components.get(name)
            if not status:
                logger.warning("Unknown component: %s", name)
                return False
            if status.state == ComponentState.RUNNING:
                logger.debug("Component %s already running", name)
                return True
            return self._launch(status)

    def stop(self, name: str) -> None:
        with self._lock:
            status = self._components.get(name)
            if not status or not status._process:
                return
            logger.info("Stopping component: %s (pid=%s)", name, status.pid)
            try:
                status._process.terminate()
                try:
                    status._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    status._process.kill()
                    status._process.wait(timeout=2)
            except OSError:
                pass
            status.state = ComponentState.STOPPED
            status.pid = None
            status._process = None
            self._notify(name, ComponentState.STOPPED)

    def restart(self, name: str) -> bool:
        self.stop(name)
        time.sleep(0.5)
        return self.start(name)

    def get_status(self, name: str) -> ComponentStatus | None:
        return self._components.get(name)

    def get_all_statuses(self) -> dict[str, ComponentStatus]:
        return dict(self._components)

    def _launch(self, status: ComponentStatus) -> bool:
        try:
            status.state = ComponentState.STARTING
            self._notify(status.config.name, ComponentState.STARTING)
            proc = subprocess.Popen(
                status.config.command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            status._process = proc
            status.pid = proc.pid
            status.state = ComponentState.RUNNING
            self._notify(status.config.name, ComponentState.RUNNING)
            logger.info("Started component %s (pid=%d)", status.config.name, proc.pid)
            return True
        except (OSError, ValueError) as exc:
            logger.error("Failed to start component %s: %s", status.config.name, exc)
            status.state = ComponentState.CRASHED
            self._notify(status.config.name, ComponentState.CRASHED)
            return False

    def _poll_loop(self) -> None:
        while self._running:
            time.sleep(2)
            with self._lock:
                for name, status in self._components.items():
                    if status.state != ComponentState.RUNNING or not status._process:
                        continue
                    ret = status._process.poll()
                    if ret is not None:
                        logger.warning(
                            "Component %s exited unexpectedly (rc=%d)", name, ret
                        )
                        status.state = ComponentState.CRASHED
                        status.pid = None
                        status.last_crash_at = time.monotonic()
                        self._notify(name, ComponentState.CRASHED)
                        if (
                            status.config.restart_on_crash
                            and status.restarts < status.config.max_restarts
                        ):
                            delay = status.config.restart_delay * (
                                status.config.backoff_multiplier ** status.restarts
                            )
                            delay = min(delay, status.config.max_restart_delay)
                            status.current_restart_delay = delay
                            status.restarts += 1
                            status.state = ComponentState.RESTARTING
                            logger.info(
                                "Scheduling restart of %s in %.1fs (attempt %d/%d)",
                                name, delay, status.restarts, status.config.max_restarts,
                            )
                            t = Thread(
                                target=self._delayed_restart,
                                args=(name, delay),
                                daemon=True,
                            )
                            t.start()
                        else:
                            logger.error(
                                "Component %s exceeded max restarts (%d), disabling.",
                                name, status.config.max_restarts,
                            )
                            status.state = ComponentState.DISABLED
                            self._notify(name, ComponentState.DISABLED)

    def _delayed_restart(self, name: str, delay: float) -> None:
        time.sleep(delay)
        with self._lock:
            status = self._components.get(name)
            if not status or status.state != ComponentState.RESTARTING:
                return
            self._launch(status)

    def _notify(self, name: str, state: ComponentState) -> None:
        if self._state_change_cb:
            try:
                self._state_change_cb(name, state)
            except Exception:
                logger.exception("State change callback raised for %s", name)
