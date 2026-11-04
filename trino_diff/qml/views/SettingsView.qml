import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

Item {
    id: root

    property string testResult: ""
    property bool   isTesting:  false
    property string ollamaTestResult: ""
    property bool   isTestingOllama:  false

    FolderDialog {
        id: folderDialog
        title: "Select Output Directory"
        onAccepted: {
            var raw = decodeURIComponent(folderDialog.selectedFolder.toString())
            // Strip file:/// prefix; on Windows the path will look like /C:/Users/...
            raw = raw.replace(/^file:\/\/\//, "").replace(/^file:\/\//, "")
            // Remove leading slash before drive letter on Windows: /C:/ → C:/
            if (/^\/[A-Za-z]:\//.test(raw))
                raw = raw.substring(1)
            outputDirField.text = raw
        }
    }

    Connections {
        target: backend
        function onOllamaTestFinished(ok, msg) {
            root.isTestingOllama = false
            root.ollamaTestResult = ok ? "SUCCESS" : msg
        }
    }

    ScrollView {
        id: settingsScroll
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        clip: true

        ColumnLayout {
            width: settingsScroll.availableWidth
            spacing: Theme.spacingLg

            // ── Header ──────────────────────────────────────────────────
            Column {
                spacing: 4
                Text {
                    text: "Connection & Application Settings"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeLg
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                }
                Text {
                    text: "Configure Trino endpoint, default catalogs, column exclusions, and output folder."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    width: parent.width
                    wrapMode: Text.WordWrap
                }
            }

            // ── Trino Connection card ────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: connColumn.implicitHeight + Theme.spacingLg * 2
                color: Theme.bgCard
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                Column {
                    id: connColumn
                    anchors {
                        top: parent.top; left: parent.left; right: parent.right
                        margins: Theme.spacingLg
                    }
                    spacing: Theme.spacingMd

                    Column {
                        spacing: 2
                        Text {
                            text: "Trino Server Connection"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "Endpoint credentials and network configuration for the Trino REST API."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textMuted
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppTextField {
                            id: hostField
                            Layout.fillWidth: true
                            label: "Host"
                            text: (backend && backend.config) ? (backend.config.trino_host || "localhost") : "localhost"
                        }

                        AppTextField {
                            id: portField
                            Layout.preferredWidth: 130
                            label: "Port"
                            text: String((backend && backend.config) ? (backend.config.trino_port || 8080) : 8080)
                        }

                        AppTextField {
                            id: userField
                            Layout.preferredWidth: 150
                            label: "User"
                            text: (backend && backend.config) ? (backend.config.trino_user || "admin") : "admin"
                        }

                        AppTextField {
                            id: passwordField
                            Layout.preferredWidth: 180
                            label: "Password"
                            echoMode: TextInput.Password
                            text: (backend && backend.config) ? (backend.config.trino_password || "") : ""
                        }

                        AppComboBox {
                            id: schemeCombo
                            Layout.preferredWidth: 110
                            label: "Scheme"
                            model: ["http", "https"]
                            currentIndex: (backend && backend.config && backend.config.http_scheme === "https") ? 1 : 0
                        }
                    }

                    AppCheckBox {
                        id: disableSslVerificationCheck
                        text: "Disable HTTPS certificate verification (self-signed certificates)"
                        visible: schemeCombo.currentText === "https"
                        checked: backend && backend.config
                                 ? !(backend.config.trino_verify_ssl !== false)
                                 : false
                    }

                    // Test Connection row
                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppButton {
                            text: root.isTesting ? "Testing…" : "⚡  Test Connection & Fetch Catalogs"
                            variant: "primary"
                            implicitHeight: 36
                            enabled: !root.isTesting
                            onClicked: {
                                root.isTesting  = true
                                root.testResult = backend ? backend.testConnection(
                                    hostField.text,
                                    parseInt(portField.text) || 8080,
                                    userField.text,
                                    passwordField.text,
                                    schemeCombo.currentText,
                                    !disableSslVerificationCheck.checked
                                ) : "ERROR: backend unavailable"
                                root.isTesting  = false
                            }
                        }

                        Text {
                            visible: root.testResult !== ""
                            text: root.testResult === "SUCCESS" ? "✓  Connection OK" : root.testResult
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            color: root.testResult === "SUCCESS" ? Theme.accentEmerald : Theme.accentRose
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    Text {
                        text: "Available catalogs: " + ((backend && backend.catalogs) ? backend.catalogs.join(", ") : "")
                        font.family: Theme.monoFontFamily
                        font.pixelSize: Theme.fontSizeXs
                        color: Theme.accentCyan
                    }
                }
            }

            // ── Default Diff Parameters card ─────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: defaultsColumn.implicitHeight + Theme.spacingLg * 2
                color: Theme.bgCard
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                Column {
                    id: defaultsColumn
                    anchors {
                        top: parent.top; left: parent.left; right: parent.right
                        margins: Theme.spacingLg
                    }
                    spacing: Theme.spacingMd

                    Column {
                        spacing: 2
                        Text {
                            text: "Default Diff Parameters"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "Default catalogs, column exclusions, and output folder for batch and ad-hoc runs."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textMuted
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppComboBox {
                            id: defaultSourceCatCombo
                            Layout.fillWidth: true
                            label: "Default Source Catalog"
                            model: (backend && backend.catalogs) ? backend.catalogs : ["postgres", "oracle"]
                            currentIndex: Math.max(0, (backend && backend.catalogs ? backend.catalogs : []).indexOf(backend && backend.config ? (backend.config.source_catalog || "postgres") : "postgres"))
                        }

                        AppComboBox {
                            id: defaultTargetCatCombo
                            Layout.fillWidth: true
                            label: "Default Target Catalog"
                            model: (backend && backend.catalogs) ? backend.catalogs : ["postgres", "oracle"]
                            currentIndex: {
                                var cats = (backend && backend.catalogs) ? backend.catalogs : []
                                var targetCat = (backend && backend.config) ? (backend.config.target_catalog || "oracle") : "oracle"
                                var idx = cats.indexOf(targetCat)
                                return idx >= 0 ? idx : (cats.length > 1 ? 1 : 0)
                            }
                        }
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppTextField {
                            id: excludeColsField
                            Layout.fillWidth: true
                            label: "Excluded Columns (comma-separated)"
                            text: (backend && backend.config) ? (backend.config.exclude_columns || "extraction_timestamp") : "extraction_timestamp"
                        }

                        AppTextField {
                            id: excludeSuffixField
                            Layout.preferredWidth: 190
                            label: "Excluded Column Suffix"
                            text: (backend && backend.config) ? (backend.config.exclude_suffix || "key") : "key"
                        }
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppTextField {
                            id: outputDirField
                            Layout.fillWidth: true
                            label: "Output Directory"
                            text: (backend && backend.config) ? (backend.config.output_dir || "output") : "output"
                        }

                        AppButton {
                            text: "Browse…"
                            variant: "secondary"
                            implicitHeight: 38
                            Layout.alignment: Qt.AlignBottom
                            onClicked: folderDialog.open()
                        }
                    }

                    AppCheckBox {
                        id: trimStringsCheck
                        checked: (backend && backend.config) ? (backend.config.trim_strings !== false) : true
                        text: "Trim strings (removes trailing whitespace from Oracle CHAR columns)"
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // Notification Preferences
                    Column {
                        width: parent.width
                        spacing: Theme.spacingXs

                        Text {
                            text: "🔔  Windows System Notifications"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }

                        AppCheckBox {
                            id: notifyTableCheck
                            checked: (backend && backend.config) ? (backend.config.notify_table_complete !== false) : true
                            text: "Notify when each individual table diff finishes"
                        }

                        AppCheckBox {
                            id: notifyBatchCheck
                            checked: (backend && backend.config) ? (backend.config.notify_batch_complete !== false) : true
                            text: "Notify when entire batch execution completes"
                        }
                    }
                }
            }

            // ── Execution Engine & Iceberg Configuration card ────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: engineColumn.implicitHeight + Theme.spacingLg * 2
                color: Theme.bgCard
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                Column {
                    id: engineColumn
                    anchors {
                        top: parent.top; left: parent.left; right: parent.right
                        margins: Theme.spacingLg
                    }
                    spacing: Theme.spacingMd

                    Column {
                        spacing: 2
                        Text {
                            text: "⚡ Execution Engine & Iceberg Acceleration"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "Select whether to use the Iceberg multi-step staged pipeline for high throughput and low memory, or the direct monolithic query."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textMuted
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppComboBox {
                            id: diffEngineCombo
                            Layout.fillWidth: true
                            label: "Diff Execution Engine"
                            model: [
                                "Iceberg Staged Pipeline (Recommended - Fast, Low Memory, Resilient)",
                                "Direct Monolithic Query (Legacy FULL OUTER JOIN)"
                            ]
                            currentIndex: {
                                var eng = ((backend && backend.config ? backend.config.diff_engine : "iceberg") || "iceberg").toLowerCase()
                                return (eng === "direct") ? 1 : 0
                            }
                        }
                    }

                    Column {
                        width: parent.width
                        spacing: Theme.spacingMd
                        visible: diffEngineCombo.currentIndex === 0

                        RowLayout {
                            width: parent.width
                            spacing: Theme.spacingMd

                            AppTextField {
                                id: icebergCatalogField
                                Layout.fillWidth: true
                                label: "Iceberg Catalog Name"
                                text: (backend && backend.config) ? (backend.config.iceberg_catalog || "iceberg") : "iceberg"
                                placeholderText: "iceberg"
                            }

                            AppTextField {
                                id: icebergSchemaField
                                Layout.preferredWidth: 240
                                label: "Staging Schema Name"
                                text: (backend && backend.config) ? (backend.config.iceberg_staging_schema || "staging") : "staging"
                                placeholderText: "staging"
                            }
                        }

                        AppCheckBox {
                            id: icebergCleanupCheck
                            checked: (backend && backend.config) ? (backend.config.iceberg_cleanup_on_error !== false) : true
                            text: "Automatically drop temporary Iceberg staging tables on completion / failure"
                        }
                    }
                }
            }

            // ── Ollama AI Assistant card ─────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: ollamaColumn.implicitHeight + Theme.spacingLg * 2
                color: Theme.bgCard
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                Column {
                    id: ollamaColumn
                    anchors {
                        top: parent.top; left: parent.left; right: parent.right
                        margins: Theme.spacingLg
                    }
                    spacing: Theme.spacingMd

                    // Header with title and Master Enable/Disable Switch
                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        Column {
                            Layout.fillWidth: true
                            spacing: 2

                            Text {
                                text: "🤖 Ollama / Qwen 2.5 Coder AI Configuration"
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeMd
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                            }
                            Text {
                                text: "Local LLM endpoint used to diagnose cross-database Trino errors and suggest SQL fixes."
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textMuted
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                            }
                        }

                        AppSwitch {
                            id: enableAiSwitch
                            checked: (backend && backend.config) ? (backend.config.enable_ai_diagnosis !== false) : true
                            text: checked ? "AI Enabled" : "AI Disabled"
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // Ollama configuration sub-section (disabled when AI is switched off)
                    Column {
                        width: parent.width
                        spacing: Theme.spacingMd
                        enabled: enableAiSwitch.checked
                        opacity: enableAiSwitch.checked ? 1.0 : 0.4

                        Behavior on opacity { NumberAnimation { duration: 150 } }

                        RowLayout {
                            width: parent.width
                            spacing: Theme.spacingMd

                            AppTextField {
                                id: ollamaUrlField
                                Layout.fillWidth: true
                                label: "Ollama API URL"
                                text: (backend && backend.config) ? (backend.config.ollama_url || "http://localhost:11434") : "http://localhost:11434"
                                placeholderText: "http://localhost:11434"
                            }

                            AppTextField {
                                id: ollamaModelField
                                Layout.preferredWidth: 220
                                label: "Ollama Model"
                                text: (backend && backend.config) ? (backend.config.ollama_model || "qwen2.5-coder:1.5b") : "qwen2.5-coder:1.5b"
                                placeholderText: "qwen2.5-coder:1.5b"
                            }
                        }

                        RowLayout {
                            width: parent.width
                            spacing: Theme.spacingMd

                            AppComboBox {
                                id: aiEffortCombo
                                Layout.fillWidth: true
                                label: "AI Reasoning & Validation Effort"
                                model: ["High (Deep Multi-Step Self-Validation)", "Medium (Balanced Verification)", "Low (Fast Single-Pass)"]
                                currentIndex: {
                                    var eff = ((backend && backend.config ? backend.config.ai_effort : "High") || "High").toLowerCase()
                                    if (eff.indexOf("low") !== -1) return 2
                                    if (eff.indexOf("med") !== -1) return 1
                                    return 0
                                }
                            }
                        }

                        Text {
                            text: "💡 High effort instructs the AI to perform an exhaustive multi-point self-validation checklist (type casting audit, syntax verification, schema qualifiers) before outputting the corrected SQL."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }

                        RowLayout {
                            width: parent.width
                            spacing: Theme.spacingMd

                            AppButton {
                                text: root.isTestingOllama ? "Testing…" : "⚡ Test Ollama Connection"
                                variant: "primary"
                                implicitHeight: 36
                                enabled: enableAiSwitch.checked && !root.isTestingOllama
                                onClicked: {
                                    root.isTestingOllama = true
                                    root.ollamaTestResult = ""
                                    backend.testOllamaConnectionAsync(ollamaUrlField.text, ollamaModelField.text)
                                }
                            }

                            Text {
                                visible: root.ollamaTestResult !== ""
                                text: root.ollamaTestResult === "SUCCESS" ? "✓ Ollama & Model Available" : root.ollamaTestResult
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSm
                                color: root.ollamaTestResult === "SUCCESS" ? Theme.accentEmerald : Theme.accentRose
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                            }
                        }

                        AppCheckBox {
                            id: autoAiCheck
                            checked: (backend && backend.config) ? (backend.config.auto_ai_diagnosis !== false) : true
                            text: "Auto-diagnose Trino errors in background with AI during batch execution"
                        }
                    }
                }
            }

            Item { height: Theme.spacingLg }
        }
    }

    AppButton {
        id: saveButton
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: Theme.spacingLg
        anchors.bottomMargin: Theme.spacingLg
        z: 10
        text: "💾  Save Configuration"
        variant: "success"
        implicitHeight: 48
        customRadius: 24
        customPaddingH: 24
        onClicked: {
            var effortVal = "High"
            if (aiEffortCombo.currentIndex === 2) effortVal = "Low"
            else if (aiEffortCombo.currentIndex === 1) effortVal = "Medium"

            var engineVal = (diffEngineCombo.currentIndex === 1) ? "direct" : "iceberg"

            backend.updateSettings(
                hostField.text,
                parseInt(portField.text) || 8080,
                userField.text,
                schemeCombo.currentText,
                defaultSourceCatCombo.currentText,
                defaultTargetCatCombo.currentText,
                outputDirField.text,
                excludeColsField.text,
                excludeSuffixField.text,
                trimStringsCheck.checked,
                notifyTableCheck.checked,
                notifyBatchCheck.checked,
                enableAiSwitch.checked,
                ollamaUrlField.text,
                ollamaModelField.text,
                effortVal,
                autoAiCheck.checked,
                engineVal,
                icebergCatalogField.text,
                icebergSchemaField.text,
                icebergCleanupCheck.checked,
                passwordField.text,
                !disableSslVerificationCheck.checked
            )
        }
    }
}
