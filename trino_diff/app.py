#!/usr/bin/env python3
"""
Trino Database Diff Studio — PySide6 + QML GUI
===============================================
Main application launcher.
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

from trino_diff.backend.controller import BackendController


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

    app = QApplication(sys.argv)
    app.setApplicationName("Trino Diff Studio")
    app.setOrganizationName("Nera")

    # ── Application & Taskbar Icon ───────────────────────────────────────────
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

    # Create backend bridge controller
    backend = BackendController()

    # ── QML engine ───────────────────────────────────────────────────────────
    engine = QQmlApplicationEngine()

    # Expose backend to QML as a context property
    engine.rootContext().setContextProperty("backend", backend)

    # Add the 'qml' directory itself as an import path.
    # The qmldir file lives inside it, registering the singleton Theme and
    # all component/view types under the module name "TrinoDiffQml".
    # We also add the PARENT of qml/ so that relative imports (".", "./components")
    # inside the view files still resolve correctly.
    qml_dir = os.path.join(SCRIPT_DIR, "qml")
    engine.addImportPath(qml_dir)          # for qmldir-based imports
    engine.addImportPath(SCRIPT_DIR)       # so 'import "."' from qml/ resolves to qml/

    # Load the root QML file
    main_qml = os.path.join(qml_dir, "Main.qml")
    engine.load(QUrl.fromLocalFile(main_qml))

    if not engine.rootObjects():
        print("[ERROR] Failed to load QML root object — check QML console output above.")
        sys.exit(1)

    # Explicitly set icon on root window if supported
    root_window = engine.rootObjects()[0]
    if hasattr(root_window, "setIcon") and not app_icon.isNull():
        root_window.setIcon(app_icon)

    print("[INFO] Trino Diff Studio started successfully.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

