#!/usr/bin/env python3
"""
Trino Database Diff Studio — Modern Splash Screen
=================================================
A sleek, dark-themed splash screen with real-time staged progress feedback,
brand typography, drop shadow, and smooth transitions.
"""

import os
import sys
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QPainterPath, QLinearGradient, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QGraphicsDropShadowEffect,
    QApplication,
    QFrame,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.path.join(SCRIPT_DIR, "resources")


class SplashScreen(QWidget):
    """
    Modern frameless dark-mode splash screen.
    """

    def __init__(self, app_version: str = "v1.0.0"):
        super().__init__()
        self._version = app_version
        self._progress = 0
        self._fade_anim = None

        # Window flags: Frameless, translucent, always on top during boot
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.setFixedSize(540, 320)
        self._init_ui()
        self._center_on_screen()

    def _init_ui(self):
        # Outer container layout for drop shadow padding
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(15, 15, 15, 15)

        # Card container
        self.card = QFrame(self)
        self.card.setObjectName("splashCard")
        self.card.setStyleSheet("""
            QFrame#splashCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0C0D0E, stop:1 #131416);
                border: 1px solid #2D2F36;
                border-radius: 16px;
            }
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        # Inner layout
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 26, 28, 22)
        card_layout.setSpacing(0)

        # ── Header Row (Logo + Titles) ────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(18)

        # Logo icon
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(58, 58)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_path = os.path.join(RES_DIR, "icon_128.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(RES_DIR, "app_icon.png")
        
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            scaled = pixmap.scaled(
                58, 58,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.logo_label.setPixmap(scaled)

        header_layout.addWidget(self.logo_label)

        # Title column
        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        title_label = QLabel("Trino Diff Studio")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #F9FAFB; background: transparent;")

        tagline_color = "#FACC15"
        pct_color = "#FACC15"
        grad_stop0 = "#FACC15"
        grad_stop1 = "#F59E0B"
        grad_stop2 = "#EAB308"

        tagline_label = QLabel("Oracle ⇄ Postgres Data Verification Engine")
        tagline_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Normal))
        tagline_label.setStyleSheet(f"color: {tagline_color}; background: transparent;")

        title_col.addWidget(title_label)
        title_col.addWidget(tagline_label)
        header_layout.addLayout(title_col)
        header_layout.addStretch()

        card_layout.addLayout(header_layout)
        card_layout.addSpacing(28)

        # ── Middle Feature Highlight / Badge ──────────────────────────────────
        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(8)

        feature_badge = QLabel("  ⚡ High-Performance Automated SQL Query Diffing  ")
        feature_badge.setFont(QFont("Segoe UI", 9))
        feature_badge.setStyleSheet("""
            color: #9CA3AF;
            background-color: #141518;
            border: 1px solid #212328;
            border-radius: 6px;
            padding: 4px 8px;
        """)
        badge_layout.addWidget(feature_badge)
        badge_layout.addStretch()
        card_layout.addLayout(badge_layout)

        card_layout.addStretch()

        # ── Status and Percentage Row ─────────────────────────────────────────
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self.status_label = QLabel("Starting Trino Diff Studio runtime...")
        self.status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Normal))
        self.status_label.setStyleSheet("color: #9CA3AF; background: transparent;")

        self.pct_label = QLabel("0%")
        self.pct_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.pct_label.setStyleSheet(f"color: {pct_color}; background: transparent;")
        self.pct_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.pct_label)
        card_layout.addLayout(status_row)
        card_layout.addSpacing(8)

        # ── Progress Bar ──────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #141518;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {grad_stop0}, stop:0.7 {grad_stop1}, stop:1 {grad_stop2});
                border-radius: 3px;
            }}
        """)
        card_layout.addWidget(self.progress_bar)
        card_layout.addSpacing(14)

        # ── Footer Info Row ───────────────────────────────────────────────────
        footer_layout = QHBoxLayout()
        
        version_label = QLabel(f"Nera Automations • {self._version}")
        version_label.setFont(QFont("Segoe UI", 8))
        version_label.setStyleSheet("color: #64748B; background: transparent;")
        
        env_label = QLabel("PySide6 • Qt Quick Engine")
        env_label.setFont(QFont("Segoe UI", 8))
        env_label.setStyleSheet("color: #475569; background: transparent;")

        footer_layout.addWidget(version_label)
        footer_layout.addStretch()
        footer_layout.addWidget(env_label)
        card_layout.addLayout(footer_layout)

        root_layout.addWidget(self.card)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            y = (geo.height() - self.height()) // 2 + geo.y()
            self.move(x, y)

    def set_progress(self, percentage: int, message: str = ""):
        """
        Update the progress bar value (0-100) and status description text.
        Processes Qt events immediately to ensure responsive UI updates.
        """
        self._progress = max(0, min(100, int(percentage)))
        self.progress_bar.setValue(self._progress)
        self.pct_label.setText(f"{self._progress}%")
        if message:
            self.status_label.setText(message)
        
        # Flush pending GUI paint events immediately
        QApplication.processEvents()

    def show_error(self, error_message: str):
        """
        Display a fatal error on the splash screen in red.
        """
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setStyleSheet("color: #EF4444; background: transparent;")
        self.pct_label.setText("Failed")
        self.pct_label.setStyleSheet("color: #EF4444; background: transparent;")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #141518;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #EF4444;
                border-radius: 3px;
            }
        """)
        QApplication.processEvents()

    def finish(self, main_window=None):
        """
        Smoothly closes the splash screen and transfers focus to the main window.
        """
        self.set_progress(100, "Ready! Launching workspace...")
        
        # Brief transition delay to show 100% completion
        QTimer.singleShot(150, self._do_close_and_show)
        self._target_window = main_window

    def _do_close_and_show(self):
        if hasattr(self, "_target_window") and self._target_window:
            try:
                if hasattr(self._target_window, "show"):
                    self._target_window.show()
                if hasattr(self._target_window, "raise_"):
                    self._target_window.raise_()
                if hasattr(self._target_window, "requestActivate"):
                    self._target_window.requestActivate()
            except Exception as e:
                print(f"[WARN] Error raising main window: {e}")

        self.close()
