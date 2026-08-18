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
    property string promptText: ""
    property bool   isLoading: false
    property string activeTab: "diagnosis" // "diagnosis" | "sql" | "error" | "prompt"

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
                        text: "Powered by " + (backend.config.ollama_model || "Qwen 2.5 Coder") + "  •  Effort: " + (backend.config.ai_effort || "High") + "  •  Table: " + root.tableName
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

                AppButton {
                    text: "📋 AI Prompt Sent"
                    variant: root.activeTab === "prompt" ? "primary" : "ghost"
                    implicitHeight: 32
                    visible: root.promptText !== ""
                    onClicked: root.activeTab = "prompt"
                }

                Item { width: 16 }

                AppButton {
                    text: root.isLoading ? "Analyzing…" : "⟳ Re-analyze"
                    variant: "secondary"
                    implicitHeight: 32
                    enabled: !root.isLoading && root.tableName !== ""
                    onClicked: backend.explainTableError(root.tableName, true)
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

                        // AI Output (Rich Markdown Rendering)
                        TextEdit {
                            id: aiOutputText
                            width: parent.width
                            text: root.renderMarkdown(root.explanationText)
                            textFormat: TextEdit.RichText
                            readOnly: true
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBase
                            color: Theme.textPrimary
                            selectedTextColor: "#FFFFFF"
                            selectionColor: Theme.primary
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
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

                // Tab 4: Prompt Sent View
                ScrollView {
                    id: promptScrollView
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    clip: true
                    visible: !root.isLoading && root.activeTab === "prompt"

                    Column {
                        width: promptScrollView.width - 24
                        spacing: Theme.spacingMd

                        Row {
                            width: parent.width
                            spacing: Theme.spacingMd

                            Text {
                                text: "Exact Prompt Sent to AI (" + (backend.config.ollama_model || "Ollama") + "):"
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSm
                                font.weight: Font.DemiBold
                                color: Theme.accentCyan
                                width: parent.width - copyPromptBtn.width - 12
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            AppButton {
                                id: copyPromptBtn
                                text: "⎘ Copy Prompt"
                                variant: "secondary"
                                implicitHeight: 30
                                anchors.verticalCenter: parent.verticalCenter
                                onClicked: {
                                    promptSentText.selectAll()
                                    promptSentText.copy()
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width
                            implicitHeight: Math.max(260, promptSentText.implicitHeight + 24)
                            color: "#080C14"
                            radius: 4
                            border.color: Theme.border
                            border.width: 1

                            TextEdit {
                                id: promptSentText
                                anchors.fill: parent
                                anchors.margins: 12
                                text: root.renderMarkdown(root.promptText || "-- No prompt recorded")
                                textFormat: TextEdit.RichText
                                readOnly: true
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textPrimary
                                selectionColor: Theme.primary
                                selectedTextColor: "#FFFFFF"
                                wrapMode: TextEdit.Wrap
                                selectByMouse: true
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

    function renderMarkdown(md) {
        if (!md || md.trim() === "") {
            return "<i style='color: #64748B;'>Click 'Re-analyze' to generate AI diagnosis.</i>"
        }

        // 1. Escape raw HTML characters
        var html = md
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")

        // 2. Fenced Code Blocks: ```sql ... ``` or ``` ... ```
        html = html.replace(/```(?:sql|trino|bash|json|python)?\n*([\s\S]*?)```/gi, function(match, code) {
            return "<div style='background-color: #0F172A; border: 1px solid #334155; border-radius: 6px; padding: 10px; margin: 10px 0;'><pre style='font-family: monospace; color: #34D399; font-size: 12px; margin: 0; white-space: pre-wrap;'>" + code.trim() + "</pre></div>"
        })

        // 3. Inline Code: `code`
        html = html.replace(/`([^`\n]+)`/g, "<code style='background-color: #1E293B; color: #38BDF8; font-family: monospace; padding: 2px 6px; border-radius: 3px; font-size: 12px;'>$1</code>")

        // 4. Headers: #, ##, ###, ####
        html = html.replace(/^#### (.*?)$/gm, "<h4 style='color: #C084FC; font-size: 13px; font-weight: bold; margin-top: 14px; margin-bottom: 4px;'>$1</h4>")
        html = html.replace(/^### (.*?)$/gm, "<h3 style='color: #A78BFA; font-size: 15px; font-weight: bold; margin-top: 16px; margin-bottom: 6px;'>$1</h3>")
        html = html.replace(/^## (.*?)$/gm, "<h2 style='color: #818CF8; font-size: 17px; font-weight: bold; margin-top: 18px; margin-bottom: 6px;'>$1</h2>")
        html = html.replace(/^# (.*?)$/gm, "<h1 style='color: #60A5FA; font-size: 19px; font-weight: bold; margin-top: 20px; margin-bottom: 8px;'>$1</h1>")

        // 5. Bold and Italics
        html = html.replace(/\*\*([^*]+)\*\*/g, "<strong style='color: #F8FAFC; font-weight: bold;'>$1</strong>")
        html = html.replace(/\*([^*]+)\*/g, "<em style='color: #CBD5E1;'>$1</em>")

        // 6. Checkboxes: - [x] or - [ ]
        html = html.replace(/^[*-] \[x\] (.*?)$/gim, "<div style='margin-left: 14px; margin-bottom: 4px; color: #34D399;'>☑ $1</div>")
        html = html.replace(/^[*-] \[ \] (.*?)$/gim, "<div style='margin-left: 14px; margin-bottom: 4px; color: #94A3B8;'>☐ $1</div>")

        // 7. Bullet Lists: - or *
        html = html.replace(/^[*-] (.*?)$/gm, "<div style='margin-left: 14px; margin-bottom: 4px; color: #E2E8F0;'>• $1</div>")

        // 8. Numbered Lists: 1. 2. etc.
        html = html.replace(/^(\d+)\. (.*?)$/gm, "<div style='margin-left: 14px; margin-bottom: 4px; color: #E2E8F0;'><strong style='color: #A78BFA;'>$1.</strong> $2</div>")

        // 9. Newlines & Paragraph Spacing
        html = html.replace(/\n\n+/g, "<div style='height: 8px;'></div>")
        html = html.replace(/\n/g, "<br/>")

        return "<div style='color: #E2E8F0; font-size: 13px; line-height: 1.5;'>" + html + "</div>"
    }
}
