import QtQuick
import QtQuick.Controls.Basic
import ".."

Item {
    id: root

    property string label: ""
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property alias readOnly: input.readOnly
    property alias echoMode: input.echoMode

    signal editingFinished()
    signal accepted()

    function forceActiveFocus() { input.forceActiveFocus() }
    function selectAll() { input.selectAll() }

    implicitWidth: 240
    implicitHeight: labelText.visible ? (labelText.implicitHeight + 4 + inputRect.implicitHeight)
                                      : inputRect.implicitHeight

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

        Rectangle {
            id: inputRect
            width: parent.width
            implicitHeight: 38
            radius: Theme.radiusSm
            color: input.activeFocus ? Theme.bgInputHover : Theme.bgInput
            border.color: input.activeFocus ? Theme.borderFocus
                        : (input.hovered ? Theme.borderHover : Theme.border)
            border.width: 1

            Behavior on border.color { ColorAnimation { duration: 120 } }
            Behavior on color        { ColorAnimation { duration: 120 } }

            TextField {
                id: input
                anchors.fill: parent
                anchors.leftMargin: Theme.spacingMd
                anchors.rightMargin: Theme.spacingMd
                verticalAlignment: TextInput.AlignVCenter
                hoverEnabled: true

                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBase
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                selectionColor: Theme.primary
                selectedTextColor: "#FFFFFF"
                background: null

                onEditingFinished: root.editingFinished()
                onAccepted: root.accepted()
            }
        }
    }
}
