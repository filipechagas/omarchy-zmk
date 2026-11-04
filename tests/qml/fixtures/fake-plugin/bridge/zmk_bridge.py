#!/usr/bin/env python3
"""Fake bridge for tests/qml/tst_Service.qml: scripted JSONL, logs argv and stdin."""
import json
import os
import signal
import sys

log_path = os.environ.get("ZMK_TEST_LOG")


def log(entry):
    if log_path:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def emit(message):
    message["v"] = 1
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def on_signal(signum, _frame):
    log({"signal": signum})
    sys.exit(0)


signal.signal(signal.SIGTERM, on_signal)
log({"argv": sys.argv[1:]})
emit({"type": "hello", "bridge": "fake"})
sys.stdout.write("not json\n")
emit({"type": "keymap", "configured": True, "ok": True, "geometry": {"width": 1, "height": 1, "keys": []},
      "layers": [{"index": 0, "name": "default", "keys": []}, {"index": 1, "name": "nav", "keys": []}]})
emit({"type": "state", "bluez": True, "adapter": {"present": True, "powered": True},
      "device": {"name": "Corne", "connected": True, "source": "custom-service", "candidates": 1},
      "features": {"customService": True, "status": True, "firmware": True, "rightBas": True},
      "status": {"version": 1, "layer": 1, "layerMask": 3, "activeLayers": [0, 1], "profile": 0,
                 "rightConnected": True, "capsWordSupported": False, "capsWord": None,
                 "leftBattery": 93, "rightBattery": 71},
      "statusError": None, "firmware": "abc1234",
      "left": {"percent": 93, "source": "status", "trend": None},
      "right": {"percent": 71, "source": "status", "connected": True, "disconnectedSince": None, "trend": None}})
emit({"type": "alert", "kind": "battery_low", "half": "right", "threshold": 20, "percent": 19, "device": "Corne"})
for line in sys.stdin:
    log({"stdin": line.strip()})
log({"eof": True})
