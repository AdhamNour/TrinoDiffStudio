import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        clip: true

        ColumnLayout {
            // Must match the ScrollView's width for layout to work inside a ScrollView
            width: root.width - Theme.spacingLg * 2
            spacing: Theme.spacingLg

            // ── Header ─────────────────────────────────────────────────────
            Column {
                spacing: 4
                Text {
                    text: "Ad-Hoc / Single Table Diff"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeLg
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                }
                Text {
                    text: "Compare any table on-demand using dynamic source and target catalogs."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    width: parent.width
                    wrapMode: Text.WordWrap
                }
            }

            // ── Configuration card ─────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                // Fixed height card (no AppCard so we control the layout precisely)
                implicitHeight: configColumn.implicitHeight + Theme.spacingLg * 2
                color: Theme.bgCard
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                Column {
                    id: configColumn
                    anchors {
                        top: parent.top; left: parent.left; right: parent.right
                        margins: Theme.spacingLg
                    }
                    spacing: Theme.spacingMd

                    // Card header
                    Column {
                        spacing: 2
                        Text {
                            text: "Table & Catalog Parameters"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "Specify table name, composite ID columns, schema, and catalogs."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textMuted
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }
                    }

                    // Separator
                    Rectangle { width: parent.width; height: 1; color: Theme.border }

                    // Row 1: Catalog selectors
                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppComboBox {
                            id: sourceCatCombo
                            Layout.fillWidth: true
                            label: "Source Catalog"
                            model: backend.catalogs
                            currentIndex: Math.max(0, backend.catalogs.indexOf(backend.config.source_catalog || "postgres"))
                        }

                        AppComboBox {
                            id: targetCatCombo
                            Layout.fillWidth: true
                            label: "Target Catalog"
                            model: backend.catalogs
                            currentIndex: {
                                var idx = backend.catalogs.indexOf(backend.config.target_catalog || "oracle")
                                return idx >= 0 ? idx : (backend.catalogs.length > 1 ? 1 : 0)
                            }
                        }
                    }

                    // Row 2: Table name + schema
                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppTextField {
                            id: tableNameField
                            Layout.fillWidth: true
                            label: "Table Name (e.g. fct_customer_blocks)"
                            placeholderText: "Enter table name…"
                        }

                        AppComboBox {
                            id: schemaCombo
                            Layout.preferredWidth: 200
                            label: "Schema"
                            model: ["auto", "curated", "rdm", "public"]
                            currentIndex: 0
                        }
                    }

                    // Row 3: ID columns
                    AppTextField {
                        id: idColsField
                        width: parent.width
                        label: "ID / Business Columns (comma-separated)"
                        placeholderText: "e.g. customer_id, account_number, block_code"
                    }

                    // Row 4: Exclude options
                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppTextField {
                            id: excludeColsField
                            Layout.fillWidth: true
                            label: "Exclude Columns (comma-separated)"
                            text: backend.config.exclude_columns || "extraction_timestamp"
                        }

                        AppTextField {
                            id: excludeSuffixField
                            Layout.preferredWidth: 190
                            label: "Exclude Suffix"
                            text: backend.config.exclude_suffix || "key"
                        }
                    }

                    // Row 5: Options + action buttons
                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        AppCheckBox {
                            id: trimStringsCheck
                            checked: backend.config.trim_strings !== false
                            text: "Trim strings (CHAR padding)"
                        }

                        Item { Layout.fillWidth: true }

                        AppButton {
                            text: "🤖 AI Fix"
                            variant: "danger"
                            implicitHeight: 36
                            visible: (backend.config.enable_ai_diagnosis !== false)
                                  && tableNameField.text.trim() !== ""
                                  && backend.getTableErrorMessage(tableNameField.text.trim()) !== ""
                            ToolTip.visible: hovered
                            ToolTip.text: "Diagnose Trino failure and generate fixed SQL with Qwen 2.5 Coder"
                            onClicked: backend.explainTableError(tableNameField.text.trim())
                        }

                        AppButton {
                            text: "🔍  Preview SQL"
                            variant: "secondary"
                            implicitHeight: 36
                            enabled: !backend.isRunning
                                  && tableNameField.text.trim() !== ""
                                  && idColsField.text.trim()    !== ""
                            onClicked: {
                                backend.generateSqlPreview(
                                    tableNameField.text.trim(),
                                    schemaCombo.currentText,
                                    idColsField.text.trim(),
                                    sourceCatCombo.currentText,
                                    targetCatCombo.currentText
                                )
                            }
                        }

                        AppButton {
                            text: backend.isRunning ? "Running…" : "▶  Run & Export"
                            variant: "primary"
                            implicitHeight: 36
                            enabled: !backend.isRunning
                                  && tableNameField.text.trim() !== ""
                                  && idColsField.text.trim()    !== ""
                            onClicked: {
                                backend.runSingleTable(
                                    tableNameField.text.trim(),
                                    schemaCombo.currentText,
                                    idColsField.text.trim(),
                                    sourceCatCombo.currentText,
                                    targetCatCombo.currentText
                                )
                            }
                        }
                    }
                }
            }

            // ── Quick templates ────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 170
                color: Theme.bgCard
                radius: Theme.radiusMd
                border.color: Theme.border
                border.width: 1

                Column {
                    anchors {
                        top: parent.top; left: parent.left; right: parent.right
                        margins: Theme.spacingLg
                    }
                    spacing: Theme.spacingMd

                    Column {
                        spacing: 2
                        Text {
                            text: "Quick Table Templates"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "Click any preset to load into the form above."
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textMuted
                        }
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingMd

                        // Template 1
                        Rectangle {
                            Layout.fillWidth: true
                            height: 80
                            color: Theme.bgInput
                            radius: Theme.radiusSm
                            border.color: Theme.border
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.spacingMd
                                spacing: Theme.spacingMd

                                Column {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text {
                                        text: "fct_customer_blocks"
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.fontSizeBase
                                        font.weight: Font.DemiBold
                                        color: Theme.accentCyan
                                    }
                                    Text {
                                        text: "Schema: curated  •  6 ID columns"
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.fontSizeXs
                                        color: Theme.textMuted
                                    }
                                }

                                AppButton {
                                    text: "Load"
                                    variant: "ghost"
                                    implicitHeight: 30
                                    onClicked: {
                                        tableNameField.text = "fct_customer_blocks"
                                        idColsField.text = "customer_id,account_number,block_code,system_name,block_type,entry_sequence"
                                        schemaCombo.currentIndex = 1
                                    }
                                }
                            }
                        }

                        // Template 2
                        Rectangle {
                            Layout.fillWidth: true
                            height: 80
                            color: Theme.bgInput
                            radius: Theme.radiusSm
                            border.color: Theme.border
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.spacingMd
                                spacing: Theme.spacingMd

                                Column {
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text {
                                        text: "ref_t24_sector"
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.fontSizeBase
                                        font.weight: Font.DemiBold
                                        color: Theme.accentCyan
                                    }
                                    Text {
                                        text: "Schema: rdm  •  1 ID column"
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.fontSizeXs
                                        color: Theme.textMuted
                                    }
                                }

                                AppButton {
                                    text: "Load"
                                    variant: "ghost"
                                    implicitHeight: 30
                                    onClicked: {
                                        tableNameField.text = "ref_t24_sector"
                                        idColsField.text = "sector_code"
                                        schemaCombo.currentIndex = 2
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Bottom spacer
            Item { height: Theme.spacingLg }
        }
    }
}
