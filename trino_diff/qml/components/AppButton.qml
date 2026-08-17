import QtQuick
import QtQuick.Controls.Basic
import ".."

Button {
    id: root

    property string variant: "primary"  // "primary", "secondary", "danger", "success", "ghost"
    property string iconName: ""
    property int customRadius: Theme.radiusSm
    property int customPaddingH: Theme.spacingMd
    property int customPaddingV: Theme.spacingSm
    property bool fullWidth: false

    implicitWidth: fullWidth ? parent.width : (contentRow.implicitWidth + customPaddingH * 2)
    implicitHeight: 36

    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeBase
    font.weight: Font.Medium

    contentItem: Row {
        id: contentRow
        spacing: Theme.spacingSm
        anchors.centerIn: parent

        Text {
            visible: root.iconName !== ""
            text: root.iconName
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeMd
            color: root.getTextColor()
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: root.text
            font: root.font
            color: root.getTextColor()
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    background: Rectangle {
        implicitHeight: root.implicitHeight
        radius: root.customRadius
        color: root.getBgColor()
        border.color: root.getBorderColor()
        border.width: (root.variant === "secondary" || root.variant === "ghost") ? 1 : 0

        Behavior on color {
            ColorAnimation { duration: 120 }
        }
        Behavior on border.color {
            ColorAnimation { duration: 120 }
        }
    }

    function getBgColor() {
        if (!root.enabled) return Theme.borderSubtle
        if (root.variant === "primary") {
            if (root.down) return Theme.primaryActive
            if (root.hovered) return Theme.primaryHover
            return Theme.primary
        }
        if (root.variant === "success") {
            if (root.down) return "#059669"
            if (root.hovered) return "#10B981"
            return "#059669"
        }
        if (root.variant === "danger") {
            if (root.down) return "#B91C1C"
            if (root.hovered) return "#DC2626"
            return "#EF4444"
        }
        if (root.variant === "secondary") {
            if (root.down) return Theme.bgCardHover
            if (root.hovered) return Theme.bgInputHover
            return Theme.bgInput
        }
        if (root.variant === "ghost") {
            if (root.down) return Theme.bgCardHover
            if (root.hovered) return Theme.bgInput
            return "transparent"
        }
        return Theme.primary
    }

    function getTextColor() {
        if (!root.enabled) return Theme.textDisabled
        if (root.variant === "secondary" || root.variant === "ghost") {
            return root.hovered ? Theme.textPrimary : Theme.textSecondary
        }
        return "#FFFFFF"
    }

    function getBorderColor() {
        if (!root.enabled) return "transparent"
        if (root.variant === "secondary") {
            return root.hovered ? Theme.borderHover : Theme.border
        }
        if (root.variant === "ghost") {
            return root.hovered ? Theme.border : "transparent"
        }
        return "transparent"
    }
}
