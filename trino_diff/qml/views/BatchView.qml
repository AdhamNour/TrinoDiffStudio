import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

Item {
    id: root

    property string searchFilter: ""

    property var filteredTables: {
        var raw = backend.tables || []
        var filter = root.searchFilter
        if (!filter) return raw
        var res = []
        for (var i = 0; i < raw.length; i++) {
            var t = raw[i]
            if (t.table_name && t.table_name.toLowerCase().indexOf(filter) !== -1)
                res.push(t)
        }
        return res
    }

    FileDialog {
        id: fileDialog
        title: "Select Business Columns Excel File"
        nameFilters: ["Excel Files (*.xlsx *.xls)"]
        onAccepted: backend.loadExcel(fileDialog.selectedFile.toString())
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        // ── Top bar: Excel path + Source/Target catalog selectors ──────────
        Rectangle {
            Layout.fillWidth: true
            height: 86
            color: Theme.bgCard
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingMd

                // Excel path picker
                Column {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: "Excel Mapping File"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSm
                        font.weight: Font.Medium
                        color: Theme.textSecondary
                    }

                    RowLayout {
                        width: parent.width
                        spacing: Theme.spacingSm

                        AppTextField {
                            id: excelPathField
                            Layout.fillWidth: true
                            text: backend.config.excel_path || ""
                            placeholderText: "Path to Business Columns Excel mapping..."
                            readOnly: true
                        }

                        AppButton {
                            text: "Browse…"
                            variant: "secondary"
                            implicitHeight: 38
                            onClicked: fileDialog.open()
                        }

                        AppButton {
                            text: "Reload"
                            variant: "ghost"
                            implicitHeight: 38
                            onClicked: backend.loadExcel(excelPathField.text)
                        }
                    }
                }

                // Divider
                Rectangle {
                    width: 1
                    Layout.fillHeight: true
                    color: Theme.border
                    Layout.leftMargin: Theme.spacingXs
                    Layout.rightMargin: Theme.spacingXs
                }

                // Source catalog
                AppComboBox {
                    id: sourceCatCombo
                    Layout.preferredWidth: 155
                    label: "Source Catalog"
                    model: backend.catalogs
                    currentIndex: Math.max(0, backend.catalogs.indexOf(backend.config.source_catalog || "postgres"))
                    onActivated: (index) => backend.config["source_catalog"] = currentText
                }

                // Target catalog
                AppComboBox {
                    id: targetCatCombo
                    Layout.preferredWidth: 155
                    label: "Target Catalog"
                    model: backend.catalogs
                    currentIndex: {
                        var idx = backend.catalogs.indexOf(backend.config.target_catalog || "oracle")
                        return idx >= 0 ? idx : (backend.catalogs.length > 1 ? 1 : 0)
                    }
                    onActivated: (index) => backend.config["target_catalog"] = currentText
                }

                AppButton {
                    text: "⟳"
                    variant: "ghost"
                    implicitHeight: 38
                    Layout.alignment: Qt.AlignBottom
                    ToolTip.visible: hovered
                    ToolTip.text: "Refresh catalogs from Trino"
                    onClicked: backend.refreshCatalogs()
                }
            }
        }

        // ── Actions bar ────────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            AppTextField {
                id: searchInput
                Layout.preferredWidth: 260
                placeholderText: "🔍  Filter tables…"
                onTextChanged: root.searchFilter = searchInput.text.toLowerCase().trim()
            }

            Text {
                text: getSelectedCount() + " / " + backend.tables.length + " selected"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
                verticalAlignment: Text.AlignVCenter
            }

            Item { Layout.fillWidth: true }

            AppButton {
                text: "Select All"
                variant: "ghost"
                implicitHeight: 34
                onClicked: backend.selectAllTables(true)
            }

            AppButton {
                text: "Deselect All"
                variant: "ghost"
                implicitHeight: 34
                onClicked: backend.selectAllTables(false)
            }

            AppButton {
                text: backend.isRunning ? "⬛  Stop" : "▶  Run Selected"
                variant: backend.isRunning ? "danger" : "primary"
                implicitHeight: 36
                enabled: backend.isRunning || getSelectedCount() > 0
                onClicked: backend.isRunning ? backend.stopBatch() : backend.startBatch(true)
            }

            AppButton {
                text: "▶▶  Run All"
                variant: "success"
                implicitHeight: 36
                visible: !backend.isRunning
                enabled: backend.tables.length > 0
                onClicked: backend.startBatch(false)
            }
        }

        // ── Table list ─────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.bgCard
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1
            clip: true

            ScrollView {
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                clip: true

                ListView {
                    id: tableListView
                    width: parent.width
                    spacing: 5
                    model: root.filteredTables

                    delegate: Rectangle {
                        width: tableListView.width - 10
                        height: 64
                        radius: Theme.radiusSm
                        color: modelData.selected ? Theme.bgCardHover : Theme.bgInput
                        border.color: modelData.selected ? Theme.borderFocus : Theme.borderSubtle
                        border.width: 1

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin:  Theme.spacingMd
                            anchors.rightMargin: Theme.spacingMd
                            spacing: Theme.spacingSm

                            // Checkbox
                            CheckBox {
                                id: rowCheck
                                checked: modelData.selected
                                onToggled: backend.toggleTableSelection(modelData.table_name, checked)
                            }

                            // Table name + id-column count
                            Column {
                                Layout.preferredWidth: 240
                                spacing: 2
                                anchors.verticalCenter: parent.verticalCenter

                                Text {
                                    text: modelData.table_name
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeMd
                                    font.weight: Font.DemiBold
                                    color: Theme.textPrimary
                                    elide: Text.ElideRight
                                    width: parent.width
                                }

                                Text {
                                    text: (modelData.id_columns ? modelData.id_columns.length : 0) + " ID column(s)"
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeXs
                                    color: Theme.textMuted
                                }
                            }

                            // ID column chip tags
                            Row {
                                Layout.fillWidth: true
                                spacing: 5
                                clip: true
                                anchors.verticalCenter: parent.verticalCenter

                                Repeater {
                                    model: modelData.id_columns ? modelData.id_columns.slice(0, 4) : []

                                    delegate: Rectangle {
                                        required property string modelData
                                        implicitWidth:  chipLabel.implicitWidth + 12
                                        implicitHeight: 22
                                        radius: 4
                                        color: "#1A2540"
                                        border.color: Theme.border
                                        border.width: 1

                                        Text {
                                            id: chipLabel
                                            anchors.centerIn: parent
                                            text: modelData
                                            font.family: Theme.monoFontFamily
                                            font.pixelSize: 10
                                            color: Theme.accentCyan
                                        }
                                    }
                                }

                                Text {
                                    visible: modelData.id_columns && modelData.id_columns.length > 4
                                    text: "+" + (modelData.id_columns.length - 4) + " more"
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeXs
                                    color: Theme.textMuted
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }

                            // Diff count badge (shown only after run)
                            Rectangle {
                                visible: modelData.status === "Completed"
                                implicitWidth:  diffLbl.implicitWidth + 18
                                implicitHeight: 22
                                radius: Theme.radiusFull
                                color:  modelData.diff_count > 0 ? "#4D2000" : "#003322"
                                border.color: modelData.diff_count > 0 ? "#F59E0B" : "#10B981"
                                border.width: 1
                                anchors.verticalCenter: parent.verticalCenter

                                Text {
                                    id: diffLbl
                                    anchors.centerIn: parent
                                    text: modelData.diff_count + " diffs"
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeXs
                                    font.weight: Font.DemiBold
                                    color: modelData.diff_count > 0 ? "#FDE68A" : "#A7F3D0"
                                }
                            }

                            // Status badge
                            StatusBadge {
                                status: modelData.status || "Ready"
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            // Action buttons
                            AppButton {
                                text: "SQL"
                                variant: "ghost"
                                implicitHeight: 28
                                customPaddingH: 8
                                onClicked: {
                                    backend.generateSqlPreview(
                                        modelData.table_name,
                                        "auto",
                                        (modelData.id_columns || []).join(","),
                                        sourceCatCombo.currentText,
                                        targetCatCombo.currentText
                                    )
                                }
                            }

                            AppButton {
                                text: "Run"
                                variant: "secondary"
                                implicitHeight: 28
                                customPaddingH: 10
                                enabled: !backend.isRunning
                                onClicked: {
                                    backend.runSingleTable(
                                        modelData.table_name,
                                        "auto",
                                        (modelData.id_columns || []).join(","),
                                        sourceCatCombo.currentText,
                                        targetCatCombo.currentText
                                    )
                                }
                            }
                        }
                    }
                }
            }

            // Empty state overlay
            Column {
                anchors.centerIn: parent
                spacing: Theme.spacingMd
                visible: backend.tables.length === 0

                Text {
                    text: "📊  No Tables Loaded"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeLg
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: "Browse and select an Excel mapping file to populate tables."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBase
                    color: Theme.textMuted
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                AppButton {
                    text: "Choose Excel File"
                    anchors.horizontalCenter: parent.horizontalCenter
                    onClicked: fileDialog.open()
                }
            }
        }
    }

    // ── Helper functions ───────────────────────────────────────────────────
    function getSelectedCount() {
        var n = 0
        for (var i = 0; i < backend.tables.length; i++)
            if (backend.tables[i].selected) n++
        return n
    }

    function getFilteredTables() {
        if (!root.searchFilter) return backend.tables
        var res = []
        for (var i = 0; i < backend.tables.length; i++) {
            var t = backend.tables[i]
            if (t.table_name.toLowerCase().indexOf(root.searchFilter) !== -1)
                res.push(t)
        }
        return res
    }
}
