"""BlueZ GetManagedObjects fixtures.

`old_firmware()` mirrors the tree BlueZ exported for a real Corne on stock
ZMK (one Battery Service, no custom service), with the address anonymised.
`new_firmware()` adds the custom status service and ZMK's split battery
proxy, whose layout follows zmk/app/src/split/bluetooth/central_bas_proxy.c.
"""

import copy

ADAPTER = "/org/bluez/hci0"
KEYBOARD = ADAPTER + "/dev_AA_BB_CC_DD_EE_01"
HEADPHONES = ADAPTER + "/dev_AA_BB_CC_DD_EE_02"
OTHER_KEYBOARD = ADAPTER + "/dev_AA_BB_CC_DD_EE_03"

SIG = "-0000-1000-8000-00805f9b34fb"


def sig(short):
    return "0000%s%s" % (short.lower(), SIG)


def device(name, connected=True, icon="input-keyboard", battery=None, paired=True):
    interfaces = {
        "org.bluez.Device1": {
            "Name": name,
            "Alias": name,
            "Icon": icon,
            "Paired": paired,
            "Connected": connected,
            "ServicesResolved": connected,
        }
    }
    if battery is not None:
        interfaces["org.bluez.Battery1"] = {"Percentage": battery, "Source": "GATT Battery Service"}
    return interfaces


def service(uuid):
    return {"org.bluez.GattService1": {"UUID": uuid, "Primary": True}}


def char(uuid, flags):
    return {"org.bluez.GattCharacteristic1": {"UUID": uuid, "Flags": flags, "Notifying": False}}


def desc(uuid):
    return {"org.bluez.GattDescriptor1": {"UUID": uuid}}


def old_firmware(connected=True):
    k = KEYBOARD
    return {
        ADAPTER: {"org.bluez.Adapter1": {"Powered": True}},
        k: device("Corne", connected=connected, battery=93 if connected else None),
        k + "/service0001": service(sig("1801")),
        k + "/service0001/char0002": char(sig("2a05"), ["indicate"]),
        k + "/service0009": service(sig("1800")),
        k + "/service0010": service(sig("180f")),
        k + "/service0010/char0011": char(sig("2a19"), ["read", "notify"]),
        k + "/service0010/char0011/desc0013": desc(sig("2902")),
        k + "/service0010/char0011/desc0014": desc(sig("2904")),
        k + "/service0015": service(sig("180a")),
        k + "/service001c": service(sig("1812")),
        HEADPHONES: device("Buds", icon="audio-headphones", battery=50),
    }


def new_firmware(right_bas=True):
    from bridge.zmkstatus import protocol

    objects = copy.deepcopy(old_firmware())
    k = KEYBOARD
    objects[k + "/service0030"] = service(protocol.SERVICE_UUID)
    objects[k + "/service0030/char0031"] = char(protocol.STATUS_UUID, ["read", "notify"])
    objects[k + "/service0030/char0031/desc0033"] = desc(sig("2902"))
    objects[k + "/service0030/char0034"] = char(protocol.FIRMWARE_UUID, ["read"])
    if right_bas:
        objects[k + "/service0040"] = service(sig("180f"))
        objects[k + "/service0040/char0041"] = char(sig("2a19"), ["read", "notify"])
        objects[k + "/service0040/char0041/desc0043"] = desc(sig("2902"))
        objects[k + "/service0040/char0041/desc0044"] = desc(sig("2904"))
        objects[k + "/service0040/char0041/desc0045"] = desc(sig("2901"))
    return objects
