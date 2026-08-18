#!/usr/bin/env python3
"""
Trino Database Diff Studio — PySide6 + QML GUI
===============================================
Main application launcher with instant splash screen and staged progress reporting.
"""

import os
import sys
import ctypes

# Ensure project root is on sys.path
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtCore import QUrl, Qt

from trino_diff.splash import SplashScreen


def main():
    # ── Windows Taskbar AppUserModelID ───────────────────────────────────────
    # Windows taskbar groups Python processes under the generic Python executable
    # unless an explicit AppUserModelID is assigned before creating windows.
    if sys.platform == "win32":
        try:
            app_id = "nera.trinodiff.studio.v1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception as e:
            print(f"[WARN] Failed to set AppUserModelID: {e}")

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    # ── 1. Create Qt Application Instance ────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName("Trino Diff Studio")
    app.setOrganizationName("Nera")

    # ── 2. Application & Taskbar Icons ───────────────────────────────────────
    res_dir = os.path.join(SCRIPT_DIR, "resources")
    ico_path = os.path.join(res_dir, "app_icon.ico")
    png_path = os.path.join(res_dir, "app_icon.png")

    app_icon = QIcon()
    if os.path.exists(ico_path):
        app_icon = QIcon(ico_path)
    elif os.path.exists(png_path):
        app_icon = QIcon(png_path)

    # Register multiple resolutions for crisp rendering across all screen DPI scales
    for size in [16, 24, 32, 48, 64, 128, 256]:
        sized_png = os.path.join(res_dir, f"icon_{size}.png")
        if os.path.exists(sized_png):
            app_icon.addFile(sized_png)

    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    # ── 3. Instant Splash Screen Display (< 200ms) ───────────────────────────
    no_splash = "--no-splash" in sys.argv
    splash = None
    if not no_splash:
        splash = SplashScreen(app_version="v1.0.0")
        splash.show()
        splash.set_progress(15, "Starting Trino Diff Studio runtime...")

    try:
        # ── 4. Staged Backend Initialization ─────────────────────────────────
        if splash:
            splash.set_progress(25, "Importing backend subsystem...")
        
        from trino_diff.backend.controller import BackendController

        progress_callback = splash.set_progress if splash else None
        backend = BackendController(progress_callback=progress_callback)

        # ── 5. Initialize QML Presentation Engine ────────────────────────────
        if splash:
            splash.set_progress(82, "Initializing QML presentation engine...")

        engine = QQmlApplicationEngine()

        # Expose backend to QML as a context property
        engine.rootContext().setContextProperty("backend", backend)

        # Add import paths for qmldir and relative views
        qml_dir = os.path.join(SCRIPT_DIR, "qml")
        engine.addImportPath(qml_dir)
        engine.addImportPath(SCRIPT_DIR)

        # ── 6. Load Root QML Window ──────────────────────────────────────────
        if splash:
            splash.set_progress(92, "Loading UI views & components...")

        main_qml = os.path.join(qml_dir, "Main.qml")
        engine.load(QUrl.fromLocalFile(main_qml))

        if not engine.rootObjects():
            err_msg = "Failed to load QML root object — check QML syntax or console logs."
            print(f"[ERROR] {err_msg}")
            if splash:
                splash.show_error(err_msg)
            sys.exit(1)

        root_window = engine.rootObjects()[0]
        if hasattr(root_window, "setIcon") and not app_icon.isNull():
            root_window.setIcon(app_icon)

        # ── 7. Transition from Splash to Main Window ─────────────────────────
        if splash:
            splash.finish(root_window)
        else:
            if hasattr(root_window, "show"):
                root_window.show()

        print("[INFO] Trino Diff Studio started successfully.")
        sys.exit(app.exec())

    except Exception as e:
        print(f"[FATAL] Startup error: {e}")
        if splash:
            splash.show_error(str(e))
        raise


if __name__ == "__main__":
    main()
