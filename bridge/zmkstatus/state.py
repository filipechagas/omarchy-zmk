"""Fold Bluetooth observations into the snapshot the shell renders.

The D-Bus glue in zmk_bridge.py only translates BlueZ events into calls on
KeyboardState; everything that decides what the user sees lives here.
"""

from . import alerts, history, protocol

SOURCE_STATUS = "status"
SOURCE_BAS = "bas"
SOURCE_BATTERY1 = "battery1"


class KeyboardState:
    def __init__(self, battery_alerts=None, disconnect_watch=None):
        self.bluez = True
        self.adapter = {"present": False, "powered": False}
        self.device = None
        self.custom_service = False
        self.status = None
        self.status_error = None
        self.firmware = None
        self.bas = {"left": None, "right": None}
        self.right_bas_present = False
        self.battery1 = None
        self.histories = {"left": history.BatteryHistory(), "right": history.BatteryHistory()}
        self.battery_alerts = battery_alerts or alerts.BatteryAlerts()
        self.disconnect_watch = disconnect_watch or alerts.RightDisconnectWatch()
        self._identity = None
        self._right_disconnected_wall = None

    # -- observations -----------------------------------------------------

    def clear_readings(self):
        self.custom_service = False
        self.status = None
        self.status_error = None
        self.firmware = None
        self.bas = {"left": None, "right": None}
        self.right_bas_present = False
        self.battery1 = None

    def set_device(self, selection, custom_service=False):
        """selection is discovery.select_keyboard() output or None."""
        identity = selection["path"] if selection else None
        if identity != self._identity:
            self.histories = {"left": history.BatteryHistory(), "right": history.BatteryHistory()}
            self._identity = identity
            self.clear_readings()
        if not selection or not selection.get("connected"):
            self.clear_readings()
        if selection is None:
            self.device = None
            return
        self.device = {
            "name": selection.get("name") or "Keyboard",
            "connected": bool(selection.get("connected")),
            "source": selection.get("source"),
            "candidates": int(selection.get("candidates") or 1),
        }
        self.custom_service = bool(custom_service) and self.device["connected"]

    def set_status_bytes(self, data):
        try:
            self.status = protocol.decode_status(data)
            self.status_error = None
        except protocol.StatusError as error:
            self.status = None
            self.status_error = error.code

    def set_firmware_bytes(self, data):
        self.firmware = protocol.decode_firmware(data)

    def set_bas(self, half, data):
        level = protocol.decode_battery_level(data)
        if half == "right" and level == 0:
            # ZMK's central zeroes a peripheral's level when it disconnects
            # (zmk/app/src/split/bluetooth/central.c) and the BAS proxy
            # reports that 0, so it means "no reading", not "empty".
            level = None
        self.bas[half] = level

    def set_right_bas_present(self, present):
        self.right_bas_present = bool(present)

    def set_battery1(self, percent):
        self.battery1 = protocol.battery_percent(percent)

    # -- derived values ---------------------------------------------------

    @property
    def connected(self):
        return bool(self.device and self.device["connected"])

    def halves(self):
        status = self.status
        left, left_source = None, None
        if status and status["leftBattery"] is not None:
            left, left_source = status["leftBattery"], SOURCE_STATUS
        elif self.bas["left"] is not None:
            left, left_source = self.bas["left"], SOURCE_BAS
        elif self.battery1 is not None:
            left, left_source = self.battery1, SOURCE_BATTERY1

        right, right_source = None, None
        right_connected = status["rightConnected"] if status else None
        if status and status["rightBattery"] is not None:
            right, right_source = status["rightBattery"], SOURCE_STATUS
        elif self.bas["right"] is not None:
            right, right_source = self.bas["right"], SOURCE_BAS
        return {
            "left": left,
            "leftSource": left_source,
            "right": right,
            "rightSource": right_source,
            "rightConnected": right_connected,
        }

    def observe(self, wall, monotonic):
        """Record history and return alerts raised by the current readings."""
        raised = []
        if not self.connected:
            self.disconnect_watch.update(monotonic, False, None)
            self._right_disconnected_wall = None
            return raised
        values = self.halves()
        name = self.device["name"]
        for half in ("left", "right"):
            percent = values[half]
            if half == "right" and values["rightConnected"] is False:
                percent = None  # a stale value from a disconnected half is not a reading
            self.histories[half].add(wall, percent)
            alert = self.battery_alerts.update(half, percent)
            if alert:
                alert["device"] = name
                raised.append(alert)
        alert = self.disconnect_watch.update(monotonic, True, values["rightConnected"])
        if values["rightConnected"] is False:
            if self._right_disconnected_wall is None:
                self._right_disconnected_wall = wall
        else:
            self._right_disconnected_wall = None
        if alert:
            alert["device"] = name
            raised.append(alert)
        return raised

    def snapshot(self, wall):
        values = self.halves()
        connected = self.connected
        status = self.status if connected else None
        return {
            "v": 1,
            "type": "state",
            "bluez": self.bluez,
            "adapter": dict(self.adapter),
            "device": dict(self.device) if self.device else None,
            "features": {
                "customService": self.custom_service,
                "status": status is not None,
                "firmware": self.firmware is not None,
                "rightBas": self.right_bas_present,
            },
            "status": status,
            "statusError": self.status_error if connected else None,
            "firmware": self.firmware if connected else None,
            "left": {
                "percent": values["left"] if connected else None,
                "source": values["leftSource"] if connected else None,
                "trend": self.histories["left"].trend(wall),
            },
            "right": {
                "percent": values["right"] if connected else None,
                "source": values["rightSource"] if connected else None,
                "connected": values["rightConnected"] if connected else None,
                "disconnectedSince": self._right_disconnected_wall if connected else None,
                "trend": self.histories["right"].trend(wall),
            },
        }
