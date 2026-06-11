"""Unit tests for macuxd.eventbus — EventBus publish/subscribe."""

from __future__ import annotations

import pytest
from macuxd.eventbus import EventBus


class TestEventBusSubscribe:
    def test_exact_match(self):
        bus = EventBus()
        received = []
        bus.subscribe("macux.app.launched", lambda c, e, d: received.append((c, e, d)))
        bus.publish("macux.app", "launched", {"name": "Terminal"})
        assert len(received) == 1
        assert received[0] == ("macux.app", "launched", {"name": "Terminal"})

    def test_category_glob(self):
        bus = EventBus()
        received = []
        bus.subscribe("macux.app.*", lambda c, e, d: received.append(e))
        bus.publish("macux.app", "launched")
        bus.publish("macux.app", "closed")
        bus.publish("macux.system", "battery_low")  # should NOT match
        assert received == ["launched", "closed"]

    def test_wildcard_all(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda c, e, d: received.append(e))
        bus.publish("macux.app", "launched")
        bus.publish("macux.system", "battery_low")
        assert len(received) == 2

    def test_no_match(self):
        bus = EventBus()
        received = []
        bus.subscribe("macux.window.*", lambda c, e, d: received.append(e))
        bus.publish("macux.app", "launched")
        assert received == []

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        cb = lambda c, e, d: received.append(e)
        bus.subscribe("macux.app.launched", cb)
        bus.unsubscribe("macux.app.launched", cb)
        bus.publish("macux.app", "launched")
        assert received == []

    def test_callback_exception_does_not_stop_others(self):
        bus = EventBus()
        received = []

        def bad_cb(c, e, d):
            raise ValueError("bad callback")

        def good_cb(c, e, d):
            received.append(e)

        bus.subscribe("macux.app.launched", bad_cb)
        bus.subscribe("macux.app.launched", good_cb)
        bus.publish("macux.app", "launched")
        assert received == ["launched"]

    def test_default_empty_data(self):
        bus = EventBus()
        received = []
        bus.subscribe("macux.app.*", lambda c, e, d: received.append(d))
        bus.publish("macux.app", "launched")   # no data arg
        assert received == [{}]

    def test_duplicate_subscriber_called_once(self):
        bus = EventBus()
        received = []
        cb = lambda c, e, d: received.append(e)

        # Subscribe the same callback to both exact and glob — should only fire once
        bus.subscribe("macux.app.launched", cb)
        bus.subscribe("macux.app.*", cb)
        bus.publish("macux.app", "launched")

        # The same cb object appears in both patterns — EventBus deduplicates per publish
        assert len(received) == 1
