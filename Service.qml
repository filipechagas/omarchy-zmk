pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Shell-level singleton: owns the Python bridge and desktop notifications.
// Panel.qml instances (one per bar/monitor) only
// read from here, so notifications fire once no matter how many bars exist.
Item {
    id: root

    property var shell: null
    property var manifest: null

    // Settings pushed by Panel.qml; used only when the bar config is not
    // readable through the shell facade.
    property var panelSettings: null

    property var keyboardState: Model.emptyState()
    property var keymap: Model.emptyKeymap()
    property string bridgePhase: "idle"
    property string bridgeError: ""
    property string lastBridgeLog: ""
    property double clockMs: Date.now()

    property bool _completed: false
    property bool _destroying: false
    property bool _expectRunning: false
    property bool _restartPending: false
    property int _restartDelay: 2000

    readonly property string pluginId: manifest && typeof manifest.id === "string" ? manifest.id : Model.DEFAULT_ID
    readonly property var barSettings: Model.settingsFromBarConfig(shell ? shell.barConfig : null, pluginId)
    readonly property var settings: Model.normalizeSettings(barSettings !== null ? barSettings : panelSettings)
    readonly property var bridgeArgs: Model.bridgeArguments(settings)
    readonly property string bridgeArgsKey: JSON.stringify(bridgeArgs)
    readonly property var view: Model.barView(keyboardState, keymap)

    implicitWidth: 0
    implicitHeight: 0
    visible: false

    function sourceDirectory() {
        if (!manifest || typeof manifest.__sourceDir !== "string")
            return "";
        return manifest.__sourceDir;
    }

    function configure(widgetSettings) {
        panelSettings = widgetSettings && typeof widgetSettings === "object" ? widgetSettings : null;
    }

    function startBridge() {
        var directory = sourceDirectory();
        if (!_completed || _destroying || directory === "" || bridge.running)
            return;
        bridge.command = Model.bridgeCommand(directory + "/bridge/zmk_bridge.py", settings);
        bridge.workingDirectory = directory;
        bridgeError = "";
        bridgePhase = "starting";
        _expectRunning = true;
        bridge.running = true;
    }

    function restartBridge() {
        restartTimer.stop();
        if (bridge.running) {
            _restartPending = true;
            _expectRunning = false;
            bridge.running = false;
        } else {
            startBridge();
        }
    }

    function refresh() {
        if (bridge.running)
            bridge.write(JSON.stringify({ v: Model.PROTOCOL_VERSION, type: "refresh" }) + "\n");
        else
            restartBridge();
    }

    function notify(alert) {
        var note = Model.notificationFor(alert);
        if (!note)
            return;
        Quickshell.execDetached(["notify-send", "--app-name=ZMK Keyboard", "--icon=input-keyboard", "--urgency=" + note.urgency, note.title, note.body]);
    }

    function handleLine(line) {
        var parsed = Model.parseLine(line);
        if (!parsed.ok) {
            if (parsed.error !== "empty")
                lastBridgeLog = "Ignored bridge line (" + parsed.error + ")";
            return;
        }
        var message = parsed.value;
        if (message.type === "hello") {
            bridgePhase = "running";
            _restartDelay = 2000;
        } else if (message.type === "state") {
            keyboardState = message;
        } else if (message.type === "keymap") {
            keymap = message;
        } else if (message.type === "alert") {
            notify(message);
        } else if (message.type === "fatal") {
            _expectRunning = false;
            bridgePhase = "failed";
            bridgeError = String(message.code || "fatal") + (message.detail ? ": " + message.detail : "");
        }
    }

    function handleExit() {
        if (_destroying)
            return;
        if (_restartPending) {
            _restartPending = false;
            Qt.callLater(startBridge);
            return;
        }
        keyboardState = Model.emptyState();
        if (!_expectRunning) {
            if (bridgePhase !== "failed")
                bridgePhase = "idle";
            return;
        }
        bridgePhase = "restarting";
        restartTimer.interval = _restartDelay;
        _restartDelay = Math.min(_restartDelay * 2, 60000);
        restartTimer.restart();
    }

    onBridgeArgsKeyChanged: if (_completed)
        restartBridge()
    onManifestChanged: if (_completed && !bridge.running)
        startBridge()

    Timer {
        id: restartTimer
        repeat: false
        onTriggered: root.startBridge()
    }

    Timer {
        // Drives the "disconnected for" label.
        interval: 1000
        repeat: true
        running: (root.keyboardState.right && root.keyboardState.right.connected === false)
        onTriggered: root.clockMs = Date.now()
    }

    Process {
        id: bridge
        stdinEnabled: true

        stdout: SplitParser {
            onRead: data => root.handleLine(data)
        }

        stderr: SplitParser {
            onRead: data => root.lastBridgeLog = String(data)
        }

        onRunningChanged: if (!running)
            root.handleExit()
    }

    Component.onCompleted: {
        _completed = true;
        startBridge();
    }

    Component.onDestruction: {
        _destroying = true;
        restartTimer.stop();
        if (bridge.running) {
            bridge.write(JSON.stringify({ v: Model.PROTOCOL_VERSION, type: "shutdown" }) + "\n");
            bridge.running = false;
        }
    }
}
