import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

Dialog {
    id: root

    property string tableName: ""
    property string errorMessage: ""
    property string failedQuery: ""
    property string explanationText: ""
    property string suggestedSql: ""
    property bool   isLoading: false
    property string activeTab: "diagnosis" // "diagnosis" | "sql" | "error"

    title: ""
    modal: true
    anchors.centerIn: Overlay.overlay
    width:  Math.min(Overlay.overlay ? Overlay.overlay.width  * 0.88 : 940, 960)
    height: Math.min(Overlay.overlay ? Overlay.overlay.height * 0.88 : 720, 740)
    padding: 0

    background: Rectangle {
        color: Theme.bgCard
        radius: Theme.radiusMd
        border.color: "#6D28D9" // Purple AI accent
        border.width: 1
    }

    contentItem: Item {
        anchors.fill: parent

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // ── Header Row ──────────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Rectangle {
                    width: 38; height: 38
                    radius: Theme.radiusSm
                    color: "#5B21B6"

                    Text {
                        anchors.centerIn: parent
                        text: "🤖"
                        font.pixelSize: 20
                    }
                }

                Column {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: "AI Error Diagnosis & Fix Suggestion"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeLg
                        font.weight: Font.Bold
                        color: Theme.textPrimary
                    }

                    Text {
                        text: "Powered by Qwen 2.5 Coder (1.5B)  •  Table: " + root.tableName
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeXs
                        color: Theme.accentCyan
                    }
                }

                AppButton {
                    text: "✕ Close"
                    variant: "ghost"
                    implicitHeight: 32
                    onClicked: root.close()
                }
            }

            // ── Tab Bar ──────────────────────────────────────────────────────
            Row {
                spacing: 6
                Layout.fillWidth: true

                AppButton {
                    text: "💡 AI Explanation & Fix"
                    variant: root.activeTab === "diagnosis" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.activeTab = "diagnosis"
                }

                AppButton {
                    text: "⚠️ Trino Error Details"
                    variant: root.activeTab === "error" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.activeTab = "error"
                }

                AppButton {
                    text: "🛠️ Corrected SQL"
                    variant: root.activeTab === "sql" ? "primary" : "ghost"
                    implicitHeight: 32
                    visible: root.suggestedSql !== ""
                    onClicked: root.activeTab = "sql"
                }

                Item { width: 16 }

                AppButton {
                    text: root.isLoading ? "Analyzing…" : "⟳ Re-analyze"
                    variant: "secondary"
                    implicitHeight: 32
                    enabled: !root.isLoading && root.tableName !== ""
                    onClicked: backend.explainTableError(root.tableName)
                }
            }

            // ── Content Area ────────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.bgDark
                radius: Theme.radiusSm
                border.color: Theme.border
                border.width: 1
                clip: true

                // Loading State
                Column {
                    anchors.centerIn: parent
                    spacing: Theme.spacingMd
                    visible: root.isLoading

                    BusyIndicator {
                        running: root.isLoading
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Text {
                        text: "Qwen 2.5-Coder is analyzing the Trino error..."
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBase
                        font.weight: Font.DemiBold
                        color: Theme.accentCyan
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Text {
                        text: "Diagnosing root cause and generating corrected Trino SQL query."
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeXs
                        color: Theme.textMuted
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }

                // Tab 1: AI Diagnosis View
                ScrollView {
                    id: diagScrollView
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    clip: true
                    visible: !root.isLoading && root.activeTab === "diagnosis"

                    Column {
                        width: diagScrollView.width - 24
                        spacing: Theme.spacingMd

                        // Error summary banner
                        Rectangle {
                            width: parent.width
                            implicitHeight: errBannerCol.implicitHeight + 16
                            color: "#3B1219"
                            radius: Theme.radiusSm
                            border.color: "#991B1B"
                            border.width: 1

                            Column {
                                id: errBannerCol
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 4

                                Text {
                                    text: "⚠️ Trino Error Summary"
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeXs
                                    font.weight: Font.Bold
                                    color: "#FCA5A5"
                                }
                                Text {
                                    text: root.errorMessage || "No error details available."
                                    font.family: Theme.monoFontFamily
                                    font.pixelSize: Theme.fontSizeXs
                                    color: "#FEE2E2"
                                    wrapMode: Text.WrapAnywhere
                                    width: parent.width
                                }
                            }
                        }

                        // AI Output
                        TextArea {
                            width: parent.width
                            text: root.explanationText || "Click 'Re-analyze' to generate AI diagnosis."
                            readOnly: true
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBase
                            color: Theme.textPrimary
                            selectedTextColor: "#FFFFFF"
                            selectionColor: Theme.primary
                            wrapMode: TextEdit.Wrap
                            background: null
                        }
                    }
                }

                // Tab 2: Trino Error & Failed Query View
                ScrollView {
                    id: errScrollView
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    clip: true
                    visible: !root.isLoading && root.activeTab === "error"

                    Column {
                        width: errScrollView.width - 24
                        spacing: Theme.spacingMd

                        Text {
                            text: "Full Trino Error Output:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            font.weight: Font.DemiBold
                            color: "#F87171"
                        }

                        Rectangle {
                            width: parent.width
                            implicitHeight: errFullText.implicitHeight + 20
                            color: "#180D11"
                            radius: 4
                            border.color: "#7F1D1D"
                            border.width: 1

                            TextArea {
                                id: errFullText
                                anchors.fill: parent
                                anchors.margins: 10
                                text: root.errorMessage || "No error details recorded."
                                readOnly: true
                                font.family: Theme.monoFontFamily
                                font.pixelSize: Theme.fontSizeXs
                                color: "#FECACA"
                                wrapMode: TextEdit.Wrap
                                background: null
                            }
                        }

                        Text {
                            text: "Executed Query at Failure:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            font.weight: Font.DemiBold
                            color: Theme.textSecondary
                        }

                        Rectangle {
                            width: parent.width
                            implicitHeight: Math.max(120, failedSqlText.implicitHeight + 20)
                            color: "#080C14"
                            radius: 4
                            border.color: Theme.border
                            border.width: 1

                            TextArea {
                                id: failedSqlText
                                anchors.fill: parent
                                anchors.margins: 10
                                text: root.failedQuery || "-- Query was not generated or failed before SQL build"
                                readOnly: true
                                font.family: Theme.monoFontFamily
                                font.pixelSize: Theme.fontSizeXs
                                color: "#94A3B8"
                                wrapMode: TextEdit.Wrap
                                background: null
                            }
                        }
                    }
                }

                // Tab 3: Suggested Corrected SQL View
                ScrollView {
                    id: sqlScrollView
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    clip: true
                    visible: !root.isLoading && root.activeTab === "sql"

                    Column {
                        width: sqlScrollView.width - 24
                        spacing: Theme.spacingMd

                        Row {
                            width: parent.width
                            spacing: Theme.spacingMd

                            Text {
                                text: "Corrected Trino SQL Query:"
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSm
                                font.weight: Font.DemiBold
                                color: Theme.accentEmerald
                                width: parent.width - copyBtn.width - 12
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            AppButton {
                                id: copyBtn
                                text: "⎘ Copy Corrected SQL"
                                variant: "success"
                                implicitHeight: 30
                                anchors.verticalCenter: parent.verticalCenter
                                onClicked: {
                                    fixedSqlText.selectAll()
                                    fixedSqlText.copy()
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width
                            implicitHeight: Math.max(300, fixedSqlText.implicitHeight + 24)
                            color: "#080C14"
                            radius: 4
                            border.color: "#059669"
                            border.width: 1

                            TextArea {
                                id: fixedSqlText
                                anchors.fill: parent
                                anchors.margins: 12
                                text: root.suggestedSql || "-- No SQL extracted"
                                readOnly: true
                                font.family: Theme.monoFontFamily
                                font.pixelSize: Theme.fontSizeSm
                                color: "#A7F3D0"
                                selectionColor: Theme.primary
                                selectedTextColor: "#FFFFFF"
                                wrapMode: TextEdit.NoWrap
                                background: null
                            }
                        }
                    }
                }
            }

            // ── Footer ──────────────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: "Tip: Qwen 2.5 Coder analyzes Trino error codes and adjusts type casts & comparisons."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textMuted
                    Layout.fillWidth: true
                }

                AppButton {
                    text: "⎘ Copy Analysis"
                    variant: "secondary"
                    implicitHeight: 34
                    enabled: root.explanationText !== ""
                    onClicked: {
                        var clip = "Table: " + root.tableName + "\n\nError:\n" + root.errorMessage + "\n\nAI Diagnosis:\n" + root.explanationText
                        if (root.suggestedSql) clip += "\n\nCorrected SQL:\n" + root.suggestedSql
                        copyHelperArea.text = clip
                        copyHelperArea.selectAll()
                        copyHelperArea.copy()
                    }
                }

                TextEdit {
                    id: copyHelperArea
                    visible: false
                }
            }
        }
    }
}
