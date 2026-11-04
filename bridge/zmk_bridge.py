#!/usr/bin/env python3
"""ZMK Keyboard bridge for the Omarchy shell.

Long-running child of Service.qml. Watches BlueZ over the system D-Bus,
subscribes to the keyboard's GATT notifications, and writes one JSON object
per line to stdout:

  hello   once at start
  state   full snapshot whenever something visible changes
  keymap  the parsed keymap-drawer YAML (at start and when the file changes)
  alert   a desktop notification the shell should raise
  fatal   unrecoverable startup problem (missing dependency), then exit

Diagnostics go to stderr. With --stdio the bridge reads JSON commands from
stdin ({"type": "refresh"} / {"type": "shutdown"}) and exits on EOF, so it
never outlives the shell.
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zmkstatus import discovery, glyphs, keymap, protocol, state  # noqa: E402

BRIDGE_VERSION = "0.1.0"
PROTOCOL_VERSION = 1

BLUEZ = "org.bluez"
PROPS = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"
UPOWER = "org.freedesktop.UPower"
UPOWER_DEVICE = "org.freedesktop.UPower.Device"

RESCAN_DEBOUNCE_MS = 400
TICK_SECONDS = 5
CALL_TIMEOUT = 10
UPOWER_HISTORY_SECONDS = 24 * 3600


def log(message):
    try:
        sys.stderr.write("zmk-bridge: %s\n" % message)
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


class Output:
    def __init__(self, stream, on_closed):
        self.stream = stream
        self.on_closed = on_closed

    def emit(self, message):
        try:
            self.stream.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.stream.flush()
        except (BrokenPipeError, OSError, ValueError):
            self.on_closed()


def find_glyph_table():
    """Read the MDI name table from an installed Nerd Font, if any."""
    try:
        listing = subprocess.run(
            ["fc-list", "--format", "%{file}\n", ":charset=f030c"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}, None
    files = [line for line in listing.splitlines() if line.lower().endswith((".ttf", ".ttc"))]
    files.sort(key=lambda path: (
        "symbolsnerdfont" not in os.path.basename(path).lower().replace(" ", ""),
        "regular" not in path.lower(),
        path,
    ))
    for path in files[:6]:
        try:
            with open(path, "rb") as handle:
                table = glyphs.mdi_table_from_font(handle.read())
        except (OSError, ValueError, IndexError) as error:
            log("glyph table: %s: %s" % (path, error))
            continue
        if table:
            return table, os.path.basename(path)
    return {}, None


class KeymapWatcher:
    def __init__(self, path):
        self.path = os.path.expanduser(path) if path else ""
        self.signature = None
        self.table = None
        self.font = None

    def _signature(self):
        try:
            info = os.stat(self.path)
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def load(self):
        message = {"v": PROTOCOL_VERSION, "type": "keymap", "configured": bool(self.path), "ok": False}
        if not self.path:
            return message
        self.signature = self._signature()
        if self.table is None:
            self.table, self.font = find_glyph_table()
        message["glyphFont"] = self.font
        try:
            message.update(keymap.load_keymap(self.path, self.table))
            message["ok"] = True
        except keymap.KeymapError as error:
            message["error"] = error.code
            message["detail"] = error.detail
        return message

    def changed(self):
        return bool(self.path) and self._signature() != self.signature


class Bridge:
    def __init__(self, dbus, bus, loop, output, device_name):
        self.dbus = dbus
        self.bus = bus
        self.loop = loop
        self.output = output
        self.device_name = device_name or ""
        self.state = state.KeyboardState()
        self.device_path = None
        self.layout = None
        self.roles = {}
        self.notifying = set()
        self.pending_notify = set()
        self.descriptors = {}
        self.firmware_requested = False
        self.upower_seeded = set()
        self.rescan_source = None
        self.last_state = None

    # -- D-Bus helpers ----------------------------------------------------

    def proxy(self, path, bus_name=BLUEZ):
        return self.bus.get_object(bus_name, path, introspect=False)

    def read_value(self, path, interface, on_value):
        def failed(error):
            log("ReadValue %s failed: %s" % (path.rsplit("/", 2)[-2:], error.get_dbus_name()))
            on_value(None)

        self.proxy(path).ReadValue(
            self.dbus.Dictionary({}, signature="sv"),
            dbus_interface=interface,
            reply_handler=lambda value: on_value(value),
            error_handler=failed,
            timeout=CALL_TIMEOUT,
        )

    def subscribed(self, path):
        return path in self.notifying or path in self.pending_notify

    def start_notify(self, path):
        if path in self.notifying or path in self.pending_notify:
            return
        self.pending_notify.add(path)

        def done():
            self.pending_notify.discard(path)
            self.notifying.add(path)

        def failed(error):
            self.pending_notify.discard(path)
            name = error.get_dbus_name()
            if name == "org.bluez.Error.InProgress":
                self.notifying.add(path)
                return
            log("StartNotify %s failed: %s" % (path.rsplit("/", 2)[-2:], name))

        # The notify session belongs to this D-Bus connection and stays alive
        # until the process exits or the device disconnects.
        self.proxy(path).StartNotify(
            dbus_interface=discovery.GATT_CHAR,
            reply_handler=done,
            error_handler=failed,
            timeout=CALL_TIMEOUT,
        )

    # -- lifecycle --------------------------------------------------------

    def start(self):
        self.bus.add_signal_receiver(
            self.on_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface=PROPS,
            bus_name=BLUEZ,
            path_keyword="path",
        )
        for signal_name in ("InterfacesAdded", "InterfacesRemoved"):
            self.bus.add_signal_receiver(
                self.on_interfaces_changed,
                signal_name=signal_name,
                dbus_interface=OBJECT_MANAGER,
                bus_name=BLUEZ,
            )
        self.bus.add_signal_receiver(
            self.on_name_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            arg0=BLUEZ,
        )
        self.rescan()

    def forget_device(self):
        self.layout = None
        self.roles = {}
        self.notifying = set()
        self.pending_notify = set()
        self.descriptors = {}
        self.firmware_requested = False

    def schedule_rescan(self, *_args, **_kwargs):
        from gi.repository import GLib

        if self.rescan_source is not None:
            GLib.source_remove(self.rescan_source)

        def fire():
            self.rescan_source = None
            self.rescan()
            return False

        self.rescan_source = GLib.timeout_add(RESCAN_DEBOUNCE_MS, fire)

    def rescan(self):
        try:
            objects = self.proxy("/").GetManagedObjects(dbus_interface=OBJECT_MANAGER, timeout=CALL_TIMEOUT)
        except self.dbus.DBusException as error:
            log("BlueZ unavailable: %s" % error.get_dbus_name())
            self.state.bluez = False
            self.state.adapter = {"present": False, "powered": False}
            self.state.set_device(None)
            self.device_path = None
            self.forget_device()
            self.publish()
            return
        self.state.bluez = True
        self.state.adapter = discovery.adapter_state(objects)
        selection = discovery.select_keyboard(objects, self.device_name)
        path = selection["path"] if selection else None
        if path != self.device_path:
            self.forget_device()
            self.device_path = path
        if selection and selection["connected"]:
            layout = discovery.gatt_layout(objects, path)
            self.state.set_device(selection, custom_service=layout["status"] is not None)
            self.state.set_battery1(discovery.battery1_percent(objects, path))
            if selection["servicesResolved"]:
                self.apply_layout(layout)
            self.seed_upower(path)
        else:
            self.forget_device()
            self.state.set_device(selection)
        self.publish()

    def apply_layout(self, layout):
        if layout != self.layout:
            known = {layout["status"], layout["firmware"]} | {entry["char"] for entry in layout["bas"]}
            self.notifying &= known
            self.roles = {path: role for path, role in self.roles.items() if path in known}
            self.layout = layout
        if layout["status"]:
            self.roles[layout["status"]] = "status"
            if not self.subscribed(layout["status"]):
                self.start_notify(layout["status"])
                self.read_value(layout["status"], discovery.GATT_CHAR, lambda v: self.on_value("status", v))
        if layout["firmware"]:
            self.roles[layout["firmware"]] = "firmware"
            if not self.firmware_requested:
                self.firmware_requested = True
                self.read_value(layout["firmware"], discovery.GATT_CHAR, lambda v: self.on_value("firmware", v))
        self.classify_bas()

    def classify_bas(self):
        entries = self.layout["bas"] if self.layout else []
        waiting = False
        for entry in entries:
            for kind, interface in (("cud", discovery.GATT_DESC), ("cpf", discovery.GATT_DESC)):
                desc = entry[kind]
                if desc and desc not in self.descriptors:
                    self.descriptors[desc] = "pending"
                    self.read_value(desc, interface, lambda v, d=desc, k=kind: self.on_descriptor(d, k, v))
                if desc and self.descriptors.get(desc) == "pending":
                    waiting = True
        if waiting:
            return
        described = []
        for entry in entries:
            cud = self.descriptors.get(entry["cud"]) if entry["cud"] else None
            cpf = self.descriptors.get(entry["cpf"]) if entry["cpf"] else None
            described.append({
                "char": entry["char"],
                "cud": protocol.decode_cud(cud) if cud not in (None, "pending", "failed") else None,
                "cpf": protocol.decode_cpf_description(cpf) if cpf not in (None, "pending", "failed") else None,
            })
        halves = discovery.classify_bas(described)
        self.state.set_right_bas_present(halves["right"] is not None)
        for half in ("left", "right"):
            path = halves[half]
            if not path:
                continue
            role = "bas_" + half
            self.roles[path] = role
            if not self.subscribed(path):
                self.start_notify(path)
                self.read_value(path, discovery.GATT_CHAR, lambda v, r=role: self.on_value(r, v))

    def on_descriptor(self, path, _kind, value):
        self.descriptors[path] = value if value is not None else "failed"
        if self.layout:
            self.classify_bas()
            self.publish()

    def on_value(self, role, value):
        if value is None:
            return
        if role == "status":
            self.state.set_status_bytes(value)
        elif role == "firmware":
            self.state.set_firmware_bytes(value)
        elif role in ("bas_left", "bas_right"):
            self.state.set_bas(role[4:], value)
        self.publish()

    def seed_upower(self, device_path):
        if device_path in self.upower_seeded:
            return
        self.upower_seeded.add(device_path)
        try:
            manager = self.proxy("/org/freedesktop/UPower", UPOWER)
            for upath in manager.EnumerateDevices(dbus_interface=UPOWER, timeout=3):
                device = self.proxy(upath, UPOWER)
                native = device.Get(UPOWER_DEVICE, "NativePath", dbus_interface=PROPS, timeout=3)
                if str(native) != device_path:
                    continue
                rows = device.GetHistory(
                    "charge", self.dbus.UInt32(UPOWER_HISTORY_SECONDS), self.dbus.UInt32(200),
                    dbus_interface=UPOWER_DEVICE, timeout=3,
                )
                count = self.state.histories["left"].seed(
                    [(int(t), float(v)) for t, v, _ in rows], "upower"
                )
                log("UPower history: %d rows, %d usable" % (len(rows), count))
                return
        except self.dbus.DBusException as error:
            log("UPower history unavailable: %s" % error.get_dbus_name())

    # -- signals ----------------------------------------------------------

    def on_properties_changed(self, interface, changed, _invalidated, path=None):
        path = str(path or "")
        if interface == discovery.GATT_CHAR and "Value" in changed and path in self.roles:
            self.on_value(self.roles[path], changed["Value"])
        elif interface == discovery.DEVICE:
            if path == self.device_path and changed.get("Connected") is not None and not changed["Connected"]:
                self.forget_device()
            if any(key in changed for key in ("Connected", "ServicesResolved", "Alias", "Name", "Paired")):
                self.schedule_rescan()
        elif interface == discovery.BATTERY and path == self.device_path and "Percentage" in changed:
            self.state.set_battery1(changed["Percentage"])
            self.publish()
        elif interface == discovery.ADAPTER and "Powered" in changed:
            self.schedule_rescan()

    def on_interfaces_changed(self, path, *_args):
        self.schedule_rescan()

    def on_name_owner_changed(self, _name, _old, _new):
        self.forget_device()
        self.schedule_rescan()

    # -- output -----------------------------------------------------------

    def publish(self):
        for alert in self.state.observe(time.time(), time.monotonic()):
            alert.update({"v": PROTOCOL_VERSION, "type": "alert"})
            self.output.emit(alert)
        snapshot = self.state.snapshot(time.time())
        if snapshot != self.last_state:
            self.last_state = snapshot
            self.output.emit(snapshot)

    def refresh(self):
        self.forget_device()
        self.rescan()


def install_stdin(GLib, bridge, loop):
    buffer = bytearray()

    def readable(_fd, condition):
        try:
            chunk = os.read(0, 4096)
        except OSError:
            chunk = b""
        if not chunk:
            loop.quit()
            return False
        buffer.extend(chunk)
        while b"\n" in buffer:
            line, _, rest = bytes(buffer).partition(b"\n")
            buffer[:] = rest
            try:
                command = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            kind = command.get("type") if isinstance(command, dict) else None
            if kind == "refresh":
                bridge.refresh()
            elif kind == "shutdown":
                loop.quit()
                return False
        if len(buffer) > 65536:
            buffer.clear()
        return True

    try:
        from gi.repository import GLibUnix

        add_fd = GLibUnix.fd_add_full
    except ImportError:
        add_fd = GLib.unix_fd_add_full
    add_fd(GLib.PRIORITY_DEFAULT, 0, GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR, readable)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device-name", default="", help="Fallback device name (Alias or Name).")
    parser.add_argument("--keymap", default="", help="keymap-drawer YAML file.")
    parser.add_argument("--stdio", action="store_true", help="Read commands from stdin; exit on EOF.")
    parser.add_argument("--keymap-only", action="store_true", help="Print the keymap message and exit.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    output = Output(sys.stdout, lambda: os._exit(0))
    output.emit({"v": PROTOCOL_VERSION, "type": "hello", "bridge": BRIDGE_VERSION})

    watcher = KeymapWatcher(args.keymap)
    output.emit(watcher.load())
    if args.keymap_only:
        return 0

    try:
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError as error:
        output.emit({"v": PROTOCOL_VERSION, "type": "fatal", "code": "missing_dependency", "detail": str(error)})
        return 3

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    try:
        bus = dbus.SystemBus()
    except dbus.DBusException as error:
        output.emit({"v": PROTOCOL_VERSION, "type": "fatal", "code": "no_system_bus", "detail": error.get_dbus_name() or ""})
        return 4

    bridge = Bridge(dbus, bus, loop, output, args.device_name)

    def tick():
        bridge.publish()
        if watcher.changed():
            output.emit(watcher.load())
        return True

    GLib.timeout_add_seconds(TICK_SECONDS, tick)
    try:
        from gi.repository import GLibUnix

        add_signal = GLibUnix.signal_add
    except ImportError:
        add_signal = GLib.unix_signal_add
    for signum in (2, 15):
        add_signal(GLib.PRIORITY_HIGH, signum, lambda: (loop.quit(), False)[1])
    if args.stdio:
        install_stdin(GLib, bridge, loop)

    bridge.start()
    loop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
