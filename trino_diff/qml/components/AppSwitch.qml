import QtQuick
import QtQuick.Controls.Basic
import ".."

Switch {
    id: control

    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeSm
    font.weight: Font.Medium
    spacing: Theme.spacingSm
    padding: 0

    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding,
                             implicitIndicatorHeight + topPadding + bottomPadding)

    indicator: Rectangle {
        implicitWidth: 42
        implicitHeight: 24
        x: control.leftPadding
        y: control.topPadding + Math.round((control.availableHeight - height) / 2)
        radius: 12

        color: !control.enabled ? Theme.borderSubtle
             : control.checked ? (control.down ? Theme.primaryActive : (control.hovered ? Theme.primaryHover : Theme.primary))
             : (control.down ? Theme.bgInputHover : (control.hovered ? Theme.borderHover : Theme.bgInput))

        border.color: !control.enabled ? Theme.borderSubtle
                    : control.checked ? (control.down ? Theme.primaryActive : (control.hovered ? Theme.primaryHover : Theme.primary))
                    : (control.hovered ? Theme.borderHover : Theme.border)
        border.width: 1.5

        Behavior on color        { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }

        // Thumb knob
        Rectangle {
            id: thumb
            width: 18
            height: 18
            radius: 9
            color: control.enabled ? "#FFFFFF" : Theme.textDisabled
            anchors.verticalCenter: parent.verticalCenter
            x: control.checked ? (parent.width - width - 3) : 3
            scale: control.down ? 0.92 : 1.0

            Behavior on x     { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
            Behavior on scale { NumberAnimation { duration: 100 } }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator && control.text !== "" ? (control.indicator.width + control.spacing) : 0
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.textDisabled
             : (control.checked ? Theme.textPrimary : Theme.textSecondary)
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        visible: control.text !== ""

        Behavior on color { ColorAnimation { duration: 120 } }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        acceptedButtons: Qt.NoButton
    }
}
