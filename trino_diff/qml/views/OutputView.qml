import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    property string searchFilter: ""
    property string typeFilter: "ALL"

    property var filteredFiles: {
        var raw = backend.outputFiles || []
        var tf = root.typeFilter
        var sf = root.searchFilter
        var res = []
        for (var i = 0; i < raw.length; i++) {
            var f = raw[i]
            if (tf !== "ALL" && f.type !== tf) continue
            if (sf && f.name.toLowerCase().indexOf(sf) === -1) continue
            res.push(f)
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
                    text: "Output Directory: " + (backend.config.output_dir || "output/")
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeXs
                    color: Theme.textMuted
                }
            }

            Item { Layout.fillWidth: true }

            AppButton {
                text: "⟳ Refresh"
                variant: "ghost"
                onClicked: backend.refreshOutputFiles()
            }

            AppButton {
                text: "📁 Open Folder"
                variant: "secondary"
                onClicked: backend.openFolder(backend.config.output_dir || "output")
            }
        }

        // Filters Bar
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
                AppButton {
                    text: "All"
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

            ScrollView {
                anchors.fill: parent
                anchors.margins: Theme.spacingSm
                clip: true

                ListView {
                    id: fileListView
                    width: parent.width
                    spacing: 6
                    model: root.filteredFiles

                    delegate: Rectangle {
                        width: fileListView.width - 12
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
                                     : (modelData.type === "Parquet" ? "#3B0764" : "#1E3A8A")
                                border.color: modelData.type === "Excel" ? "#059669"
                                            : (modelData.type === "Parquet" ? "#9333EA" : "#3B82F6")
                                border.width: 1

                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.type === "Excel" ? "📊"
                                        : (modelData.type === "Parquet" ? "📦" : "⚡")
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
                                    text: (modelData.size || "") + " • Modified: " + (modelData.modified || "")
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeXs
                                    color: Theme.textMuted
                                }
                            }

                            // Actions
                            AppButton {
                                text: modelData.type === "Excel" ? "Open Excel"
                                    : (modelData.type === "Parquet" ? "Open Parquet" : "Edit / Open")
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
                    text: "Generated diff SQL queries and Excel reports will appear here."
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBase
                    color: Theme.textMuted
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }

    function getFilteredFiles() {
        var result = []
        for (var i = 0; i < backend.outputFiles.length; i++) {
            var f = backend.outputFiles[i]
            if (root.typeFilter !== "ALL" && f.type !== root.typeFilter) continue
            if (root.searchFilter && f.name.toLowerCase().indexOf(root.searchFilter) === -1) continue
            result.push(f)
        }
        return result
    }
}
