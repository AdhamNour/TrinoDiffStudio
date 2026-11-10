import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    property string searchFilter: ""
    property string typeFilter: "ALL"
    property string selectedBatchId: "ALL"

    property var batchComboModel: {
        var list = ["All Batches"]
        var bList = (backend && backend.batches) ? backend.batches : []
        for (var i = 0; i < bList.length; i++) {
            var b = bList[i]
            if (b) {
                var label = (b.batch_id || "") + " [" + (b.started_at || "") + " • " + (b.status || "") + "]"
                list.push(label)
            }
        }
        return list
    }

    property var currentSelectedBatch: {
        if (root.selectedBatchId === "ALL" || !root.selectedBatchId) return null
        var bList = (backend && backend.batches) ? backend.batches : []
        for (var i = 0; i < bList.length; i++) {
            if (bList[i] && bList[i].batch_id === root.selectedBatchId) return bList[i]
        }
        return null
    }

    property var filteredFiles: {
        var raw = (backend && backend.outputFiles) ? backend.outputFiles : []
        var tf = root.typeFilter
        var sf = root.searchFilter
        var res = []
        for (var i = 0; i < raw.length; i++) {
            var f = raw[i]
            if (f) {
                if (tf !== "ALL" && f.type !== tf) continue
                if (sf && f.name && f.name.toLowerCase().indexOf(sf) === -1) continue
                res.push(f)
            }
        }
        return res
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        // Header & Actions Bar
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            ColumnLayout {
                spacing: 2
                Text {
                    text: "Reports & Output Explorer"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeLg
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                }
                Text {
                    text: "Database: ~/Documents/TrinoDiffStudio/trino_diff.db  •  Output: " + ((backend && backend.config) ? (backend.config.output_dir || "output/") : "output/")
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textMuted
                }
            }

            Item { Layout.fillWidth: true }

            AppButton {
                text: "⟳ Refresh"
                variant: "ghost"
                onClicked: {
                    backend.refreshOutputFiles(root.selectedBatchId)
                }
            }

            AppButton {
                text: "📁 Open Folder"
                variant: "secondary"
                onClicked: backend.openFolder(backend.config.output_dir || "output")
            }
        }

        // Batch Filter & Batch Info Card
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: batchCardCol.implicitHeight + Theme.spacingMd * 2
            color: Theme.bgCard
            radius: Theme.radiusMd
            border.color: Theme.border
            border.width: 1

            ColumnLayout {
                id: batchCardCol
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingMd

                    Text {
                        text: "Filter by Batch:"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSm
                        font.weight: Font.Medium
                        color: Theme.textSecondary
                        Layout.alignment: Qt.AlignVCenter
                    }

                    AppComboBox {
                        id: batchCombo
                        Layout.fillWidth: true
                        model: root.batchComboModel
                        currentIndex: 0
                        onActivated: (index) => {
                            if (index === 0) {
                                root.selectedBatchId = "ALL"
                            } else {
                                var bList = backend.batches || []
                                if (index - 1 < bList.length) {
                                    root.selectedBatchId = bList[index - 1].batch_id
                                }
                            }
                            backend.filterOutputByBatch(root.selectedBatchId)
                        }
                    }

                    AppButton {
                        text: "Show All"
                        variant: "ghost"
                        implicitHeight: 36
                        visible: root.selectedBatchId !== "ALL"
                        Layout.alignment: Qt.AlignVCenter
                        onClicked: {
                            root.selectedBatchId = "ALL"
                            batchCombo.currentIndex = 0
                            backend.filterOutputByBatch("ALL")
                        }
                    }
                }

                // Batch summary banner (visible when a specific batch is selected)
                RowLayout {
                    id: batchDetailsRow
                    Layout.fillWidth: true
                    visible: root.currentSelectedBatch !== null
                    spacing: Theme.spacingLg

                    Row {
                        spacing: 6
                        Text {
                            text: "Catalogs:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                        }
                        Text {
                            text: (root.currentSelectedBatch ? (root.currentSelectedBatch.source_catalog + " ➔ " + root.currentSelectedBatch.target_catalog) : "")
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            font.weight: Font.DemiBold
                            color: Theme.accentCyan
                        }
                    }

                    Row {
                        spacing: 6
                        Text {
                            text: "Status:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                        }
                        StatusBadge {
                            status: root.currentSelectedBatch ? root.currentSelectedBatch.status : "Ready"
                        }
                    }

                    Row {
                        spacing: 6
                        Text {
                            text: "Tables:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                        }
                        Text {
                            text: root.currentSelectedBatch ? (root.currentSelectedBatch.success_count + " ok, " + root.currentSelectedBatch.error_count + " failed / " + root.currentSelectedBatch.total_tables + " total") : ""
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            font.weight: Font.Medium
                            color: Theme.textPrimary
                        }
                    }

                    Row {
                        spacing: 6
                        Text {
                            text: "Total Diffs:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                        }
                        Text {
                            text: root.currentSelectedBatch ? (root.currentSelectedBatch.total_diffs + " row(s)") : "0"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            font.weight: Font.Bold
                            color: Theme.accentAmber
                        }
                    }

                    Row {
                        spacing: 6
                        visible: root.currentSelectedBatch && root.currentSelectedBatch.duration_seconds > 0
                        Text {
                            text: "Duration:"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textMuted
                        }
                        Text {
                            text: root.currentSelectedBatch ? (root.currentSelectedBatch.duration_seconds + "s") : ""
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.textSecondary
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }
        }

        // Filters Bar (Search & File Type)
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            AppTextField {
                id: searchInput
                Layout.preferredWidth: 260
                placeholderText: "🔍 Filter files..."
                onTextChanged: root.searchFilter = searchInput.text.toLowerCase().trim()
            }

            Row {
                spacing: 4
                Layout.alignment: Qt.AlignVCenter

                AppButton {
                    text: "All Files"
                    variant: root.typeFilter === "ALL" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.typeFilter = "ALL"
                }
                AppButton {
                    text: "Excel Reports (.xlsx)"
                    variant: root.typeFilter === "Excel" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.typeFilter = "Excel"
                }
                AppButton {
                    text: "Parquet (.parquet)"
                    variant: root.typeFilter === "Parquet" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.typeFilter = "Parquet"
                }
                AppButton {
                    text: "SQL Queries (.sql)"
                    variant: root.typeFilter === "SQL" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.typeFilter = "SQL"
                }
                AppButton {
                    text: "Run Logs (.txt)"
                    variant: root.typeFilter === "Log" ? "primary" : "ghost"
                    implicitHeight: 32
                    onClicked: root.typeFilter = "Log"
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                text: root.filteredFiles.length + " file(s)"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textMuted
            }
        }

        // Output Files List Card
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.bgCard
            radius: Theme.radiusMd
            clip: true
            border.color: Theme.border
            border.width: 1

            ListView {
                id: fileListView
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                clip: true
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                model: root.filteredFiles
                reuseItems: true

                ScrollBar.vertical: ScrollBar {
                    id: vScrollBar
                    policy: ScrollBar.AsNeeded
                }

                delegate: Rectangle {
                    width: fileListView.width - (vScrollBar.visible ? 14 : 6)
                    implicitHeight: 56
                    radius: Theme.radiusSm
                    color: Theme.bgInput
                    border.color: Theme.borderSubtle
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.spacingMd
                        anchors.rightMargin: Theme.spacingMd
                        spacing: Theme.spacingMd

                        // Type Icon Badge
                        Rectangle {
                            implicitWidth: 34
                            implicitHeight: 34
                            radius: Theme.radiusSm
                            color: modelData.type === "Excel" ? "#064E3B"
                                 : (modelData.type === "Parquet" ? "#3B0764"
                                 : (modelData.type === "Log" ? "#0C4A6E" : "#451A03"))
                            border.color: modelData.type === "Excel" ? "#059669"
                                        : (modelData.type === "Parquet" ? "#9333EA"
                                        : (modelData.type === "Log" ? "#0EA5E9" : "#F59E0B"))
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: modelData.type === "Excel" ? "📊"
                                    : (modelData.type === "Parquet" ? "📦"
                                    : (modelData.type === "Log" ? "📝" : "⚡"))
                                font.pixelSize: 14
                            }
                        }

                        // File Details
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            Text {
                                text: modelData.name
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeBase
                                font.weight: Font.Medium
                                color: Theme.textPrimary
                                elide: Text.ElideRight
                            }

                            Text {
                                text: (modelData.size || "") + " • Modified: " + (modelData.modified || "") + (modelData.table_name ? (" • Table: " + modelData.table_name) : "")
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeXs
                                color: Theme.textMuted
                            }
                        }

                        // Actions
                        AppButton {
                            text: modelData.type === "Excel" ? "Open Excel"
                                : (modelData.type === "Parquet" ? "Open Parquet"
                                : (modelData.type === "Log" ? "Open Log" : "Edit / Open"))
                            variant: "secondary"
                            implicitHeight: 30
                            onClicked: backend.openFile(modelData.path)
                        }

                        AppButton {
                            text: "Open Folder"
                            variant: "ghost"
                            implicitHeight: 30
                            onClicked: backend.openFolder(modelData.path)
                        }

                        AppButton {
                            text: "🗑"
                            variant: "ghost"
                            implicitHeight: 30
                            customPaddingH: 8
                            onClicked: backend.deleteOutputFile(modelData.path)
                        }
                    }
                }
            }

            // Empty State
            Column {
                anchors.centerIn: parent
                spacing: Theme.spacingSm
                visible: root.filteredFiles.length === 0

                Text {
                    text: "📂 No Output Files Found"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeLg
                    font.weight: Font.DemiBold
                    color: Theme.textSecondary
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: root.selectedBatchId !== "ALL"
                          ? "No output files linked to Batch " + root.selectedBatchId
                          : "Generated diff SQL queries, Excel reports and run logs will appear here."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBase
                    color: Theme.textMuted
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }
}
