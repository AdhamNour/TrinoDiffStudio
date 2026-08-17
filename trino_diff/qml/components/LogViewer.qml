import QtQuick
import QtQuick.Controls.Basic
import ".."

// LogViewer lives inside components/ so:
//   ".."         → qml/       (Theme singleton)
//   "."          → same folder (components/) - no sub-imports needed here

Rectangle {
    id: root

    property var logsModel: []
    property bool autoScroll: true

    color: Theme.bgDark
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1

    Column {
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        spacing: Theme.spacingSm

        // Toolbar row
        Row {
            width: parent.width
            height: 32
            spacing: Theme.spacingSm

            Text {
                text: "Execution Logs"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                font.weight: Font.DemiBold
                color: Theme.textSecondary
                anchors.verticalCenter: parent.verticalCenter
            }

            Item { width: parent.width - 130; height: 1 }

            // Inline clear button so we don't need to import AppButton
            Rectangle {
                width: clearBtnLabel.implicitWidth + 16
                height: 26
                radius: Theme.radiusSm
                color: clearBtnMa.containsMouse ? Theme.bgInput : "transparent"
                anchors.verticalCenter: parent.verticalCenter

                Text {
                    id: clearBtnLabel
                    anchors.centerIn: parent
                    text: "Clear"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSm
                    color: clearBtnMa.containsMouse ? Theme.textPrimary : Theme.textSecondary
                }

                MouseArea {
                    id: clearBtnMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.clearLogs()
                }
            }
        }

        // Log list
        ScrollView {
            id: scrollView
            width: parent.width
            height: parent.height - 40
            clip: true

            ListView {
                id: logList
                width: scrollView.width
                model: root.logsModel
                spacing: 2

                delegate: Rectangle {
                    width: logList.width
                    implicitHeight: logContentRow.implicitHeight + 6
                    color: index % 2 === 0 ? "transparent" : "#080C14"
                    radius: 2

                    Row {
                        id: logContentRow
                        width: parent.width - 12
                        x: 6
                        y: 3
                        spacing: Theme.spacingSm

                        Text {
                            text: modelData.timestamp || ""
                            font.family: Theme.monoFontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Rectangle {
                            width: 56
                            height: 16
                            radius: 3
                            color: getTagBg(modelData.level)
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                anchors.centerIn: parent
                                text: modelData.level || "INFO"
                                font.family: Theme.monoFontFamily
                                font.pixelSize: 10
                                font.weight: Font.Bold
                                color: getTagColor(modelData.level)
                            }
                        }

                        Text {
                            text: modelData.message || ""
                            font.family: Theme.monoFontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: getMessageColor(modelData.level)
                            wrapMode: Text.WrapAnywhere
                            width: logContentRow.width - 130
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                onCountChanged: {
                    if (root.autoScroll && count > 0)
                        logList.positionViewAtEnd()
                }
            }
        }
    }

    function getTagColor(level) {
        if (level === "SUCCESS") return "#34D399"
        if (level === "ERROR")   return "#F87171"
        if (level === "WARN" || level === "WARNING") return "#FBBF24"
        return "#60A5FA"
    }

    function getTagBg(level) {
        if (level === "SUCCESS") return "#064E3B"
        if (level === "ERROR")   return "#7F1D1D"
        if (level === "WARN" || level === "WARNING") return "#78350F"
        return "#1E3A8A"
    }

    function getMessageColor(level) {
        if (level === "SUCCESS") return "#D1FAE5"
        if (level === "ERROR")   return "#FEE2E2"
        if (level === "WARN" || level === "WARNING") return "#FEF3C7"
        return Theme.textPrimary
    }
}
