import QtQuick
import QtQuick.Controls.Basic
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
    anchors.centerIn: Overlay.overlay
    width:  Math.min(Overlay.overlay ? Overlay.overlay.width  * 0.86 : 900, 940)
    height: Math.min(Overlay.overlay ? Overlay.overlay.height * 0.86 : 680, 720)
    padding: 0

    background: Rectangle {
        color: Theme.bgCard
        radius: Theme.radiusMd
        border.color: Theme.border
        border.width: 1
    }

    contentItem: Item {
        anchors.fill: parent

        Column {
            anchors.fill: parent
            anchors.margins: Theme.spacingLg
            spacing: Theme.spacingMd

            // ── Header ─────────────────────────────────────────────────────
            Row {
                width: parent.width
                height: 44

                Column {
                    width: parent.width - btnRow.width - Theme.spacingMd
                    spacing: 3
                    anchors.verticalCenter: parent.verticalCenter

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

                Row {
                    id: btnRow
                    spacing: Theme.spacingSm
                    anchors.verticalCenter: parent.verticalCenter

                    // Copy button
                    Rectangle {
                        width: copyLbl.implicitWidth + 24
                        height: 32
                        radius: Theme.radiusSm
                        color: copyMa.containsMouse ? Theme.bgInputHover : Theme.bgInput
                        border.color: copyMa.containsMouse ? Theme.borderHover : Theme.border
                        border.width: 1

                        Text {
                            id: copyLbl
                            anchors.centerIn: parent
                            text: "⎘  Copy SQL"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBase
                            color: Theme.textSecondary
                        }

                        MouseArea {
                            id: copyMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                sqlTextEdit.selectAll()
                                sqlTextEdit.copy()
                            }
                        }
                    }

                    // Close button
                    Rectangle {
                        width: closeLbl.implicitWidth + 24
                        height: 32
                        radius: Theme.radiusSm
                        color: closeMa.containsMouse ? Theme.bgCardHover : "transparent"
                        border.color: closeMa.containsMouse ? Theme.border : "transparent"
                        border.width: 1

                        Text {
                            id: closeLbl
                            anchors.centerIn: parent
                            text: "✕  Close"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBase
                            color: closeMa.containsMouse ? Theme.textPrimary : Theme.textSecondary
                        }

                        MouseArea {
                            id: closeMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.close()
                        }
                    }
                }
            }

            // ── SQL Code View ───────────────────────────────────────────────
            Rectangle {
                width: parent.width
                height: parent.height - 44 - Theme.spacingMd
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
                        color: "#A5B4FC"
                        selectedTextColor: "#FFFFFF"
                        selectionColor: Theme.primary
                        wrapMode: TextEdit.NoWrap
                        background: null
                    }
                }
            }
        }
    }
}
