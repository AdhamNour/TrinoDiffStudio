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

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        // Top Toolbar
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
                Layout.fillHeight: true
                color: Theme.border
            }

            CheckBox {
                checked: root.autoScroll
                text: "Auto-scroll"
                onToggled: root.autoScroll = checked
            }

            AppButton {
                text: "Clear Logs"
                variant: "ghost"
                onClicked: backend.clearLogs()
            }
        }

        // Search Filter
        AppTextField {
            id: logSearchInput
            Layout.fillWidth: true
            placeholderText: "🔍 Filter logs by text or keyword..."
            onTextChanged: root.searchFilter = logSearchInput.text.toLowerCase().trim()
        }

        // Console Log Area
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.bgDark
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            ScrollView {
                id: scrollView
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                clip: true

                ListView {
                    id: logListView
                    width: parent.width
                    spacing: 2
                    model: getFilteredLogs()

                    delegate: Rectangle {
                        width: logListView.width
                        implicitHeight: logRow.implicitHeight + 6
                        color: index % 2 === 0 ? "transparent" : "#080C14"
                        radius: 2

                        RowLayout {
                            id: logRow
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            spacing: Theme.spacingSm

                            Text {
                                text: modelData.timestamp || ""
                                font.family: Theme.monoFontFamily
                                font.pixelSize: Theme.fontSizeXs
                                color: Theme.textMuted
                            }

                            Rectangle {
                                implicitWidth: 64
                                implicitHeight: 18
                                radius: 3
                                color: getTagBg(modelData.level)

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
                                Layout.fillWidth: true
                                text: modelData.message || ""
                                font.family: Theme.monoFontFamily
                                font.pixelSize: Theme.fontSizeXs
                                color: getMessageColor(modelData.level)
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                    }

                    onCountChanged: {
                        if (root.autoScroll && count > 0) {
                            logListView.positionViewAtEnd()
                        }
                    }
                }
            }
        }
    }

    function getFilteredLogs() {
        var result = []
        for (var i = 0; i < backend.logs.length; i++) {
            var l = backend.logs[i]
            if (root.levelFilter !== "ALL") {
                if (root.levelFilter === "WARN" && l.level !== "WARN" && l.level !== "WARNING") continue
                if (root.levelFilter !== "WARN" && l.level !== root.levelFilter) continue
            }
            if (root.searchFilter && l.message.toLowerCase().indexOf(root.searchFilter) === -1) continue
            result.push(l)
        }
        return result
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
