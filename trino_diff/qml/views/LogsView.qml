import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    property string searchFilter: ""
    property string levelFilter: "ALL"
    property bool autoScroll: true

    // Fully reactive filtered logs property bound to backend.logs, levelFilter, and searchFilter
    property var filteredLogs: {
        var raw = backend.logs || []
        var lvl = root.levelFilter
        var srch = root.searchFilter
        var result = []
        for (var i = 0; i < raw.length; i++) {
            var l = raw[i]
            if (lvl !== "ALL") {
                if (lvl === "WARN" && l.level !== "WARN" && l.level !== "WARNING") continue
                if (lvl !== "WARN" && l.level !== lvl) continue
            }
            if (srch && (!l.message || l.message.toLowerCase().indexOf(srch) === -1)) continue
            result.push(l)
        }
        return result
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        // Top Toolbar Row
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            ColumnLayout {
                spacing: 2
                Text {
                    text: "Execution Console & Logs"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeLg
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                }
                Text {
                    text: "Real-time streaming logs from Trino SQL generation and batch processing."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textMuted
                }
            }

            Item { Layout.fillWidth: true }

            Row {
                spacing: 4
                Layout.alignment: Qt.AlignVCenter

                AppButton {
                    text: "All"
                    variant: root.levelFilter === "ALL" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.levelFilter = "ALL"
                }
                AppButton {
                    text: "Info"
                    variant: root.levelFilter === "INFO" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.levelFilter = "INFO"
                }
                AppButton {
                    text: "Success"
                    variant: root.levelFilter === "SUCCESS" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.levelFilter = "SUCCESS"
                }
                AppButton {
                    text: "Warnings"
                    variant: root.levelFilter === "WARN" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.levelFilter = "WARN"
                }
                AppButton {
                    text: "Errors"
                    variant: root.levelFilter === "ERROR" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.levelFilter = "ERROR"
                }
            }

            Rectangle {
                width: 1
                height: 24
                Layout.alignment: Qt.AlignVCenter
                color: Theme.border
            }

            AppCheckBox {
                checked: root.autoScroll
                text: "Auto-scroll"
                Layout.alignment: Qt.AlignVCenter
                onToggled: root.autoScroll = checked
            }

            AppButton {
                text: "Clear Logs"
                variant: "ghost"
                implicitHeight: 32
                Layout.alignment: Qt.AlignVCenter
                onClicked: backend.clearLogs()
            }
        }

        // Search Filter Bar
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            AppTextField {
                id: logSearchInput
                Layout.fillWidth: true
                placeholderText: "🔍 Filter logs by text or keyword..."
                onTextChanged: root.searchFilter = logSearchInput.text.toLowerCase().trim()
            }

            Text {
                text: root.filteredLogs.length + " log entry(ies)"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textMuted
                Layout.alignment: Qt.AlignVCenter
            }
        }

        // Console Log Area
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.bgDark
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1
            clip: true

            ListView {
                id: logListView
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                clip: true
                spacing: 4
                model: root.filteredLogs

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                delegate: Rectangle {
                    width: logListView.width - 12
                    implicitHeight: logRow.implicitHeight + 8
                    color: index % 2 === 0 ? "transparent" : "#080C14"
                    radius: 3

                    RowLayout {
                        id: logRow
                        width: parent.width - 16
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: Theme.spacingSm

                        Text {
                            text: modelData.timestamp || ""
                            font.family: Theme.monoFontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                            Layout.alignment: Qt.AlignVCenter
                        }

                        Rectangle {
                            implicitWidth: 64
                            implicitHeight: 18
                            radius: 3
                            color: root.getTagBg(modelData.level)
                            Layout.alignment: Qt.AlignVCenter

                            Text {
                                anchors.centerIn: parent
                                text: modelData.level || "INFO"
                                font.family: Theme.monoFontFamily
                                font.pixelSize: 10
                                font.weight: Font.Bold
                                color: root.getTagColor(modelData.level)
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.message || ""
                            font.family: Theme.monoFontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: root.getMessageColor(modelData.level)
                            wrapMode: Text.WrapAnywhere
                            Layout.alignment: Qt.AlignVCenter
                        }
                    }
                }

                onCountChanged: {
                    if (root.autoScroll && count > 0) {
                        logListView.positionViewAtEnd()
                    }
                }
            }

            // Empty state overlay
            Column {
                anchors.centerIn: parent
                spacing: Theme.spacingSm
                visible: root.filteredLogs.length === 0

                Text {
                    text: root.searchFilter !== "" ? "🔍 No logs match your filter" : "📝 Execution Console Ready"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBase
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: root.searchFilter !== ""
                        ? "Try clearing the search query or changing the log level filter."
                        : "Real-time logs from diff generation, batch runs, and connection checks will appear here."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textMuted
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }

    function getTagColor(level) {
        if (level === "SUCCESS") return "#34D399"
        if (level === "ERROR") return "#F87171"
        if (level === "WARN" || level === "WARNING") return "#FBBF24"
        return "#60A5FA"
    }

    function getTagBg(level) {
        if (level === "SUCCESS") return "#064E3B"
        if (level === "ERROR") return "#7F1D1D"
        if (level === "WARN" || level === "WARNING") return "#78350F"
        return "#1E3A8A"
    }

    function getMessageColor(level) {
        if (level === "SUCCESS") return "#D1FAE5"
        if (level === "ERROR") return "#FEE2E2"
        if (level === "WARN" || level === "WARNING") return "#FEF3C7"
        return Theme.textPrimary
    }
}
