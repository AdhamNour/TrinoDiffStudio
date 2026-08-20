import QtQuick

pragma Singleton

QtObject {
    // Mode detection: Dev mode when running locally from Python (version is "dev")
    property bool isDev: (typeof backend !== "undefined" && backend && backend.isDev) ? true : true

    // Backgrounds
    readonly property color bgDark: "#0B0F19"
    readonly property color bgSidebar: "#111827"
    readonly property color bgCard: "#182234"
    readonly property color bgCardHover: "#1F2B42"
    readonly property color bgInput: "#131C2D"
    readonly property color bgInputHover: "#19253B"

    // Accents & Actions
    // In Dev Mode: Bright Yellow (#FACC15 / #FDE047 / #EAB308)
    // In Production / Release Mode: Dark Blue (#3B82F6 / #2563EB / #1D4ED8)
    readonly property color primary: isDev ? "#FACC15" : "#3B82F6"
    readonly property color primaryHover: isDev ? "#FDE047" : "#2563EB"
    readonly property color primaryActive: isDev ? "#EAB308" : "#1D4ED8"
    readonly property color primaryText: isDev ? "#0F172A" : "#FFFFFF"

    readonly property color accentCyan: isDev ? "#FACC15" : "#06B6D4"
    readonly property color accentEmerald: "#10B981"
    readonly property color accentAmber: "#F59E0B"
    readonly property color accentRose: "#EF4444"
    readonly property color accentPurple: "#8B5CF6"

    // Text Colors
    readonly property color textPrimary: "#F9FAFB"
    readonly property color textSecondary: "#94A3B8"
    readonly property color textMuted: "#64748B"
    readonly property color textDisabled: "#475569"

    // Borders & Dividers
    readonly property color border: "#223049"
    readonly property color borderHover: "#334155"
    readonly property color borderFocus: isDev ? "#FACC15" : "#3B82F6"
    readonly property color borderSubtle: "#1E293B"

    // Typography — use single font name (QML does not parse CSS font stacks)
    readonly property string fontFamily: "Segoe UI"
    readonly property string monoFontFamily: "Consolas"

    readonly property int fontSizeXs: 11
    readonly property int fontSizeSm: 12
    readonly property int fontSizeBase: 13
    readonly property int fontSizeMd: 15
    readonly property int fontSizeLg: 18
    readonly property int fontSizeXl: 22

    // Dimensions & Radii
    readonly property int radiusSm: 6
    readonly property int radiusMd: 10
    readonly property int radiusLg: 14
    readonly property int radiusFull: 9999

    readonly property int spacingXs: 4
    readonly property int spacingSm: 8
    readonly property int spacingMd: 14
    readonly property int spacingLg: 20
    readonly property int spacingXl: 28
}
