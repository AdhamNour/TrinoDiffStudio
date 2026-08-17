import QtQuick
import QtQuick.Controls.Basic
import ".."

Item {
    id: root

    property string label: ""
    property alias model: combo.model
    property alias currentIndex: combo.currentIndex
    property alias currentText: combo.currentText
    property alias displayText: combo.displayText

    signal activated(int index)

    // Do NOT default to parent.width — let RowLayout/ColumnLayout control sizing
    implicitWidth: 200
    implicitHeight: (label !== "" ? (labelText.implicitHeight + 4) : 0) + combo.implicitHeight

    Column {
        anchors.fill: parent
        spacing: 4

        Text {
            id: labelText
            visible: root.label !== ""
            text: root.label
            width: parent.width
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSm
            font.weight: Font.Medium
            color: Theme.textSecondary
            elide: Text.ElideRight
        }

        ComboBox {
            id: combo
            width: parent.width
            implicitHeight: 38

            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBase

            onActivated: (index) => root.activated(index)

            delegate: ItemDelegate {
                id: itemDel
                required property string modelData
                required property int index
                width: combo.width
                implicitHeight: 36
                highlighted: combo.highlightedIndex === index

                contentItem: Text {
                    text: itemDel.modelData
                    color: itemDel.highlighted ? Theme.primary : Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBase
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: Theme.spacingMd
                }

                background: Rectangle {
                    color: itemDel.highlighted ? Theme.bgCardHover : "transparent"
                }
            }

            contentItem: Text {
                leftPadding: Theme.spacingMd
                rightPadding: combo.indicator ? (combo.indicator.width + Theme.spacingSm) : Theme.spacingMd
                text: combo.displayText
                font: combo.font
                color: Theme.textPrimary
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }

            indicator: Text {
                x: combo.width - width - Theme.spacingMd
                y: (combo.height - height) / 2
                text: "▾"
                font.pixelSize: 12
                color: combo.activeFocus ? Theme.textSecondary : Theme.textMuted
            }

            background: Rectangle {
                implicitHeight: 38
                radius: Theme.radiusSm
                color: combo.activeFocus ? Theme.bgInputHover
                     : (combo.hovered    ? Theme.bgInputHover : Theme.bgInput)
                border.color: combo.activeFocus ? Theme.borderFocus
                            : (combo.hovered    ? Theme.borderHover : Theme.border)
                border.width: 1

                Behavior on color        { ColorAnimation { duration: 100 } }
                Behavior on border.color { ColorAnimation { duration: 100 } }
            }

            popup: Popup {
                y: combo.height + 4
                width: combo.width
                implicitHeight: Math.min(listView.contentHeight + 8, 240)
                padding: 4

                contentItem: ListView {
                    id: listView
                    clip: true
                    implicitHeight: contentHeight
                    model: combo.popup.visible ? combo.delegateModel : null
                    currentIndex: combo.highlightedIndex
                    ScrollIndicator.vertical: ScrollIndicator { }
                }

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: Theme.bgCard
                    border.color: Theme.border
                    border.width: 1

                    // Subtle drop shadow effect via layered rectangle
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: -1
                        radius: parent.radius + 1
                        color: "transparent"
                        border.color: "#0A000000"
                        border.width: 2
                        z: -1
                    }
                }
            }
        }
    }
}
