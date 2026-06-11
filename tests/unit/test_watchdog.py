"""Unit tests for macuxd.watchdog — ComponentWatchdog."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from macuxd.watchdog import ComponentConfig, ComponentState, ComponentWatchdog


@pytest.fixture
def echo_config():
    return ComponentConfig(
        name="test-echo",
        command=["bash", "-c", "sleep 60"],
        restart_on_crash=False,
        max_restarts=3,
        restart_delay=0.1,
    )


@pytest.fixture
def crash_config():
    return ComponentConfig(
        name="test-crash",
        command=["bash", "-c", "exit 1"],
        restart_on_crash=True,
        max_restarts=2,
        restart_delay=0.05,
        backoff_multiplier=1.0,
    )


class TestComponentWatchdogLifecycle:
    def test_register(self, echo_config):
        dog = ComponentWatchdog()
        dog.register(echo_config)
        status = dog.get_status("test-echo")
        assert status is not None
        assert status.state == ComponentState.STOPPED

    def test_start_running_process(self, echo_config):
        dog = ComponentWatchdog()
        dog.register(echo_config)
        result = dog.start("test-echo")
        assert result is True
        status = dog.get_status("test-echo")
        assert status.state == ComponentState.RUNNING
        assert status.pid is not None
        dog.stop("test-echo")

    def test_stop_running_process(self, echo_config):
        dog = ComponentWatchdog()
        dog.register(echo_config)
        dog.start("test-echo")
        dog.stop("test-echo")
        status = dog.get_status("test-echo")
        assert status.state == ComponentState.STOPPED
        assert status.pid is None

    def test_start_unknown_component(self, echo_config):
        dog = ComponentWatchdog()
        result = dog.start("nonexistent")
        assert result is False

    def test_start_already_running(self, echo_config):
        dog = ComponentWatchdog()
        dog.register(echo_config)
        dog.start("test-echo")
        result = dog.start("test-echo")  # second call
        assert result is True            # should be idempotent
        dog.stop("test-echo")

    def test_invalid_command_returns_false(self):
        cfg = ComponentConfig(
            name="bad",
            command=["this_command_does_not_exist_xyz"],
        )
        dog = ComponentWatchdog()
        dog.register(cfg)
        result = dog.start("bad")
        assert result is False
        assert dog.get_status("bad").state == ComponentState.CRASHED

    def test_state_change_callback(self, echo_config):
        changes: list[tuple] = []
        dog = ComponentWatchdog(state_change_callback=lambda n, s: changes.append((n, s)))
        dog.register(echo_config)
        dog.start("test-echo")
        dog.stop("test-echo")
        states = [s for _, s in changes]
        assert ComponentState.STARTING in states
        assert ComponentState.RUNNING in states
        assert ComponentState.STOPPED in states

    def test_restart(self, echo_config):
        dog = ComponentWatchdog()
        dog.register(echo_config)
        dog.start("test-echo")
        old_pid = dog.get_status("test-echo").pid
        dog.restart("test-echo")
        new_pid = dog.get_status("test-echo").pid
        assert new_pid is not None
        assert new_pid != old_pid
        dog.stop("test-echo")
