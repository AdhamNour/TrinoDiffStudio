import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// SqlViewerDialog lives inside components/ so:
//   ".."  → qml/         (Theme singleton)
//   Other components in the same folder can be used directly by type name
//   because qmldir declares them all.

Dialog {
    id: root

    property string tableName: ""
    property string sqlContent: ""

    title: ""
    modal: true
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    width:  Math.min(parent ? parent.width * 0.86 : 900, 940)
    height: Math.min(parent ? parent.height * 0.86 : 680, 720)
    padding: 0

    background: Rectangle {
        color: Theme.bgCard
        radius: Theme.radiusMd
        border.color: Theme.border
        border.width: 1
    }

    contentItem: Item {
        anchors.fill: parent

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // ── Header ─────────────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                spacing: Theme.spacingMd

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        text: "Generated Trino SQL Query"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeLg
                        font.weight: Font.Bold
                        color: Theme.textPrimary
                    }

                    Text {
                        text: "Table: " + root.tableName
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.accentCyan
                    }
                }

                RowLayout {
                    spacing: Theme.spacingSm

                    // Copy button
                    AppButton {
                        text: "⎘  Copy SQL"
                        variant: "secondary"
                        implicitHeight: 34
                        onClicked: {
                            sqlTextEdit.selectAll()
                            sqlTextEdit.copy()
                        }
                    }

                    // Close button
                    AppButton {
                        text: "✕  Close"
                        variant: "ghost"
                        implicitHeight: 34
                        onClicked: root.close()
                    }
                }
            }

            // ── SQL Code View ───────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.bgDark
                radius: Theme.radiusSm
                border.color: Theme.border
                border.width: 1
                clip: true

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingSm
                    clip: true

                    TextArea {
                        id: sqlTextEdit
                        text: root.sqlContent
                        readOnly: true
                        font.family: Theme.monoFontFamily
                        font.pixelSize: Theme.fontSizeSm
                        color: "#FDE047"
                        selectedTextColor: Theme.primaryText
                        selectionColor: Theme.primary
                        wrapMode: TextEdit.NoWrap
                        background: null
                    }
                }
            }
        }
    }
}
