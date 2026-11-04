"""Find the ZMK keyboard and its GATT attributes in a BlueZ object tree.

Input is the dict returned by org.freedesktop.DBus.ObjectManager
GetManagedObjects: {object_path: {interface: {property: value}}}. Values may
be dbus-python types or plain Python types; both behave the same here.
"""

from . import protocol

ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
BATTERY = "org.bluez.Battery1"
GATT_SERVICE = "org.bluez.GattService1"
GATT_CHAR = "org.bluez.GattCharacteristic1"
GATT_DESC = "org.bluez.GattDescriptor1"

SOURCE_CUSTOM_SERVICE = "custom-service"
SOURCE_DEVICE_NAME = "device-name"
SOURCE_KEYBOARD_FALLBACK = "keyboard-fallback"


def _uuid(props):
    return str(props.get("UUID", "")).lower()


def _children(objects, parent, interface):
    prefix = str(parent) + "/"
    rows = []
    for path, interfaces in objects.items():
        path = str(path)
        if not path.startswith(prefix) or interface not in interfaces:
            continue
        # Direct children only: no further "/" after the prefix.
        if "/" in path[len(prefix):]:
            continue
        rows.append((path, interfaces[interface]))
    rows.sort(key=lambda row: row[0])
    return rows


def adapter_state(objects):
    adapters = sorted(
        (str(path), props[ADAPTER]) for path, props in objects.items() if ADAPTER in props
    )
    if not adapters:
        return {"present": False, "powered": False}
    return {
        "present": True,
        "powered": any(bool(props.get("Powered", False)) for _, props in adapters),
    }


def _device_name(props):
    for key in ("Alias", "Name"):
        value = props.get(key)
        if value:
            return str(value)
    return ""


def has_custom_service(objects, device_path):
    return any(
        _uuid(props) == protocol.SERVICE_UUID
        for _, props in _children(objects, device_path, GATT_SERVICE)
    )


def _matches_name(props, wanted):
    wanted = wanted.strip().casefold()
    if not wanted:
        return False
    return any(
        str(props.get(key, "")).strip().casefold() == wanted for key in ("Alias", "Name")
    )


def select_keyboard(objects, device_name=""):
    """Pick the keyboard to monitor.

    Order: connected device exposing the custom service (preferring one that
    also matches device_name); connected device matching device_name;
    connected device with Icon "input-keyboard" and a Battery1 interface.
    If nothing is connected, a paired device matching the same rules is
    returned with connected=False so the UI can name it.
    Returns None or a dict {path, name, connected, source, candidates}.
    """
    devices = sorted(
        (str(path), interfaces)
        for path, interfaces in objects.items()
        if DEVICE in interfaces
    )
    device_name = (device_name or "").strip()

    def pick(rows):
        rows = list(rows)
        if not rows:
            return None
        named = [row for row in rows if _matches_name(row[1][DEVICE], device_name)]
        return (named or rows)[0], len(rows)

    for connected in (True, False):
        pool = [
            (path, interfaces)
            for path, interfaces in devices
            if bool(interfaces[DEVICE].get("Connected", False)) == connected
            and (connected or bool(interfaces[DEVICE].get("Paired", False)))
        ]
        rules = (
            (SOURCE_CUSTOM_SERVICE, lambda row: has_custom_service(objects, row[0])),
            (SOURCE_DEVICE_NAME, lambda row: _matches_name(row[1][DEVICE], device_name)),
            (
                SOURCE_KEYBOARD_FALLBACK,
                lambda row: str(row[1][DEVICE].get("Icon", "")) == "input-keyboard"
                and (BATTERY in row[1] or not connected),
            ),
        )
        for source, rule in rules:
            chosen = pick(row for row in pool if rule(row))
            if chosen is None:
                continue
            (path, interfaces), count = chosen
            return {
                "path": path,
                "name": _device_name(interfaces[DEVICE]),
                "connected": connected,
                "servicesResolved": bool(interfaces[DEVICE].get("ServicesResolved", False)),
                "source": source,
                "candidates": count,
            }
    return None


def battery1_percent(objects, device_path):
    interfaces = objects.get(device_path) or {}
    props = interfaces.get(BATTERY)
    if not props:
        return None
    return protocol.battery_percent(props.get("Percentage"))


def gatt_layout(objects, device_path):
    """Return the attribute paths the bridge needs for one device.

    {"status": path|None, "firmware": path|None,
     "bas": [{"char": path, "cud": path|None, "cpf": path|None}, ...]}
    """
    layout = {"status": None, "firmware": None, "bas": []}
    for service_path, service in _children(objects, device_path, GATT_SERVICE):
        service_uuid = _uuid(service)
        if service_uuid == protocol.SERVICE_UUID:
            for char_path, char in _children(objects, service_path, GATT_CHAR):
                char_uuid = _uuid(char)
                if char_uuid == protocol.STATUS_UUID and layout["status"] is None:
                    layout["status"] = char_path
                elif char_uuid == protocol.FIRMWARE_UUID and layout["firmware"] is None:
                    layout["firmware"] = char_path
        elif service_uuid == protocol.BAS_UUID:
            for char_path, char in _children(objects, service_path, GATT_CHAR):
                if _uuid(char) != protocol.BATTERY_LEVEL_UUID:
                    continue
                entry = {"char": char_path, "cud": None, "cpf": None}
                for desc_path, desc in _children(objects, char_path, GATT_DESC):
                    desc_uuid = _uuid(desc)
                    if desc_uuid == protocol.CUD_UUID and entry["cud"] is None:
                        entry["cud"] = desc_path
                    elif desc_uuid == protocol.CPF_UUID and entry["cpf"] is None:
                        entry["cpf"] = desc_path
                layout["bas"].append(entry)
    return layout


def classify_bas(entries):
    """Assign Battery Level characteristics to the left and right halves.

    entries: [{"char": path, "cud": str|None, "cpf": int|None}, ...] where
    cud is the decoded user description and cpf the CPF description field.
    A characteristic is auxiliary (a split peripheral proxied by the central)
    when its CPF says "auxiliary" or its user description is "Peripheral N".
    The left half is the first non-auxiliary characteristic; the right half
    is the auxiliary one with the lowest peripheral index.
    """
    main = []
    aux = []
    for entry in entries:
        index = protocol.peripheral_index(entry.get("cud"))
        auxiliary = index is not None or entry.get("cpf") == protocol.CPF_DESCRIPTION_AUXILIARY
        if auxiliary:
            aux.append((index if index is not None else 1 << 16, entry["char"]))
        else:
            main.append(entry["char"])
    aux.sort()
    return {
        "left": main[0] if main else None,
        "right": aux[0][1] if aux else None,
    }
