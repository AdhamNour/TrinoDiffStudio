import QtQuick
import QtQuick.Controls.Basic
import ".."

CheckBox {
    id: control

    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeSm
    spacing: Theme.spacingSm
    padding: 0

    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             implicitContentHeight + topPadding + bottomPadding,
                             implicitIndicatorHeight + topPadding + bottomPadding)

    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: control.topPadding + Math.round((control.availableHeight - height) / 2)
        radius: Theme.radiusSm - 2
        color: !control.enabled ? Theme.bgCard
             : control.checked ? (control.down ? Theme.primaryActive : (control.hovered ? Theme.primaryHover : Theme.primary))
             : (control.down ? Theme.bgInputHover : (control.hovered ? Theme.bgInputHover : Theme.bgInput))
        border.color: !control.enabled ? Theme.borderSubtle
                    : control.checked ? (control.down ? Theme.primaryActive : (control.hovered ? Theme.primaryHover : Theme.primary))
                    : (control.hovered ? Theme.borderHover : Theme.border)
        border.width: 1.5

        Behavior on color        { ColorAnimation { duration: 120 } }
        Behavior on border.color { ColorAnimation { duration: 120 } }

        Text {
            anchors.centerIn: parent
            text: "✓"
            font.family: Theme.fontFamily
            font.pixelSize: 11
            font.weight: Font.Bold
            color: Theme.primaryText
            visible: control.checked
            scale: control.checked ? 1.0 : 0.4
            opacity: control.checked ? 1.0 : 0.0

            Behavior on scale   { NumberAnimation { duration: 120; easing.type: Easing.OutBack } }
            Behavior on opacity { NumberAnimation { duration: 100 } }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator && control.text !== "" ? (control.indicator.width + control.spacing) : 0
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.textDisabled
             : (control.hovered || control.checked ? Theme.textPrimary : Theme.textSecondary)
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
