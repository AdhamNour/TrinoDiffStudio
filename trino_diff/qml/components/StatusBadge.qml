import QtQuick
import ".."

Rectangle {
    id: root

    property string status: "Ready"  // "Ready", "Running", "Completed", "Error", "Pending"

    implicitWidth: badgeRow.implicitWidth + Theme.spacingMd * 2
    implicitHeight: 24
    radius: Theme.radiusFull
    color: getBgColor()
    border.color: getBorderColor()
    border.width: 1

    Row {
        id: badgeRow
        spacing: 6
        anchors.centerIn: parent

        Rectangle {
            width: 6
            height: 6
            radius: 3
            color: getDotColor()
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: root.status
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeXs
            font.weight: Font.Medium
            color: getTextColor()
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    function getDotColor() {
        if (status === "Completed" || status === "Success") return Theme.accentEmerald
        if (status === "Running") return Theme.primary
        if (status === "Error" || status === "Failed") return Theme.accentRose
        if (status === "Warning") return Theme.accentAmber
        return Theme.textMuted
    }

    function getBgColor() {
        if (status === "Completed" || status === "Success") return "#064E3B"
        if (status === "Running") return "#451A03"
        if (status === "Error" || status === "Failed") return "#7F1D1D"
        if (status === "Warning") return "#78350F"
        return Theme.bgCardHover
    }

    function getBorderColor() {
        if (status === "Completed" || status === "Success") return "#059669"
        if (status === "Running") return Theme.primary
        if (status === "Error" || status === "Failed") return "#DC2626"
        if (status === "Warning") return "#D97706"
        return Theme.borderSubtle
    }

    function getTextColor() {
        if (status === "Completed" || status === "Success") return "#A7F3D0"
        if (status === "Running") return "#FEF3C7"
        if (status === "Error" || status === "Failed") return "#FECDD3"
        if (status === "Warning") return "#FDE68A"
        return Theme.textSecondary
    }
}
