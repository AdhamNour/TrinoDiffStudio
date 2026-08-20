import QtQuick

pragma Singleton

QtObject {
    // Mode detection: Dev mode when running locally from Python (version is "dev")
    property bool isDev: (typeof backend !== "undefined" && backend && backend.isDev) ? true : true

    // Backgrounds — Deep Carbon & Obsidian Dark Palette (eliminates muddy brown and dark blue)
    readonly property color bgDark: "#0C0D0E"
    readonly property color bgSidebar: "#131416"
    readonly property color bgCard: "#1A1B1E"
    readonly property color bgCardHover: "#222429"
    readonly property color bgInput: "#141518"
    readonly property color bgInputHover: "#1C1E22"

    // Accents & Actions — Vibrant Bright Yellow Palette
    readonly property color primary: "#FACC15"
    readonly property color primaryHover: "#FDE047"
    readonly property color primaryActive: "#EAB308"
    readonly property color primaryText: "#000000"

    readonly property color accentCyan: "#FACC15"
    readonly property color accentEmerald: "#10B981"
    readonly property color accentAmber: "#F59E0B"
    readonly property color accentRose: "#EF4444"
    readonly property color accentPurple: "#A855F7"

    // Text Colors
    readonly property color textPrimary: "#F9FAFB"
    readonly property color textSecondary: "#9CA3AF"
    readonly property color textMuted: "#6B7280"
    readonly property color textDisabled: "#4B5563"

    // Borders & Dividers
    readonly property color border: "#2D2F36"
    readonly property color borderHover: "#454852"
    readonly property color borderFocus: "#FACC15"
    readonly property color borderSubtle: "#212328"

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
