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
        var raw = (backend && backend.tables) ? backend.tables : []
        var filter = root.searchFilter
        if (!filter) return raw
        var res = []
        for (var i = 0; i < raw.length; i++) {
            var t = raw[i]
            if (t && t.table_name && t.table_name.toLowerCase().indexOf(filter) !== -1)
                res.push(t)
        }
        return res
    }

    // Preserve scroll position across model data updates
    onFilteredTablesChanged: {
        if (!tableListView.moving && !tableListView.flicking) {
            var prevY = tableListView.contentY
            Qt.callLater(function() {
                if (tableListView.contentHeight > tableListView.height) {
                    var maxY = tableListView.contentHeight - tableListView.height
                    tableListView.contentY = Math.max(0, Math.min(prevY, maxY))
                }
            })
        }
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
                            text: (backend && backend.config) ? (backend.config.excel_path || "") : ""
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
                    model: (backend && backend.catalogs) ? backend.catalogs : ["postgres", "oracle"]
                    currentIndex: Math.max(0, (backend && backend.catalogs ? backend.catalogs : []).indexOf(backend && backend.config ? (backend.config.source_catalog || "postgres") : "postgres"))
                    onActivated: (index) => {
                        if (backend && backend.config) backend.config["source_catalog"] = currentText
                    }
                }

                // Target catalog
                AppComboBox {
                    id: targetCatCombo
                    Layout.preferredWidth: 155
                    label: "Target Catalog"
                    model: (backend && backend.catalogs) ? backend.catalogs : ["postgres", "oracle"]
                    currentIndex: {
                        var cats = (backend && backend.catalogs) ? backend.catalogs : []
                        var targetCat = (backend && backend.config) ? (backend.config.target_catalog || "oracle") : "oracle"
                        var idx = cats.indexOf(targetCat)
                        return idx >= 0 ? idx : (cats.length > 1 ? 1 : 0)
                    }
                    onActivated: (index) => {
                        if (backend && backend.config) backend.config["target_catalog"] = currentText
                    }
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
                text: getSelectedCount() + " / " + (backend && backend.tables ? backend.tables.length : 0) + " selected"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
                verticalAlignment: Text.AlignVCenter
            }

            Rectangle {
                visible: backend ? (backend.currentBatchId !== "") : false
                implicitWidth: batchChipText.implicitWidth + 16
                implicitHeight: 24
                radius: Theme.radiusSm
                color: (backend && backend.isRunning) ? "#1E3A8A" : "#1A2540"
                border.color: (backend && backend.isRunning) ? Theme.accentCyan : Theme.border
                border.width: 1

                Text {
                    id: batchChipText
                    anchors.centerIn: parent
                    text: (backend && backend.isRunning ? "⚡ " : "📦 ") + (backend ? backend.currentBatchId : "")
                    font.family: Theme.monoFontFamily
                    font.pixelSize: Theme.fontSizeXs
                    color: (backend && backend.isRunning) ? Theme.accentCyan : Theme.textSecondary
                }
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
                text: (backend && backend.isRunning) ? "⬛  Stop" : "▶  Run Selected"
                variant: (backend && backend.isRunning) ? "danger" : "primary"
                implicitHeight: 36
                enabled: (backend && backend.isRunning) || getSelectedCount() > 0
                onClicked: (backend && backend.isRunning) ? backend.stopBatch() : backend.startBatch(true)
            }

            AppButton {
                text: "▶▶  Run All"
                variant: "success"
                implicitHeight: 36
                visible: !backend || !backend.isRunning
                enabled: backend && backend.tables && backend.tables.length > 0
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

            ListView {
                id: tableListView
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                clip: true
                spacing: 5
                boundsBehavior: Flickable.StopAtBounds
                model: root.filteredTables
                reuseItems: true

                ScrollBar.vertical: ScrollBar {
                    id: vScrollBar
                    policy: ScrollBar.AsNeeded
                }

                delegate: Rectangle {
                    width: tableListView.width - (vScrollBar.visible ? 14 : 6)
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
                        AppCheckBox {
                            id: rowCheck
                            checked: modelData.selected
                            onToggled: backend.toggleTableSelection(modelData.table_name, checked)
                        }

                        // Table name + id-column count
                        Column {
                            Layout.preferredWidth: 240
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 2

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
                            Layout.minimumWidth: 0
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 5
                            clip: true

                            Repeater {
                                model: modelData.id_columns ? modelData.id_columns.slice(0, 4) : []

                                delegate: Rectangle {
                                    required property var modelData
                                    implicitWidth:  chipLabel.implicitWidth + 12
                                    implicitHeight: 22
                                    radius: 4
                                    color: "#1A2540"
                                    border.color: Theme.border
                                    border.width: 1

                                    Text {
                                        id: chipLabel
                                        anchors.centerIn: parent
                                        text: typeof modelData === "string" ? modelData : String(modelData)
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
                            Layout.alignment: Qt.AlignVCenter

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
                            Layout.alignment: Qt.AlignVCenter
                        }

                        // AI Fix button (shown for failing tables when AI is enabled)
                        AppButton {
                            text: modelData.ai_status === "Ready" ? "🤖 View AI Fix"
                                : (modelData.ai_status === "Diagnosing" ? "🤖 Diagnosing…" : "🤖 AI Fix")
                            variant: modelData.ai_status === "Ready" ? "primary" : "danger"
                            implicitHeight: 28
                            customPaddingH: 8
                            visible: (backend && backend.config && backend.config.enable_ai_diagnosis !== false) && modelData.status === "Error"
                            Layout.alignment: Qt.AlignVCenter
                            ToolTip.visible: hovered
                            ToolTip.text: modelData.ai_status === "Ready"
                                          ? "AI diagnosis and SQL fix are ready! Click to view."
                                          : (modelData.ai_status === "Diagnosing"
                                             ? "Qwen 2.5-Coder is analyzing this error in parallel with Trino batch..."
                                             : "Ask Qwen 2.5-Coder to explain this Trino error and suggest a SQL fix")
                            onClicked: backend.explainTableError(modelData.table_name)
                        }

                        // Action buttons
                        AppButton {
                            text: "SQL"
                            variant: "ghost"
                            implicitHeight: 28
                            customPaddingH: 8
                            Layout.alignment: Qt.AlignVCenter
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
                            enabled: !backend || !backend.isRunning
                            Layout.alignment: Qt.AlignVCenter
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

            // Empty state overlay
            Column {
                anchors.centerIn: parent
                spacing: Theme.spacingMd
                visible: !backend || !backend.tables || backend.tables.length === 0

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
        if (!backend || !backend.tables) return 0
        var n = 0
        for (var i = 0; i < backend.tables.length; i++)
            if (backend.tables[i] && backend.tables[i].selected) n++
        return n
    }

    function getFilteredTables() {
        if (!backend || !backend.tables) return []
        if (!root.searchFilter) return backend.tables
        var res = []
        for (var i = 0; i < backend.tables.length; i++) {
            var t = backend.tables[i]
            if (t && t.table_name && t.table_name.toLowerCase().indexOf(root.searchFilter) !== -1)
                res.push(t)
        }
        return res
    }
}
