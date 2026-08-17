import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Controls
import QtQuick.Layouts
import "."
import "components"
import "views"

ApplicationWindow {
    id: window
    width: 1240
    height: 820
    minimumWidth: 980
    minimumHeight: 640
    visible: true
    title: "Trino Database Diff & Report Studio"
    color: Theme.bgDark

    // Active View: "batch" | "adhoc" | "output" | "logs" | "settings"
    property string currentView: "batch"

    // Toast notification
    property string toastMessage: ""
    property string toastType: "info"
    property bool   toastVisible: false

    // SQL Viewer Dialog (modal)
    SqlViewerDialog { id: sqlViewerDialog }

    // Backend signal connections
    Connections {
        target: backend

        function onSqlPreviewReady(tableName, sqlText) {
            sqlViewerDialog.tableName    = tableName
            sqlViewerDialog.sqlContent   = sqlText
            sqlViewerDialog.open()
        }

        function onNotificationEmitted(type, message) {
            window.showToast(type, message)
        }
    }

    function showToast(type, message) {
        window.toastType    = type
        window.toastMessage = message
        window.toastVisible = true
        toastTimer.restart()
    }

    Timer {
        id: toastTimer
        interval: 4000
        onTriggered: window.toastVisible = false
    }

    // =========================================================================
    // Root Layout: Sidebar  |  Main area
    // =========================================================================
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ── Sidebar ──────────────────────────────────────────────────────────
        Rectangle {
            Layout.preferredWidth: 230
            Layout.fillHeight: true
            color: Theme.bgSidebar
            // right-edge border only
            Rectangle {
                anchors.right: parent.right
                width: 1; height: parent.height
                color: Theme.border
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: 0

                // Brand row
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin:    Theme.spacingSm
                    Layout.bottomMargin: Theme.spacingMd
                    spacing: Theme.spacingSm

                    Rectangle {
                        width: 36; height: 36
                        radius: Theme.radiusSm
                        color: Theme.primary

                        Text {
                            anchors.centerIn: parent
                            text: "⚡"
                            font.pixelSize: 18
                        }
                    }

                    Column {
                        spacing: 1
                        Text {
                            text: "Trino Diff Studio"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.Bold
                            color: Theme.textPrimary
                        }
                        Text {
                            text: "Oracle ⇄ Postgres"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeXs
                            color: Theme.accentCyan
                        }
                    }
                }

                // Divider
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.border
                    Layout.bottomMargin: Theme.spacingSm
                }

                // Nav items
                NavItem {
                    icon: "📊"; label: "Batch Runner"
                    active: window.currentView === "batch"
                    badge: backend.tables.length > 0 ? String(backend.tables.length) : ""
                    onClicked: window.currentView = "batch"
                    Layout.fillWidth: true
                }
                NavItem {
                    icon: "⚡"; label: "Single Diff"
                    active: window.currentView === "adhoc"
                    onClicked: window.currentView = "adhoc"
                    Layout.fillWidth: true
                }
                NavItem {
                    icon: "📁"; label: "Reports & Output"
                    active: window.currentView === "output"
                    badge: backend.outputFiles.length > 0 ? String(backend.outputFiles.length) : ""
                    onClicked: window.currentView = "output"
                    Layout.fillWidth: true
                }
                NavItem {
                    icon: "📝"; label: "Execution Logs"
                    active: window.currentView === "logs"
                    onClicked: window.currentView = "logs"
                    Layout.fillWidth: true
                }
                NavItem {
                    icon: "⚙️"; label: "Settings"
                    active: window.currentView === "settings"
                    onClicked: window.currentView = "settings"
                    Layout.fillWidth: true
                }

                Item { Layout.fillHeight: true }

                // Connection footer card
                Rectangle {
                    Layout.fillWidth: true
                    height: 60
                    Layout.bottomMargin: Theme.spacingXs
                    radius: Theme.radiusSm
                    color: Theme.bgInput
                    border.color: Theme.borderSubtle
                    border.width: 1

                    Column {
                        anchors.fill: parent
                        anchors.margins: Theme.spacingSm
                        spacing: 2

                        Row {
                            spacing: 6
                            Rectangle {
                                width: 8; height: 8; radius: 4
                                color: Theme.accentEmerald
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: "Trino"
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeXs
                                font.weight: Font.DemiBold
                                color: Theme.textPrimary
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        Text {
                            text: (backend.config.trino_host || "localhost") + ":" + (backend.config.trino_port || 8080)
                            font.family: Theme.monoFontFamily
                            font.pixelSize: 10
                            color: Theme.textMuted
                        }
                    }
                }
            }
        }

        // ── Main area ─────────────────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Toast notification banner — animate height, NOT visibility
            Rectangle {
                id: toastBanner
                Layout.fillWidth: true
                // Height drives the show/hide animation; clip keeps content invisible when height=0
                height: window.toastVisible ? 38 : 0
                clip: true
                color: window.getToastBg()

                Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin:  Theme.spacingLg
                    anchors.rightMargin: Theme.spacingLg
                    spacing: Theme.spacingSm

                    Text {
                        text: window.toastMessage
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSm
                        font.weight: Font.Medium
                        color: "#FFFFFF"
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }

                    AppButton {
                        text: "✕"
                        variant: "ghost"
                        implicitHeight: 24
                        customPaddingH: 6
                        onClicked: window.toastVisible = false
                    }
                }
            }

            // View stack
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: window.getViewIndex(window.currentView)

                BatchView   { id: batchView   }
                AdhocView   { id: adhocView   }
                OutputView  { id: outputView  }
                LogsView    { id: logsView    }
                SettingsView { id: settingsView }
            }

            // Status bar
            Rectangle {
                Layout.fillWidth: true
                height: 34
                color: Theme.bgSidebar
                border.color: Theme.border
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin:  Theme.spacingLg
                    anchors.rightMargin: Theme.spacingLg
                    spacing: Theme.spacingMd

                    Text {
                        text: backend.statusText
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeXs
                        color: backend.isRunning ? Theme.accentCyan : Theme.textSecondary
                    }

                    ProgressBar {
                        visible: backend.isRunning
                        Layout.preferredWidth: 180
                        value: backend.progressPercent / 100.0

                        background: Rectangle {
                            implicitHeight: 6
                            implicitWidth:  180
                            radius: 3
                            color: Theme.bgInput
                        }
                        contentItem: Item {
                            implicitHeight: 6
                            Rectangle {
                                width: parent.width * (backend.progressPercent / 100.0)
                                height: parent.height
                                radius: 3
                                color: Theme.primary
                                Behavior on width { NumberAnimation { duration: 200 } }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: "Source: " + (backend.config.source_catalog || "postgres") +
                              "   ➔   Target: " + (backend.config.target_catalog || "oracle")
                        font.family: Theme.monoFontFamily
                        font.pixelSize: 11
                        color: Theme.textMuted
                    }
                }
            }
        }
    }

    // =========================================================================
    // Inline component: NavItem
    // =========================================================================
    component NavItem: Rectangle {
        id: navRoot
        property string icon:   ""
        property string label:  ""
        property bool   active: false
        property string badge:  ""
        signal clicked()

        // width is set by caller via Layout.fillWidth: true
        implicitHeight: 40
        radius: Theme.radiusSm
        color: active              ? Theme.primary
             : navMouseArea.containsMouse ? Theme.bgCardHover
             : "transparent"

        Behavior on color { ColorAnimation { duration: 110 } }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin:  Theme.spacingMd
            anchors.rightMargin: Theme.spacingMd
            spacing: Theme.spacingSm

            Text {
                text: navRoot.icon
                font.pixelSize: 15
            }

            Text {
                text: navRoot.label
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBase
                font.weight: navRoot.active ? Font.DemiBold : Font.Normal
                color: navRoot.active ? "#FFFFFF" : Theme.textSecondary
                Layout.fillWidth: true
            }

            Rectangle {
                visible: navRoot.badge !== ""
                implicitWidth:  badgeText.implicitWidth + 12
                implicitHeight: 18
                radius: 9
                color: navRoot.active ? "#3D5AE0" : Theme.bgCard
                border.color: navRoot.active ? "#6D84F5" : Theme.border
                border.width: 1

                Text {
                    id: badgeText
                    anchors.centerIn: parent
                    text: navRoot.badge
                    font.family: Theme.fontFamily
                    font.pixelSize: 10
                    color: navRoot.active ? "#FFFFFF" : Theme.textMuted
                }
            }
        }

        MouseArea {
            id: navMouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: navRoot.clicked()
        }
    }

    // =========================================================================
    // Helper functions
    // =========================================================================
    function getViewIndex(viewName) {
        if (viewName === "batch")    return 0
        if (viewName === "adhoc")    return 1
        if (viewName === "output")   return 2
        if (viewName === "logs")     return 3
        if (viewName === "settings") return 4
        return 0
    }

    function getToastBg() {
        if (window.toastType === "success") return "#065F46"
        if (window.toastType === "error")   return "#991B1B"
        if (window.toastType === "warning") return "#92400E"
        return "#1E40AF"
    }
}
