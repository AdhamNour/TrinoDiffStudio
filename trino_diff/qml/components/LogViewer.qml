import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
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

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingSm
        spacing: Theme.spacingSm

        // Toolbar row
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            spacing: Theme.spacingSm

            Text {
                text: "Execution Logs"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                font.weight: Font.DemiBold
                color: Theme.textSecondary
                Layout.alignment: Qt.AlignVCenter
            }

            Item { Layout.fillWidth: true }

            // Inline clear button
            Rectangle {
                implicitWidth: clearBtnLabel.implicitWidth + 16
                implicitHeight: 26
                radius: Theme.radiusSm
                color: clearBtnMa.containsMouse ? Theme.bgInput : "transparent"
                Layout.alignment: Qt.AlignVCenter

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
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ListView {
                id: logList
                width: scrollView.availableWidth
                model: root.logsModel
                spacing: 2

                delegate: Rectangle {
                    width: logList.width
                    implicitHeight: logContentRow.implicitHeight + 8
                    color: index % 2 === 0 ? "transparent" : Theme.bgDark
                    radius: 2

                    RowLayout {
                        id: logContentRow
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        anchors.topMargin: 4
                        anchors.bottomMargin: 4
                        spacing: Theme.spacingSm

                        Text {
                            text: modelData.timestamp || ""
                            font.family: Theme.monoFontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                            Layout.alignment: Qt.AlignTop
                        }

                        Rectangle {
                            implicitWidth: 56
                            implicitHeight: 18
                            radius: 3
                            color: getTagBg(modelData.level)
                            Layout.alignment: Qt.AlignTop

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
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
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
        return "#FDE047"
    }

    function getTagBg(level) {
        if (level === "SUCCESS") return "#064E3B"
        if (level === "ERROR")   return "#7F1D1D"
        if (level === "WARN" || level === "WARNING") return "#78350F"
        return "#451A03"
    }

    function getMessageColor(level) {
        if (level === "SUCCESS") return "#D1FAE5"
        if (level === "ERROR")   return "#FEE2E2"
        if (level === "WARN" || level === "WARNING") return "#FEF3C7"
        return Theme.textPrimary
    }
}
