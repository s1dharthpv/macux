"""MacUX event bus — publish/subscribe over DBus signals."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for subscriber callbacks
Subscriber = Callable[[str, str, dict[str, Any]], None]


class EventBus:
    """
    In-process publish/subscribe bus.

    Events have the form:  category.event_name
    e.g.:  macux.app.launched  |  macux.system.battery_low

    Subscribers can match:
      - Exact event:    'macux.app.launched'
      - Category glob:  'macux.app.*'
      - All events:     '*'
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = {}

    def subscribe(self, pattern: str, callback: Subscriber) -> None:
        """Register a callback for events matching the given pattern."""
        self._subscribers.setdefault(pattern, []).append(callback)
        logger.debug("EventBus: subscribed to %r", pattern)

    def unsubscribe(self, pattern: str, callback: Subscriber) -> None:
        subs = self._subscribers.get(pattern, [])
        try:
            subs.remove(callback)
        except ValueError:
            pass

    def publish(self, category: str, event: str, data: dict[str, Any] | None = None) -> None:
        """
        Publish an event.

        Args:
            category: e.g. 'macux.app'
            event:    e.g. 'launched'
            data:     optional payload dict
        """
        if data is None:
            data = {}
        full_event = f"{category}.{event}"
        logger.debug("EventBus: publish %s data=%r", full_event, data)

        matched: set[Subscriber] = set()

        for pattern, callbacks in self._subscribers.items():
            if self._matches(pattern, full_event, category):
                for cb in callbacks:
                    if cb not in matched:
                        matched.add(cb)
                        try:
                            cb(category, event, data)
                        except Exception:
                            logger.exception(
                                "EventBus subscriber raised for event %s", full_event
                            )

    @staticmethod
    def _matches(pattern: str, full_event: str, category: str) -> bool:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return full_event.startswith(pattern[:-2])
        return pattern == full_event
