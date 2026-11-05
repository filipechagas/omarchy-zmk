import QtQuick
import QtTest
import "../../Model.js" as Model

TestCase {
    name: "ZmkModel"

    function keymapFixture() {
        return {
            v: 1,
            type: "keymap",
            configured: true,
            ok: true,
            layers: [
                { index: 0, name: "default", keys: [{ t: "Q", h: "", s: "", type: "" }] },
                { index: 1, name: "sym", keys: [{ t: "!", h: "", s: "", type: "" }] },
                { index: 2, name: "num", keys: [] },
                { index: 3, name: "nav", keys: [{ t: "", h: "", s: "", type: "held" }] }
            ],
            geometry: { source: "split-3x6+3", width: 13, height: 4.15, keys: [] }
        };
    }

    function connectedState(overrides) {
        var state = Model.emptyState();
        state.adapter = { present: true, powered: true };
        state.device = { name: "Corne", connected: true, source: "custom-service", candidates: 1 };
        state.features = { customService: true, status: true, firmware: true, rightBas: true };
        state.status = { version: 1, layer: 0, layerMask: 1, activeLayers: [0], profile: 0, rightConnected: true, capsWordSupported: true, capsWord: false, leftBattery: 93, rightBattery: 71 };
        state.firmware = "07f8bdb";
        state.left = { percent: 93, source: "status", trend: { perHour: null, spanMinutes: 0, samples: 1, points: [93] } };
        state.right = { percent: 71, source: "status", connected: true, disconnectedSince: null, trend: null };
        var keys = Object.keys(overrides || {});
        for (let i = 0; i < keys.length; i++)
            state[keys[i]] = overrides[keys[i]];
        return state;
    }

    function oldFirmwareState() {
        var state = connectedState();
        state.device.source = "keyboard-fallback";
        state.features = { customService: false, status: false, firmware: false, rightBas: false };
        state.status = null;
        state.firmware = null;
        state.left = { percent: 93, source: "battery1", trend: null };
        state.right = { percent: null, source: null, connected: null, disconnectedSince: null, trend: null };
        return state;
    }

    function test_parseLine() {
        compare(Model.parseLine('{"v":1,"type":"hello"}').ok, true);
        compare(Model.parseLine("").error, "empty");
        compare(Model.parseLine("{").error, "bad_json");
        compare(Model.parseLine("[1]").error, "bad_shape");
        compare(Model.parseLine('{"v":2,"type":"state"}').error, "bad_version");
        compare(Model.parseLine('{"v":1}').error, "bad_shape");
    }

    function test_settingsFromBarConfig() {
        var config = {
            layout: {
                left: [{ id: "omarchy.menu" }],
                right: [{ id: "omarchy.audio" }, { id: "io.github.filipechagas.zmk", keymapPath: "~/k.yaml" }]
            }
        };
        compare(Model.settingsFromBarConfig(config, "io.github.filipechagas.zmk").keymapPath, "~/k.yaml");
        compare(Model.settingsFromBarConfig(config, ""), Model.settingsFromBarConfig(config, Model.DEFAULT_ID));
        compare(Model.settingsFromBarConfig({ layout: { right: [] } }, Model.DEFAULT_ID), null);
        compare(Model.settingsFromBarConfig(null, Model.DEFAULT_ID), null);
    }

    function test_bridgeArguments() {
        compare(Model.bridgeArguments(null), ["--stdio"]);
        compare(Model.bridgeArguments({ deviceName: " Corne ", keymapPath: "/k.yaml", unknown: "x" }), ["--stdio", "--device-name", "Corne", "--keymap", "/k.yaml"]);
        compare(Model.normalizeSettings({ keymapPath: null }).keymapPath, "");
        var command = Model.bridgeCommand("/p/bridge/zmk_bridge.py", { keymapPath: "/k.yaml" });
        compare(command.slice(0, 2), ["/bin/sh", "-c"]);
        verify(command[2].indexOf("/usr/bin/python3") !== -1);
        compare(command.slice(3), ["zmk-bridge", "/p/bridge/zmk_bridge.py", "--stdio", "--keymap", "/k.yaml"]);
    }

    function test_layerNames() {
        var keymap = keymapFixture();
        compare(Model.layerName(keymap, 3), "nav");
        compare(Model.layerName(Model.emptyKeymap(), 3), "Layer 3");
        compare(Model.layerName(keymap, 9), "Layer 9");
    }

    function test_layerTabs() {
        var status = { layer: 3, activeLayers: [0, 3] };
        var tabs = Model.layerTabs(keymapFixture(), status);
        compare(tabs.length, 4);
        compare(tabs[3].highest, true);
        compare(tabs[0].active, true);
        compare(tabs[1].active, false);
        var noKeymap = Model.layerTabs(Model.emptyKeymap(), status);
        compare(noKeymap.length, 4);
        compare(noKeymap[2].name, "Layer 2");
        compare(Model.layerTabs(Model.emptyKeymap(), null).length, 0);
    }

    // The bar shows only an icon; battery and layer stay in the panel, so
    // the tooltip names the keyboard and nothing that changes while typing.
    function test_barView_connected() {
        var state = connectedState();
        state.status.layer = 3;
        var view = Model.barView(state, keymapFixture());
        compare(view.connected, true);
        compare(view.tooltip, "Corne");
        compare(view.accessibleName, "Corne · Left 93% · Right 71% · Layer nav");
        compare(view.left, undefined);
        compare(view.layer, undefined);
    }

    function test_barView_disconnected_right() {
        var state = connectedState();
        state.right = { percent: 60, source: "status", connected: false, disconnectedSince: 100, trend: null };
        var view = Model.barView(state, keymapFixture());
        compare(view.tooltip, "Corne");
        verify(view.accessibleName.indexOf("Right disconnected") !== -1);
    }

    function test_barView_disconnected() {
        var state = connectedState();
        state.device.connected = false;
        var view = Model.barView(state, keymapFixture());
        compare(view.connected, false);
        compare(view.tooltip, "Corne — Disconnected");
        compare(Model.barView(Model.emptyState(), null).tooltip, "No Bluetooth adapter");
    }

    function test_details() {
        var state = connectedState();
        compare(Model.profileText(state.status), "Profile 1 (BT_SEL 0)");
        compare(Model.profileText(null), "Unavailable");
        compare(Model.capsWordText(state), "Off");
        compare(Model.firmwareText(state), "07f8bdb");
        compare(Model.rightLinkText(state, 0), "Connected");
        state.right.connected = false;
        state.right.disconnectedSince = 1000;
        compare(Model.rightLinkText(state, 1090 * 1000), "Disconnected for 1m");
        var old = oldFirmwareState();
        compare(Model.rightLinkText(old, 0), "Unavailable");
        compare(Model.capsWordVisible(old), false);
        compare(Model.firmwareText(old), "Unavailable");
        verify(Model.statusNote(old).indexOf("no ZMK status service") !== -1);
        compare(Model.statusNote(state), "");
        state.statusError = "unsupported_version";
        verify(Model.statusNote(state).indexOf("newer status format") !== -1);
    }

    function test_trendText() {
        compare(Model.trendText(null, 50), "");
        compare(Model.trendText({ perHour: null, samples: 0, spanMinutes: 0 }, 50), "No history yet");
        compare(Model.trendText({ perHour: null, samples: 3, spanMinutes: 12 }, 50), "Collecting trend (12m)");
        compare(Model.trendText({ perHour: 0.01, samples: 9, spanMinutes: 90 }, 50), "Steady");
        compare(Model.trendText({ perHour: -2, samples: 9, spanMinutes: 90 }, 50), "Draining 2.0%/h · ~25h 0m left");
        compare(Model.trendText({ perHour: 5.5, samples: 9, spanMinutes: 90 }, 50), "Charging 5.5%/h");
    }

    function test_notifications() {
        var low = Model.notificationFor({ kind: "battery_low", half: "right", threshold: 10, percent: 9, device: "Corne" });
        compare(low.title, "Corne: Right half at 9%");
        compare(low.urgency, "critical");
        compare(Model.notificationFor({ kind: "battery_low", half: "left", threshold: 20, percent: 20 }).urgency, "normal");
        compare(Model.notificationFor({ kind: "right_disconnected", device: "Corne" }).title, "Corne: right half disconnected");
        compare(Model.notificationFor({ kind: "nope" }), null);
    }

    function test_activeLayerTab() {
        compare(Model.activeLayerTab({ layer: 3 }, 6), 3);
        compare(Model.activeLayerTab({ layer: 7 }, 6), 0);
        compare(Model.activeLayerTab(null, 6), 0);
        compare(Model.activeLayerTab({ layer: 2 }, 0), 0);
    }

    function test_keyHelpers() {
        compare(Model.keyAt(keymapFixture(), 1, 0).t, "!");
        compare(Model.keyAt(keymapFixture(), 1, 5), null);
        compare(Model.keyAt(Model.emptyKeymap(), 0, 0), null);
        compare(Model.keyUnit({ width: 13 }, 520, 56), 40);
        compare(Model.keyUnit({ width: 4 }, 520, 56), 56);
        compare(Model.keyUnit(null, 520, 56), 0);
    }

    function test_formatDuration() {
        compare(Model.formatDuration(5), "5s");
        compare(Model.formatDuration(3600 * 3 + 120), "3h 2m");
        compare(Model.formatDuration(3600 * 50), "2d 2h");
    }
}
