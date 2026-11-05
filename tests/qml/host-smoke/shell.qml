import QtQuick
import Quickshell

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

    function findText(item, text) {
        if (!item)
            return null;
        if (item instanceof Text && item.text === text)
            return item;
        for (let i = 0; i < item.children.length; i++) {
            const found = findText(item.children[i], text);
            if (found)
                return found;
        }
        return null;
    }

    // Height the label covers in panel coordinates. Equal to its own height
    // unless the host scaled the bar content.
    function renderedHeight(panel, label) {
        var top = label.mapToItem(panel, 0, 0);
        var bottom = label.mapToItem(panel, 0, label.height);
        return bottom.y - top.y;
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
            check(service.view.left.text === "L 93%", "service bar text: " + service.view.left.text);
            check(service.view.layer.text === "NAV", "layer badge: " + service.view.layer.text);
            check(service.lastBridgeLog === "Ignored bridge line (bad_json)", "bad line not ignored: " + service.lastBridgeLog);
            check(horizontalPanel.hasService, "panel did not find its service via bar.shell.serviceFor");
            check(horizontalPanel.view.right.text === "R 71%", "panel right text: " + horizontalPanel.view.right.text);
            check(horizontalPanel.barText.indexOf("NAV") !== -1, "bar text lacks layer: " + horizontalPanel.barText);
            check(horizontalPanel.implicitWidth > horizontalPanel.iconSlot, "horizontal widget did not grow for text: " + horizontalPanel.implicitWidth);
            // Omarchy 4.5 shrinks a BarIconButton iconComponent to icon size;
            // the bar text must render at its own font size.
            const leftLabel = findText(horizontalPanel, "L 93%");
            check(leftLabel !== null, "bar text item for the left half not found");
            if (leftLabel)
                check(Math.abs(renderedHeight(horizontalPanel, leftLabel) - leftLabel.height) < 0.5, "bar text is scaled: rendered " + renderedHeight(horizontalPanel, leftLabel) + "px for a " + leftLabel.height + "px label");
            check(verticalPanel.verticalBar, "vertical bar not detected");
            check(verticalPanel.implicitHeight > verticalPanel.iconSlot, "vertical widget did not grow: " + verticalPanel.implicitHeight);
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
