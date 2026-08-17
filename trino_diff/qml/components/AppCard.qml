import QtQuick
import ".."

Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""
    property Component headerAction: null
    default property alias content: contentArea.data

    color: Theme.bgCard
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1

    // Header column (optional) ─ always at top of card
    Column {
        id: cardHeader
        visible: root.title !== ""
        width: parent.width - Theme.spacingLg * 2
        x: Theme.spacingLg
        y: Theme.spacingLg
        spacing: 2

        Row {
            width: parent.width
            spacing: Theme.spacingSm

            Column {
                width: parent.width - (actionLoader.visible ? actionLoader.width + Theme.spacingSm : 0)
                spacing: 2

                Text {
                    text: root.title
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeMd
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                    width: parent.width
                    elide: Text.ElideRight
                }

                Text {
                    visible: root.subtitle !== ""
                    text: root.subtitle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textMuted
                    width: parent.width
                    wrapMode: Text.WordWrap
                }
            }

            Loader {
                id: actionLoader
                sourceComponent: root.headerAction
                visible: root.headerAction !== null
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // Content area — fills the space below the header
    Item {
        id: contentArea
        x: Theme.spacingLg
        y: root.title !== "" ? (cardHeader.y + cardHeader.height + Theme.spacingMd) : Theme.spacingLg
        width: root.width - Theme.spacingLg * 2
        height: root.height - y - Theme.spacingLg
    }
}
