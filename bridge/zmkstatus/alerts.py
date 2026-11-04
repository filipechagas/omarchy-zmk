"""Decide when to raise desktop notifications.

Pure state machines; the bridge feeds them observations and forwards any
returned alert to the shell, which runs notify-send.
"""

THRESHOLDS = (20, 10, 5)
REARM_MARGIN = 3
RIGHT_DISCONNECT_DELAY = 60.0


class BatteryAlerts:
    """One alert per threshold crossing per half.

    A threshold fires when a half reports a percentage at or below it while
    the threshold is armed. It re-arms only after the half climbs back to
    threshold + REARM_MARGIN, so a reading that wobbles between 20 and 21
    does not notify twice. When one reading crosses several thresholds at
    once (or the first reading is already low) a single alert is raised for
    the lowest threshold crossed.
    """

    def __init__(self, thresholds=THRESHOLDS, rearm_margin=REARM_MARGIN):
        self.thresholds = tuple(sorted(thresholds, reverse=True))
        self.rearm_margin = rearm_margin
        self._armed = {}

    def _armed_for(self, half):
        if half not in self._armed:
            self._armed[half] = {threshold: True for threshold in self.thresholds}
        return self._armed[half]

    def update(self, half, percent):
        if percent is None:
            return None
        armed = self._armed_for(half)
        for threshold in self.thresholds:
            if percent >= threshold + self.rearm_margin:
                armed[threshold] = True
        crossed = [t for t in self.thresholds if percent <= t and armed[t]]
        if not crossed:
            return None
        for threshold in crossed:
            armed[threshold] = False
        return {
            "kind": "battery_low",
            "half": half,
            "threshold": min(crossed),
            "percent": percent,
        }


class RightDisconnectWatch:
    """Alert once when the right half stays disconnected too long.

    Only meaningful while the keyboard (left/central half) is connected and
    the firmware reports the right-half link state. The watch resets when
    the right half reconnects, the keyboard disconnects, or the state
    becomes unknown.
    """

    def __init__(self, delay=RIGHT_DISCONNECT_DELAY):
        self.delay = delay
        self._since = None
        self._fired = False

    def update(self, now, keyboard_connected, right_connected):
        if keyboard_connected and right_connected is False:
            if self._since is None:
                self._since = now
            if not self._fired and now - self._since >= self.delay:
                self._fired = True
                return {
                    "kind": "right_disconnected",
                    "half": "right",
                    "seconds": int(now - self._since),
                }
            return None
        self._since = None
        self._fired = False
        return None

    @property
    def disconnected_since(self):
        return self._since
