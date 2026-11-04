pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as Controls
import qs.Commons as Commons
import qs.Ui as Ui
import "Model.js" as Model

Ui.Panel {
    id: root

    manageIpc: false

    property int viewedLayer: 0
    property bool serviceWaitExpired: false

    readonly property var service: {
        var hostShell = dynamicProperty(bar, "shell");
        return hostShell && typeof hostShell.serviceFor === "function" ? hostShell.serviceFor(moduleName) : null;
    }
    readonly property bool hasService: service !== null && service !== undefined
    readonly property var kbd: hasService ? service.keyboardState : Model.emptyState()
    readonly property var keymap: hasService ? service.keymap : Model.emptyKeymap()
    readonly property var view: Model.barView(kbd, keymap)
    readonly property var status: kbd.status
    readonly property var layerTabs: Model.layerTabs(keymap, status)
    readonly property double nowMs: hasService ? service.clockMs : Date.now()

    readonly property bool verticalBar: dynamicProperty(bar, "vertical") === true
    readonly property var barFontFamily: dynamicProperty(bar, "fontFamily")
    readonly property string fontFamily: typeof barFontFamily === "string" ? barFontFamily : Commons.Style.fontFamily
    readonly property int captionFontSize: Commons.Style.fontToken("caption", Commons.Style.fontPx(0.833))
    readonly property int bodySmallFontSize: Commons.Style.fontToken("body-small", Commons.Style.fontPx(0.917))
    readonly property int bodyFontSize: Commons.Style.fontToken("body", Commons.Style.fontPx(1))
    readonly property int displayFontSize: Commons.Style.fontToken("display", Commons.Style.fontPx(2))
    readonly property int iconFontSize: Commons.Style.barToken("icon-font", 13)
    readonly property real iconSlot: Commons.Style.barToken("icon-slot", 27)
    readonly property string keyboardGlyph: "\u{f030c}"

    readonly property string barText: view.connected ? view.left.text + "  " + view.right.text + (view.layer.visible ? "  " + view.layer.text : "") : ""
    readonly property int verticalLines: view.connected ? (view.layer.visible ? 3 : 2) : 0
    readonly property real barSlotSize: verticalBar ? Math.max(iconSlot, iconMetrics.height + verticalLines * captionMetrics.height + Commons.Style.space(6)) : iconSlot + (barText === "" ? 0 : barTextMeasure.advanceWidth + Commons.Style.space(14))

    visible: true
    implicitWidth: barButton.implicitWidth
    implicitHeight: barButton.implicitHeight

    function dynamicProperty(object, name) {
        return object ? object[name] : null;
    }

    function toneColor(tone) {
        if (tone === "low")
            return Commons.Color.urgent;
        if (tone === "muted")
            return Commons.Color.muted;
        if (tone === "accent")
            return Commons.Color.accent;
        return root.barForeground;
    }

    function selectLayer(index) {
        if (layerTabs.length === 0)
            return;
        viewedLayer = Math.max(0, Math.min(layerTabs.length - 1, index));
    }

    function pushSettings() {
        // Read `service` directly: during a plugin reload `hasService` can be
        // stale for one evaluation after the service is already gone.
        if (service && typeof service.configure === "function")
            service.configure(settings);
    }

    onServiceChanged: pushSettings()
    onSettingsChanged: pushSettings()

    onOpenedChanged: {
        if (!opened)
            return;
        bodyFlickable.contentY = 0;
        viewedLayer = Model.initialLayer(status, layerTabs.length);
    }

    Timer {
        interval: 2000
        repeat: false
        running: !root.hasService && !root.serviceWaitExpired
        onTriggered: root.serviceWaitExpired = true
    }

    TextMetrics {
        id: barTextMeasure
        font.family: root.fontFamily
        font.pixelSize: root.bodySmallFontSize
        font.bold: true
        text: root.barText
    }

    FontMetrics {
        id: iconMetrics
        font.family: root.fontFamily
        font.pixelSize: root.iconFontSize
    }

    FontMetrics {
        id: captionMetrics
        font.family: root.fontFamily
        font.pixelSize: root.captionFontSize
        font.bold: true
    }

    Component {
        id: barContent

        Item {
            Row {
                visible: !root.verticalBar
                anchors.centerIn: parent
                spacing: Commons.Style.space(5)

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.keyboardGlyph
                    color: root.barForeground
                    font.family: root.fontFamily
                    font.pixelSize: root.iconFontSize
                    Accessible.ignored: true
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.view.connected
                    text: root.view.left.text
                    color: root.toneColor(root.view.left.tone === "muted" ? "normal" : root.view.left.tone)
                    font.family: root.fontFamily
                    font.pixelSize: root.bodySmallFontSize
                    font.bold: true
                    Accessible.ignored: true
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.view.connected
                    text: root.view.right.text
                    color: root.toneColor(root.view.right.tone)
                    font.family: root.fontFamily
                    font.pixelSize: root.bodySmallFontSize
                    font.bold: true
                    Accessible.ignored: true
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: root.view.connected && root.view.layer.visible
                    text: root.view.layer.text
                    color: root.toneColor("accent")
                    font.family: root.fontFamily
                    font.pixelSize: root.bodySmallFontSize
                    font.bold: true
                    Accessible.ignored: true
                }
            }

            Column {
                visible: root.verticalBar
                anchors.centerIn: parent
                spacing: 0

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.keyboardGlyph
                    color: root.barForeground
                    font.family: root.fontFamily
                    font.pixelSize: root.iconFontSize
                    Accessible.ignored: true
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.view.connected
                    text: root.view.compact.left
                    color: root.toneColor(root.view.left.tone === "muted" ? "normal" : root.view.left.tone)
                    font.family: root.fontFamily
                    font.pixelSize: root.captionFontSize
                    font.bold: true
                    Accessible.ignored: true
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.view.connected
                    text: root.view.compact.right
                    color: root.toneColor(root.view.right.tone)
                    font.family: root.fontFamily
                    font.pixelSize: root.captionFontSize
                    font.bold: true
                    Accessible.ignored: true
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.view.connected && root.view.layer.visible
                    text: root.view.compact.layer
                    color: root.toneColor("accent")
                    font.family: root.fontFamily
                    font.pixelSize: root.captionFontSize
                    font.bold: true
                    Accessible.ignored: true
                }
            }
        }
    }

    Ui.BarIconButton {
        id: barButton
        anchors.fill: parent
        bar: root.bar
        dimmed: !root.view.connected
        slotSize: root.barSlotSize
        opticalSize: root.barSlotSize
        iconComponent: barContent
        tooltipText: root.view.tooltip || "ZMK Keyboard"
        onPressed: function (button) {
            if (button === Qt.LeftButton)
                root.toggle();
        }

        Accessible.role: Accessible.Button
        Accessible.name: root.view.accessibleName || "ZMK Keyboard"
        Accessible.description: root.opened ? "Closes keyboard status" : "Opens keyboard status"
        Accessible.onPressAction: root.toggle()
    }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: barButton
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: fittedContentWidth(Commons.Style.space(620))
        contentHeight: fittedContentHeight(contentColumn.implicitHeight, Commons.Style.space(720))

        Ui.PanelKeyCatcher {
            id: keyCatcher
            anchors.fill: parent
            onMoveRequested: function (dx, dy) {
                if (dx !== 0)
                    root.selectLayer(root.viewedLayer + dx);
            }
            onCloseRequested: root.close()
            onTabRequested: function (direction) {
                root.switchPanel(direction);
            }

            Flickable {
                id: bodyFlickable
                anchors.fill: parent
                contentWidth: width
                contentHeight: contentColumn.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                interactive: contentHeight > height
                clip: true

                Controls.ScrollBar.vertical: Controls.ScrollBar {
                    policy: Controls.ScrollBar.AsNeeded
                }

                Column {
                    id: contentColumn
                    width: bodyFlickable.width
                    spacing: Commons.Style.space(14)

                    Ui.PanelHero {
                        title: root.kbd.device ? root.kbd.device.name : "ZMK Keyboard"
                        meta: root.hasService ? Model.connectionText(root.kbd) : (root.serviceWaitExpired ? "Keyboard service unavailable" : "Keyboard service is starting")
                        foreground: root.barForeground
                        fontFamily: root.fontFamily
                        iconComponent: Component {
                            Text {
                                text: root.keyboardGlyph
                                color: root.barForeground
                                font.family: root.fontFamily
                                font.pixelSize: root.displayFontSize
                                Accessible.ignored: true
                            }
                        }
                    }

                    Text {
                        visible: text !== ""
                        width: parent.width
                        text: Model.statusNote(root.kbd)
                        color: Commons.Color.muted
                        font.family: root.fontFamily
                        font.pixelSize: root.captionFontSize
                        wrapMode: Text.WordWrap
                        Accessible.role: Accessible.StaticText
                        Accessible.name: text
                    }

                    Ui.PanelSeparator {
                        foreground: root.barForeground
                        Accessible.ignored: true
                    }

                    Column {
                        width: parent.width
                        spacing: Commons.Style.space(10)

                        Ui.PanelSectionHeader {
                            text: "BATTERY"
                            foreground: root.barForeground
                            fontFamily: root.fontFamily
                        }

                        BatteryRow {
                            label: "Left"
                            half: root.kbd.left || ({})
                            linked: Model.connected(root.kbd)
                        }

                        BatteryRow {
                            label: "Right"
                            half: root.kbd.right || ({})
                            linked: Model.connected(root.kbd) && (root.kbd.right ? root.kbd.right.connected !== false : true)
                        }
                    }

                    Ui.PanelSeparator {
                        foreground: root.barForeground
                        Accessible.ignored: true
                    }

                    Column {
                        width: parent.width
                        spacing: Commons.Style.space(8)

                        Ui.PanelSectionHeader {
                            text: "CONNECTION"
                            foreground: root.barForeground
                            fontFamily: root.fontFamily
                        }

                        InfoRow {
                            label: "Bluetooth profile"
                            value: Model.connected(root.kbd) ? Model.profileText(root.status) : "—"
                        }

                        InfoRow {
                            label: "Right half link"
                            value: Model.rightLinkText(root.kbd, root.nowMs)
                            valueColor: root.kbd.right && root.kbd.right.connected === false ? Commons.Color.urgent : root.barForeground
                        }

                        InfoRow {
                            visible: Model.capsWordVisible(root.kbd)
                            label: "Caps word"
                            value: Model.capsWordText(root.kbd)
                            valueColor: root.status && root.status.capsWord ? Commons.Color.accent : root.barForeground
                        }

                        InfoRow {
                            label: "Firmware"
                            value: Model.firmwareText(root.kbd)
                        }
                    }

                    Ui.PanelSeparator {
                        foreground: root.barForeground
                        Accessible.ignored: true
                    }

                    Column {
                        width: parent.width
                        spacing: Commons.Style.space(10)

                        Ui.PanelSectionHeader {
                            text: "LAYERS"
                            foreground: root.barForeground
                            fontFamily: root.fontFamily
                        }

                        Flow {
                            visible: root.layerTabs.length > 0
                            width: parent.width
                            spacing: Commons.Style.space(6)
                            Accessible.role: Accessible.PageTabList
                            Accessible.name: "Layers"

                            Repeater {
                                model: root.layerTabs

                                delegate: Ui.Button {
                                    id: tabButton
                                    required property var modelData
                                    text: modelData.highest ? "● " + modelData.name : modelData.name
                                    bordered: true
                                    selected: root.viewedLayer === modelData.index
                                    foreground: modelData.highest ? Commons.Color.accent : root.barForeground
                                    fontFamily: root.fontFamily
                                    fontSize: root.bodySmallFontSize
                                    tooltipText: modelData.highest ? "Active layer" : (modelData.active ? "Also active" : "")
                                    onClicked: root.selectLayer(modelData.index)

                                    Accessible.role: Accessible.PageTab
                                    Accessible.name: modelData.name + (modelData.highest ? ", active layer" : "")
                                    Accessible.checkable: true
                                    Accessible.checked: tabButton.selected
                                    Accessible.onPressAction: root.selectLayer(modelData.index)
                                }
                            }
                        }

                        KeymapView {
                            visible: root.keymap.ok === true && root.keymap.geometry !== null && root.keymap.geometry !== undefined
                            width: parent.width
                        }

                        Text {
                            visible: text !== ""
                            width: parent.width
                            text: {
                                if (!root.keymap.configured)
                                    return "Set keymapPath in this widget's settings to a keymap-drawer YAML file to see layer names and key layouts.";
                                if (!root.keymap.ok)
                                    return "Could not load the keymap (" + (root.keymap.error || "unknown") + (root.keymap.detail ? ": " + root.keymap.detail : "") + ").";
                                if (root.keymap.mismatchedLayers && root.keymap.mismatchedLayers.length > 0)
                                    return "Key count differs from the layout for: " + root.keymap.mismatchedLayers.join(", ");
                                return "";
                            }
                            color: Commons.Color.muted
                            font.family: root.fontFamily
                            font.pixelSize: root.captionFontSize
                            wrapMode: Text.WordWrap
                            Accessible.role: Accessible.StaticText
                            Accessible.name: text
                        }
                    }

                    Text {
                        visible: text !== ""
                        width: parent.width
                        text: {
                            if (!root.hasService)
                                return "";
                            if (root.service.bridgePhase === "failed")
                                return "Bluetooth bridge stopped: " + root.service.bridgeError;
                            if (root.service.bridgePhase === "restarting")
                                return "Bluetooth bridge exited; restarting. " + root.service.lastBridgeLog;
                            return "";
                        }
                        color: Commons.Color.urgent
                        font.family: root.fontFamily
                        font.pixelSize: root.captionFontSize
                        wrapMode: Text.WordWrap
                        Accessible.role: Accessible.StaticText
                        Accessible.name: text
                    }
                }
            }
        }
    }

    component InfoRow: Item {
        id: infoRow

        required property string label
        required property string value
        property color valueColor: root.barForeground
        readonly property int columnSpacing: Commons.Style.space(8)
        readonly property bool stacked: Model.shouldStackInfoRow(width, infoLabel.implicitWidth, infoValue.implicitWidth, columnSpacing)

        width: parent ? parent.width : implicitWidth
        implicitHeight: stacked ? infoLabel.implicitHeight + columnSpacing + infoValue.implicitHeight : Math.max(infoLabel.implicitHeight, infoValue.implicitHeight)
        Accessible.role: Accessible.StaticText
        Accessible.name: label + ", " + value

        Text {
            id: infoLabel
            width: infoRow.stacked ? infoRow.width : Math.min(implicitWidth, Math.max(0, infoRow.width - infoRow.columnSpacing))
            text: infoRow.label
            textFormat: Text.PlainText
            color: root.barForeground
            font.family: root.fontFamily
            font.pixelSize: root.bodyFontSize
            elide: Text.ElideRight
            maximumLineCount: 1
            Accessible.ignored: true
        }

        Text {
            id: infoValue
            x: infoRow.stacked ? 0 : infoLabel.width + infoRow.columnSpacing
            y: infoRow.stacked ? infoLabel.implicitHeight + infoRow.columnSpacing : 0
            width: infoRow.stacked ? infoRow.width : Math.max(0, infoRow.width - x)
            text: infoRow.value
            textFormat: Text.PlainText
            color: infoRow.valueColor
            font.family: root.fontFamily
            font.pixelSize: root.bodyFontSize
            font.bold: true
            horizontalAlignment: infoRow.stacked ? Text.AlignLeft : Text.AlignRight
            elide: Text.ElideRight
            maximumLineCount: 1
            Accessible.ignored: true
        }
    }

    component BatteryRow: Column {
        id: batteryRow

        required property string label
        required property var half
        required property bool linked
        readonly property var percent: half.percent
        readonly property string tone: Model.batteryTone(percent, linked)
        readonly property var points: half.trend && half.trend.points ? half.trend.points : []

        width: parent ? parent.width : implicitWidth
        spacing: Commons.Style.space(4)
        opacity: linked ? 1 : 0.55
        Accessible.role: Accessible.StaticText
        Accessible.name: label + " half battery, " + Model.percentText(percent) + ". " + Model.trendText(half.trend, percent)

        Item {
            width: parent.width
            implicitHeight: Math.max(batteryLabel.implicitHeight, batteryValue.implicitHeight)

            Text {
                id: batteryLabel
                text: batteryRow.label
                color: root.barForeground
                font.family: root.fontFamily
                font.pixelSize: root.bodyFontSize
                Accessible.ignored: true
            }

            Row {
                anchors.right: batteryValue.left
                anchors.rightMargin: Commons.Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Math.max(1, Commons.Style.space(2))
                visible: batteryRow.points.length > 1

                Repeater {
                    model: batteryRow.points

                    delegate: Rectangle {
                        required property var modelData
                        width: Math.max(2, Commons.Style.space(3))
                        height: Math.max(2, Commons.Style.space(16) * Number(modelData) / 100)
                        anchors.bottom: parent.bottom
                        color: Number(modelData) <= Model.LOW_BATTERY ? Commons.Color.urgent : Commons.Color.muted
                    }
                }
            }

            Text {
                id: batteryValue
                anchors.right: parent.right
                text: Model.percentText(batteryRow.percent)
                color: root.toneColor(batteryRow.tone === "muted" ? "normal" : batteryRow.tone)
                font.family: root.fontFamily
                font.pixelSize: root.bodyFontSize
                font.bold: true
                Accessible.ignored: true
            }
        }

        Text {
            width: parent.width
            text: {
                if (!batteryRow.linked)
                    return Model.connected(root.kbd) ? "Disconnected" : "—";
                if (!Model.validPercent(batteryRow.percent))
                    return "Unavailable";
                var parts = [Model.trendText(batteryRow.half.trend, batteryRow.percent), Model.sourceText(batteryRow.half.source)];
                return parts.filter(function (part) {
                    return part !== "";
                }).join(" · ");
            }
            color: Commons.Color.muted
            font.family: root.fontFamily
            font.pixelSize: root.captionFontSize
            elide: Text.ElideRight
            Accessible.ignored: true
        }
    }

    component KeymapView: Item {
        id: keymapView

        readonly property var geometry: root.keymap.geometry
        readonly property real unit: Model.keyUnit(geometry, width, Commons.Style.space(56))
        readonly property real gap: Math.max(2, unit * 0.08)
        readonly property real offsetX: geometry ? (width - geometry.width * unit) / 2 : 0

        implicitHeight: geometry ? geometry.height * unit : 0
        height: implicitHeight
        Accessible.role: Accessible.Grouping
        Accessible.name: "Keys on layer " + Model.layerName(root.keymap, root.viewedLayer)

        Repeater {
            model: keymapView.geometry ? keymapView.geometry.keys : []

            delegate: Item {
                id: keyItem
                required property var modelData
                required property int index
                readonly property var legend: Model.keyAt(root.keymap, root.viewedLayer, index)
                readonly property string kind: legend ? String(legend.type || "") : ""
                readonly property real unit: keymapView.unit

                x: keymapView.offsetX + modelData.x * unit + keymapView.gap / 2
                y: modelData.y * unit + keymapView.gap / 2
                width: modelData.w * unit - keymapView.gap
                height: modelData.h * unit - keymapView.gap
                transform: Rotation {
                    angle: Number(keyItem.modelData.r) || 0
                    origin.x: keyItem.modelData.rx === null || keyItem.modelData.rx === undefined ? keyItem.width / 2 : (keyItem.modelData.rx - keyItem.modelData.x) * keyItem.unit
                    origin.y: keyItem.modelData.ry === null || keyItem.modelData.ry === undefined ? keyItem.height / 2 : (keyItem.modelData.ry - keyItem.modelData.y) * keyItem.unit
                }

                Rectangle {
                    anchors.fill: parent
                    radius: Math.max(2, keyItem.unit * 0.12)
                    color: keyItem.kind === "held" ? Commons.Util.alpha(Commons.Color.accent, 0.3) : "transparent"
                    border.width: 1
                    border.color: Commons.Util.alpha(root.barForeground, keyItem.kind === "trans" ? 0.12 : 0.3)
                }

                Text {
                    anchors.top: parent.top
                    anchors.topMargin: 1
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 4
                    visible: text !== ""
                    text: keyItem.legend ? keyItem.legend.s : ""
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                    color: Commons.Color.muted
                    font.family: root.fontFamily
                    font.pixelSize: Math.max(7, keyItem.unit * 0.2)
                    elide: Text.ElideRight
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 4
                    text: keyItem.legend ? keyItem.legend.t : ""
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                    color: keyItem.kind === "trans" ? Commons.Util.alpha(root.barForeground, 0.35) : (keyItem.kind === "held" ? Commons.Color.accent : root.barForeground)
                    font.family: root.fontFamily
                    font.pixelSize: Math.max(8, keyItem.unit * (keyItem.legend && keyItem.legend.glyph ? 0.36 : 0.28))
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: 6
                    elide: Text.ElideRight
                }

                Text {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 1
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 4
                    visible: text !== ""
                    text: keyItem.legend ? keyItem.legend.h : ""
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter
                    color: Commons.Color.muted
                    font.family: root.fontFamily
                    font.pixelSize: Math.max(7, keyItem.unit * 0.2)
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: 6
                    elide: Text.ElideRight
                }
            }
        }
    }
}
