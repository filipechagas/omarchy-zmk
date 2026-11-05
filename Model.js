.pragma library

// Pure view logic for the ZMK Keyboard plugin. No QML types, no side effects:
// Service.qml and Panel.qml feed bridge messages in and render what comes out,
// and tests/qml/tst_Model.qml exercises every function here.

var PROTOCOL_VERSION = 1;
var MAX_LINE_CHARS = 1000000;
var LOW_BATTERY = 20;
var DEFAULT_ID = "io.github.filipechagas.zmk";

function emptyState() {
    return {
        v: PROTOCOL_VERSION,
        type: "state",
        bluez: true,
        adapter: { present: false, powered: false },
        device: null,
        features: { customService: false, status: false, firmware: false, rightBas: false },
        status: null,
        statusError: null,
        firmware: null,
        left: { percent: null, source: null, trend: null },
        right: { percent: null, source: null, connected: null, disconnectedSince: null, trend: null }
    };
}

function emptyKeymap() {
    return { configured: false, ok: false, layers: [], geometry: null };
}

function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseLine(line) {
    var text = String(line === undefined || line === null ? "" : line);
    if (text.length === 0)
        return { ok: false, error: "empty" };
    if (text.length > MAX_LINE_CHARS)
        return { ok: false, error: "too_long" };
    var value;
    try {
        value = JSON.parse(text);
    } catch (e) {
        return { ok: false, error: "bad_json" };
    }
    if (!isObject(value) || typeof value.type !== "string")
        return { ok: false, error: "bad_shape" };
    if (value.v !== PROTOCOL_VERSION)
        return { ok: false, error: "bad_version" };
    return { ok: true, value: value };
}

// -- settings ---------------------------------------------------------------

function stringSetting(settings, key) {
    if (!isObject(settings))
        return "";
    var value = settings[key];
    return value === undefined || value === null ? "" : String(value).trim();
}

function normalizeSettings(settings) {
    return {
        deviceName: stringSetting(settings, "deviceName"),
        keymapPath: stringSetting(settings, "keymapPath")
    };
}

// The shell gives services no settings of their own, so read this widget's
// inline entry from the detached bar config. Returns null when not found.
function settingsFromBarConfig(barConfig, pluginId) {
    var id = pluginId || DEFAULT_ID;
    var layout = isObject(barConfig) ? barConfig.layout : null;
    if (!isObject(layout))
        return null;
    var sections = Object.keys(layout);
    for (var s = 0; s < sections.length; s++) {
        var entries = layout[sections[s]];
        if (!Array.isArray(entries))
            continue;
        for (var i = 0; i < entries.length; i++) {
            var entry = entries[i];
            if (isObject(entry) && entry.id === id)
                return entry;
        }
    }
    return null;
}

function bridgeArguments(settings) {
    var normalized = normalizeSettings(settings);
    var args = ["--stdio"];
    if (normalized.deviceName !== "")
        args.push("--device-name", normalized.deviceName);
    if (normalized.keymapPath !== "")
        args.push("--keymap", normalized.keymapPath);
    return args;
}

// Distro packages (python-dbus, python-gobject) live with the system
// interpreter, while the shell's PATH may put a version-manager shim (mise,
// pyenv) without them first. Prefer /usr/bin/python3 and fall back to PATH.
var PYTHON_LAUNCHER = 'if [ -x /usr/bin/python3 ]; then exec /usr/bin/python3 "$@"; fi; exec python3 "$@"';

function bridgeCommand(scriptPath, settings) {
    return ["/bin/sh", "-c", PYTHON_LAUNCHER, "zmk-bridge", String(scriptPath)].concat(bridgeArguments(settings));
}

// -- layers -----------------------------------------------------------------

function layerCount(keymap) {
    return keymap && keymap.ok && Array.isArray(keymap.layers) ? keymap.layers.length : 0;
}

function layerName(keymap, index) {
    if (index === null || index === undefined || index < 0)
        return "";
    if (layerCount(keymap) > index && keymap.layers[index] && keymap.layers[index].name)
        return String(keymap.layers[index].name);
    return "Layer " + index;
}

// Tabs for the panel: every layer in the keymap, or one per active layer bit
// up to the highest active layer when no keymap is configured.
function layerTabs(keymap, status) {
    var count = layerCount(keymap);
    var tabs = [];
    var active = status && Array.isArray(status.activeLayers) ? status.activeLayers : [];
    var highest = status && typeof status.layer === "number" ? status.layer : -1;
    if (count === 0)
        count = Math.max(highest + 1, 0);
    for (var i = 0; i < count; i++) {
        tabs.push({
            index: i,
            name: layerName(keymap, i),
            highest: i === highest,
            active: active.indexOf(i) !== -1
        });
    }
    return tabs;
}

// Tab showing the keyboard's highest active layer, or 0 when it has no tab.
// The panel selects it on open and whenever the active layer changes.
function activeLayerTab(status, tabCount) {
    var layer = status && typeof status.layer === "number" ? status.layer : 0;
    return layer >= 0 && layer < tabCount ? layer : 0;
}

function keyAt(keymap, layerIndex, keyIndex) {
    if (layerCount(keymap) <= layerIndex || layerIndex < 0)
        return null;
    var keys = keymap.layers[layerIndex].keys || [];
    return keyIndex >= 0 && keyIndex < keys.length ? keys[keyIndex] : null;
}

// -- battery ----------------------------------------------------------------

function validPercent(value) {
    return typeof value === "number" && isFinite(value) && value >= 0 && value <= 100;
}

function batteryTone(percent, linked) {
    if (linked === false || !validPercent(percent))
        return "muted";
    return percent <= LOW_BATTERY ? "low" : "normal";
}

function percentText(percent) {
    return validPercent(percent) ? Math.round(percent) + "%" : "—";
}

function sourceText(source) {
    if (source === "status")
        return "ZMK status service";
    if (source === "bas")
        return "Battery Service";
    if (source === "battery1")
        return "BlueZ battery";
    return "";
}

function formatDuration(seconds) {
    var s = Math.max(0, Math.floor(Number(seconds) || 0));
    if (s < 60)
        return s + "s";
    var m = Math.floor(s / 60);
    if (m < 60)
        return m + "m";
    var h = Math.floor(m / 60);
    if (h < 48)
        return h + "h " + (m % 60) + "m";
    return Math.floor(h / 24) + "d " + (h % 24) + "h";
}

function trendText(trend, percent) {
    if (!isObject(trend))
        return "";
    if (trend.perHour === null || trend.perHour === undefined) {
        if (!trend.samples)
            return "No history yet";
        return trend.spanMinutes > 0 ? "Collecting trend (" + formatDuration(trend.spanMinutes * 60) + ")" : "Collecting trend";
    }
    var rate = Number(trend.perHour);
    if (Math.abs(rate) < 0.05)
        return "Steady";
    var text = (rate < 0 ? "Draining " : "Charging ") + Math.abs(rate).toFixed(1) + "%/h";
    if (rate < 0 && validPercent(percent) && percent > 0)
        text += " · ~" + formatDuration(percent / Math.abs(rate) * 3600) + " left";
    return text;
}

// -- connection details ------------------------------------------------------

function connected(state) {
    return !!(state && state.device && state.device.connected);
}

function connectionText(state) {
    if (!state || state.bluez === false)
        return "Bluetooth service unavailable";
    if (!state.adapter || !state.adapter.present)
        return "No Bluetooth adapter";
    if (!state.adapter.powered)
        return "Bluetooth is off";
    if (!state.device)
        return "No ZMK keyboard found";
    return state.device.connected ? "Connected" : "Disconnected";
}

function profileText(status) {
    if (!status || typeof status.profile !== "number")
        return "Unavailable";
    return "Profile " + (status.profile + 1) + " (BT_SEL " + status.profile + ")";
}

function rightLinkText(state, nowMs) {
    if (!connected(state))
        return "—";
    var right = state.right || {};
    if (right.connected === true)
        return "Connected";
    if (right.connected === false) {
        if (typeof right.disconnectedSince === "number" && typeof nowMs === "number")
            return "Disconnected for " + formatDuration(nowMs / 1000 - right.disconnectedSince);
        return "Disconnected";
    }
    return "Unavailable";
}

function capsWordVisible(state) {
    return !!(state && state.status && state.status.capsWordSupported);
}

function capsWordText(state) {
    if (!capsWordVisible(state))
        return "Unavailable";
    return state.status.capsWord ? "On" : "Off";
}

function firmwareText(state) {
    if (!connected(state))
        return "—";
    if (state.firmware)
        return String(state.firmware);
    return state.features && state.features.customService ? "Reading…" : "Unavailable";
}

function statusNote(state) {
    if (!connected(state))
        return "";
    if (state.statusError === "unsupported_version")
        return "The keyboard reports a newer status format than this plugin understands. Update the plugin.";
    if (state.statusError)
        return "The keyboard sent a status payload this plugin could not read (" + state.statusError + ").";
    if (!state.features || !state.features.customService)
        return "This firmware has no ZMK status service: layer, profile, and right-half details are unavailable.";
    return "";
}

// -- bar --------------------------------------------------------------------

// The bar draws only an icon. Battery and layer change while typing, so they
// stay out of the bar and its tooltip and live in the panel; the accessible
// name still carries them, since a screen reader asks for it on demand.
function barView(state, keymap) {
    var view = {
        present: !!(state && state.device),
        connected: connected(state),
        tooltip: "",
        accessibleName: ""
    };
    var name = view.present ? String(state.device.name || "Keyboard") : "ZMK keyboard";
    if (!view.connected) {
        view.tooltip = view.present ? name + " — " + connectionText(state) : connectionText(state);
        view.accessibleName = view.tooltip;
        return view;
    }
    var left = state.left || {};
    var right = state.right || {};
    var status = state.status;
    var parts = [name, "Left " + percentText(left.percent)];
    if (right.connected === false)
        parts.push("Right disconnected");
    else
        parts.push("Right " + percentText(right.percent));
    if (status)
        parts.push("Layer " + layerName(keymap, status.layer));
    view.tooltip = name;
    view.accessibleName = parts.join(" · ");
    return view;
}

// -- notifications ------------------------------------------------------------

function notificationFor(alert) {
    if (!isObject(alert))
        return null;
    var device = alert.device ? String(alert.device) : "Keyboard";
    if (alert.kind === "battery_low") {
        var half = alert.half === "right" ? "Right" : "Left";
        return {
            title: device + ": " + half + " half at " + Math.round(alert.percent) + "%",
            body: half + " half battery is at or below " + alert.threshold + "%.",
            urgency: alert.threshold <= 10 ? "critical" : "normal"
        };
    }
    if (alert.kind === "right_disconnected") {
        return {
            title: device + ": right half disconnected",
            body: "The right half has been disconnected for over a minute while the left half is connected.",
            urgency: "normal"
        };
    }
    return null;
}

// -- layout helpers -------------------------------------------------------------

function shouldStackInfoRow(width, labelWidth, valueWidth, spacing) {
    return width > 0 && labelWidth + spacing + valueWidth > width;
}

function keyUnit(geometry, width, maxUnit) {
    if (!geometry || !(geometry.width > 0) || !(width > 0))
        return 0;
    return Math.min(maxUnit, width / geometry.width);
}
