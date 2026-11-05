import QtQuick
import Quickshell
import qs.Ui as Ui

// Host smoke test: loads the real Service.qml and Panel.qml inside Quickshell
// with a fake bridge (fixtures/fake-plugin) and fake bars, drives the scripted
// lifecycle, and exits 0 only when every check passed. run-host-smoke.sh then
// checks the logs the fake bridge and fake notify-send wrote.
ShellRoot {
    id: root

    readonly property string pluginRoot: Quickshell.env("ZMK_PLUGIN_ROOT")
    readonly property string bridgeRoot: Quickshell.env("ZMK_BRIDGE_ROOT")
    readonly property string pluginId: "io.github.filipechagas.zmk"
    property var failures: []
    property var service: null
    property var horizontalPanel: null
    property var verticalPanel: null
    property int step: 0

    function check(condition, message) {
        if (!condition)
            failures.push(message);
    }

    function load(name) {
        var component = Qt.createComponent("file://" + pluginRoot + "/" + name, Component.PreferSynchronous);
        check(component.status === Component.Ready, name + ": " + component.errorString());
        return component.status === Component.Ready ? component : null;
    }

    function createPanel(component, barObject) {
        var panel = component.createObject(host);
        check(panel !== null, "Panel.qml createObject returned null");
        if (!panel)
            return null;
        panel.moduleName = pluginId;
        panel.settings = fakeShell.barConfig.layout.right[0];
        panel.bar = barObject;
        return panel;
    }

    function run() {
        var serviceComponent = load("Service.qml");
        var panelComponent = load("Panel.qml");
        if (!serviceComponent || !panelComponent)
            return finish();
        service = serviceComponent.createObject(null, {
            shell: fakeShell,
            manifest: { id: pluginId, __sourceDir: bridgeRoot }
        });
        check(service !== null, "Service.qml createObject returned null");
        horizontalPanel = createPanel(panelComponent, horizontalBar);
        verticalPanel = createPanel(panelComponent, verticalBar);
        ticker.start();
    }

    function advance() {
        step += 1;
        if (step === 1) {
            check(service.bridgePhase === "running", "bridge did not reach running: " + service.bridgePhase);
            check(service.keyboardState.device !== null, "no state from bridge");
            check(service.keymap.ok === true, "keymap message not applied");
            // Battery and layer stay out of the bar and its tooltip.
            check(service.view.tooltip === "Corne", "bar tooltip: " + service.view.tooltip);
            check(service.view.accessibleName.indexOf("Left 93%") !== -1, "accessible name lacks battery: " + service.view.accessibleName);
            check(service.lastBridgeLog === "Ignored bridge line (bad_json)", "bad line not ignored: " + service.lastBridgeLog);
            check(horizontalPanel.hasService, "panel did not find its service via bar.shell.serviceFor");
            check(horizontalPanel.view.accessibleName.indexOf("Right 71%") !== -1, "panel accessible name: " + horizontalPanel.view.accessibleName);
            // The viewed layer tab follows the keyboard's active layer.
            check(horizontalPanel.viewedLayer === 1, "viewed layer does not follow the active layer: " + horizontalPanel.viewedLayer);
            // Icon only: the widget takes the same slot as a stock bar icon.
            check(horizontalPanel.implicitWidth === stockIcon.implicitWidth, "horizontal widget is not one icon slot: " + horizontalPanel.implicitWidth + " vs " + stockIcon.implicitWidth);
            check(verticalPanel.implicitHeight === stockVerticalIcon.implicitHeight, "vertical widget is not one icon slot: " + verticalPanel.implicitHeight + " vs " + stockVerticalIcon.implicitHeight);
        } else if (step === 2) {
            // The popup is never opened: on a live session that would map a
            // full-screen layer-shell surface. Its content is built eagerly,
            // so its bindings have already been evaluated by now.
            check(horizontalPanel.layerTabs.length === 2 && horizontalPanel.layerTabs[1].highest, "layer tabs wrong");
            horizontalPanel.selectLayer(1);
            check(horizontalPanel.viewedLayer === 1, "selectLayer failed");
            horizontalPanel.selectLayer(9);
            check(horizontalPanel.viewedLayer === 1, "selectLayer did not clamp");
            fakeShell.barConfig = {
                layout: { right: [{ id: pluginId, deviceName: "Other", keymapPath: "" }] }
            };
            check(service.settings.deviceName === "Other", "settings change not seen");
        } else if (step === 3) {
            check(service.bridgePhase === "running", "bridge did not restart: " + service.bridgePhase);
            service.refresh();
        } else if (step === 4) {
            horizontalPanel.destroy();
            verticalPanel.destroy();
            service.destroy();
        } else {
            ticker.stop();
            finish();
        }
    }

    function finish() {
        for (let i = 0; i < failures.length; i++)
            console.error("HOST-SMOKE:", failures[i]);
        if (failures.length === 0)
            console.log("HOST-SMOKE: PASS");
        Qt.exit(failures.length === 0 ? 0 : 1);
    }

    Timer {
        id: ticker
        interval: 700
        repeat: true
        onTriggered: root.advance()
    }

    Item {
        id: host

        // Reference widths for the icon-only bar widget.
        Ui.BarIconButton {
            id: stockIcon
            bar: horizontalBar
            text: "\u{f030c}"
        }

        Ui.BarIconButton {
            id: stockVerticalIcon
            bar: verticalBar
            text: "\u{f030c}"
        }
    }

    QtObject {
        id: fakeShell

        property var barConfig: ({
                layout: {
                    right: [{ id: "io.github.filipechagas.zmk", deviceName: "Corne", keymapPath: "/tmp/k.yaml" }]
                }
            })

        function serviceFor(id) {
            return id === root.pluginId ? root.service : null;
        }
    }

    component FakeBar: QtObject {
        property var shell: null
        property bool vertical: false
        property int barSize: 26
        property string position: "top"
        property string fontFamily: "monospace"
        property color foreground: "white"
        property color barForeground: "white"
        property color urgent: "red"
        property bool foregroundAnimationEnabled: false
        property var activePopout: null

        function requestPopout(owner) {
            activePopout = owner;
        }
        function releasePopout(owner) {
            if (activePopout === owner)
                activePopout = null;
        }
        function registerClickTarget(target) {}
        function unregisterClickTarget(target) {}
        function showTooltip(target, text) {}
        function hideTooltip(target) {}
        function switchPanelFrom(panel, direction) {
            return false;
        }
        function moduleWidgets(name) {
            return [];
        }
    }

    FakeBar {
        id: horizontalBar
        shell: fakeShell
    }

    FakeBar {
        id: verticalBar
        shell: fakeShell
        vertical: true
        position: "left"
    }

    Component.onCompleted: Qt.callLater(root.run)
}
