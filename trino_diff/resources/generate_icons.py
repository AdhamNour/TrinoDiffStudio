"""
Icon generator for Trino Database Diff Studio.
Generates multi-resolution PNG icons and a combined Windows .ico file.
"""

import os
import struct
from PySide6.QtGui import (
    QImage, QPainter, QColor, QLinearGradient,
    QRadialGradient, QPainterPath, QPen, QBrush, QFont
)
from PySide6.QtCore import Qt, QRectF, QPointF


def create_app_icon_image(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    scale = size / 256.0

    # 1. Background Rounded Squircle with Shadow/Glow
    margin = 12 * scale
    rect_size = size - 2 * margin
    rect = QRectF(margin, margin, rect_size, rect_size)
    corner_radius = 48 * scale

    # Outer subtle glow / border
    glow_path = QPainterPath()
    glow_path.addRoundedRect(rect, corner_radius, corner_radius)

    # Base background gradient (Deep Obsidian Navy -> Royal Blue)
    bg_gradient = QLinearGradient(0, 0, size, size)
    bg_gradient.setColorAt(0.0, QColor("#0B132B"))   # Rich midnight navy
    bg_gradient.setColorAt(0.5, QColor("#1C2541"))   # Deep slate
    bg_gradient.setColorAt(1.0, QColor("#0F172A"))   # Dark obsidian

    painter.fillPath(glow_path, QBrush(bg_gradient))

    # Gradient border
    border_pen = QPen()
    border_grad = QLinearGradient(0, 0, size, size)
    border_grad.setColorAt(0.0, QColor(56, 189, 248, 200))   # Cyan highlight
    border_grad.setColorAt(0.5, QColor(59, 130, 246, 150))   # Blue
    border_grad.setColorAt(1.0, QColor(139, 92, 246, 120))   # Purple
    border_pen.setBrush(QBrush(border_grad))
    border_pen.setWidthF(max(1.5, 3.5 * scale))
    painter.strokePath(glow_path, border_pen)

    # 2. Glowing ambient orb in center
    orb_gradient = QRadialGradient(size * 0.5, size * 0.45, size * 0.4)
    orb_gradient.setColorAt(0.0, QColor(6, 182, 212, 60))    # Cyan glow
    orb_gradient.setColorAt(0.6, QColor(59, 130, 246, 30))   # Blue glow
    orb_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(0, 0, size, size, QBrush(orb_gradient))

    # 3. Draw Left Database Cylinder (representing Source / Oracle)
    # Scaled coordinates on 256x256 grid
    def draw_db_cylinder(cx, cy, cw, ch, is_source=True):
        # Database stack consisting of 3 disk layers
        layer_h = ch * 0.28
        spacing = ch * 0.22

        grad_color1 = QColor("#0284C7") if is_source else QColor("#10B981")
        grad_color2 = QColor("#0369A1") if is_source else QColor("#047857")
        top_color   = QColor("#38BDF8") if is_source else QColor("#34D399")

        for i in range(2, -1, -1):
            ly = cy + i * spacing
            # Bottom curved body
            body_path = QPainterPath()
            body_path.moveTo(cx - cw/2, ly)
            body_path.lineTo(cx - cw/2, ly + layer_h)
            body_path.quadTo(cx, ly + layer_h + layer_h*0.5, cx + cw/2, ly + layer_h)
            body_path.lineTo(cx + cw/2, ly)
            body_path.quadTo(cx, ly + layer_h*0.5, cx - cw/2, ly)

            body_grad = QLinearGradient(cx - cw/2, ly, cx + cw/2, ly)
            body_grad.setColorAt(0.0, grad_color2)
            body_grad.setColorAt(0.4, grad_color1)
            body_grad.setColorAt(1.0, grad_color2)
            painter.fillPath(body_path, QBrush(body_grad))

            # Top ellipse for top layer
            if i == 0:
                top_path = QPainterPath()
                top_rect = QRectF(cx - cw/2, ly - layer_h*0.3, cw, layer_h*0.7)
                top_path.addEllipse(top_rect)
                painter.fillPath(top_path, QBrush(top_color))
            else:
                lip_path = QPainterPath()
                lip_path.moveTo(cx - cw/2, ly)
                lip_path.quadTo(cx, ly + layer_h*0.5, cx + cw/2, ly)
                lip_pen = QPen(top_color.lighter(120), max(1.0, 1.5 * scale))
                painter.strokePath(lip_path, lip_pen)

    db_w = 44 * scale
    db_h = 60 * scale
    left_x = 76 * scale
    right_x = 180 * scale
    db_y = 98 * scale

    draw_db_cylinder(left_x, db_y, db_w, db_h, is_source=True)
    draw_db_cylinder(right_x, db_y, db_w, db_h, is_source=False)

    # 4. Central Diff / Compare Badge & Dynamic Energy Wave
    # Connect databases with bidirectional glowing data streams
    arrow_pen = QPen()
    arrow_pen.setStyle(Qt.DotLine if size < 32 else Qt.SolidLine)
    arrow_pen.setWidthF(max(1.5, 3.0 * scale))
    
    # Upper transfer curve (Left -> Right)
    curve1 = QPainterPath()
    curve1.moveTo(left_x + db_w*0.3, db_y + 10*scale)
    curve1.quadTo(128 * scale, db_y - 12*scale, right_x - db_w*0.3, db_y + 10*scale)
    arrow_grad1 = QLinearGradient(left_x, 0, right_x, 0)
    arrow_grad1.setColorAt(0.0, QColor("#38BDF8"))
    arrow_grad1.setColorAt(1.0, QColor("#34D399"))
    arrow_pen.setBrush(QBrush(arrow_grad1))
    painter.strokePath(curve1, arrow_pen)

    # Lower transfer curve (Right -> Left)
    curve2 = QPainterPath()
    curve2.moveTo(right_x - db_w*0.3, db_y + db_h - 10*scale)
    curve2.quadTo(128 * scale, db_y + db_h + 12*scale, left_x + db_w*0.3, db_y + db_h - 10*scale)
    arrow_grad2 = QLinearGradient(right_x, 0, left_x, 0)
    arrow_grad2.setColorAt(0.0, QColor("#34D399"))
    arrow_grad2.setColorAt(1.0, QColor("#38BDF8"))
    arrow_pen.setBrush(QBrush(arrow_grad2))
    painter.strokePath(curve2, arrow_pen)

    # Central Comparison Hub / Lightning Diamond
    center_x = 128 * scale
    center_y = (db_y + db_h/2)
    badge_size = 28 * scale

    # Diamond / Octagon shield
    shield_path = QPainterPath()
    shield_path.moveTo(center_x, center_y - badge_size)
    shield_path.lineTo(center_x + badge_size, center_y)
    shield_path.lineTo(center_x, center_y + badge_size)
    shield_path.lineTo(center_x - badge_size, center_y)
    shield_path.closeSubpath()

    shield_grad = QLinearGradient(center_x, center_y - badge_size, center_x, center_y + badge_size)
    shield_grad.setColorAt(0.0, QColor("#3B82F6"))
    shield_grad.setColorAt(1.0, QColor("#1D4ED8"))
    painter.fillPath(shield_path, QBrush(shield_grad))

    shield_border = QPen(QColor("#FFFFFF"), max(1.0, 2.0 * scale))
    painter.strokePath(shield_path, shield_border)

    # Lightning / Delta symbol inside center badge
    bolt_path = QPainterPath()
    b_scale = scale * 0.9
    bx = center_x
    by = center_y
    bolt_path.moveTo(bx + 2*b_scale, by - 14*b_scale)
    bolt_path.lineTo(bx - 10*b_scale, by + 1*b_scale)
    bolt_path.lineTo(bx - 1*b_scale, by + 1*b_scale)
    bolt_path.lineTo(bx - 3*b_scale, by + 14*b_scale)
    bolt_path.lineTo(bx + 10*b_scale, by - 1*b_scale)
    bolt_path.lineTo(bx + 1*b_scale, by - 1*b_scale)
    bolt_path.closeSubpath()

    painter.fillPath(bolt_path, QBrush(QColor("#FBBF24"))) # Golden amber lightning
    painter.strokePath(bolt_path, QPen(QColor("#FFFBEB"), max(0.5, 1.0 * scale)))

    # 5. Bottom Label "TRINO DIFF" (for larger sizes >= 128)
    if size >= 128:
        font = QFont("Segoe UI", int(15 * scale), QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2.5 * scale)
        painter.setFont(font)
        painter.setPen(QColor("#E2E8F0"))
        text_rect = QRectF(0, size - 46 * scale, size, 24 * scale)
        painter.drawText(text_rect, Qt.AlignCenter, "TRINO DIFF")

    painter.end()
    return image


def save_ico_file(png_files: list, output_ico_path: str):
    """
    Combines multiple PNG images into a standard Windows ICO format file.
    """
    images_data = []
    for path, width, height in png_files:
        with open(path, "rb") as f:
            data = f.read()
        images_data.append((width, height, data))

    # ICO Header: 2 bytes reserved (0), 2 bytes type (1=ICO), 2 bytes count
    header = struct.pack("<HHH", 0, 1, len(images_data))
    
    # Calculate offset after header and all directory entries (16 bytes each)
    offset = 6 + 16 * len(images_data)
    
    dir_entries = []
    for width, height, data in images_data:
        w_byte = 0 if width >= 256 else width
        h_byte = 0 if height >= 256 else height
        size_bytes = len(data)
        # Entry: Width, Height, Colors (0), Reserved (0), Planes (1), BPP (32), Size (4B), Offset (4B)
        entry = struct.pack("<BBBBHHII", w_byte, h_byte, 0, 0, 1, 32, size_bytes, offset)
        dir_entries.append(entry)
        offset += size_bytes

    with open(output_ico_path, "wb") as f:
        f.write(header)
        for entry in dir_entries:
            f.write(entry)
        for _, _, data in images_data:
            f.write(data)


def main():
    res_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(res_dir, exist_ok=True)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    png_list = []

    for s in sizes:
        img = create_app_icon_image(s)
        filename = f"icon_{s}.png" if s != 256 else "app_icon.png"
        filepath = os.path.join(res_dir, filename)
        img.save(filepath, "PNG")
        png_list.append((filepath, s, s))
        if s == 256:
            # Also save as icon_256.png for uniformity
            img.save(os.path.join(res_dir, "icon_256.png"), "PNG")
        print(f"Generated {filepath} ({s}x{s})")

    # Combine into .ico
    ico_path = os.path.join(res_dir, "app_icon.ico")
    save_ico_file(png_list, ico_path)
    print(f"Generated Windows icon: {ico_path}")


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys
    # QApplication is required for QFont/QPainter operations
    app = QApplication.instance() or QApplication(sys.argv)
    main()
