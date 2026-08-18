import os
import sys
import threading
import subprocess
from PySide6.QtWidgets import QSystemTrayIcon
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt


class WindowsNotifier:
    """
    Windows Notification Manager for Trino Diff Studio.
    Uses Qt's QSystemTrayIcon (integrating with Windows 10/11 Action Center / Toast),
    with an asynchronous PowerShell fallback if system tray is unavailable.
    """

    def __init__(self):
        self._tray = None
        self._init_tray()

    def _init_tray(self):
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self._tray = QSystemTrayIcon()

                # Locate resources directory
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                res_dir = os.path.join(os.path.dirname(backend_dir), "resources")
                ico_path = os.path.join(res_dir, "app_icon.ico")
                png_path = os.path.join(res_dir, "icon_32.png")
                main_png = os.path.join(res_dir, "app_icon.png")

                tray_icon = QIcon()
                if os.path.exists(ico_path):
                    tray_icon = QIcon(ico_path)
                elif os.path.exists(png_path):
                    tray_icon = QIcon(png_path)
                elif os.path.exists(main_png):
                    tray_icon = QIcon(main_png)

                # Add individual resolutions for crisp tray scaling
                for size in [16, 24, 32, 48, 64]:
                    sized_png = os.path.join(res_dir, f"icon_{size}.png")
                    if os.path.exists(sized_png):
                        tray_icon.addFile(sized_png)

                if not tray_icon.isNull():
                    self._tray.setIcon(tray_icon)
                self._tray.setToolTip("Trino Diff Studio")
                self._tray.show()
        except Exception as e:
            print(f"[WARN] Could not initialize QSystemTrayIcon: {e}")

    def notify(self, title: str, message: str, level: str = "info"):
        """
        Display a native Windows notification.
        level: 'info' | 'success' | 'warning' | 'error'
        """
        # Try QSystemTrayIcon first
        if self._tray and QSystemTrayIcon.isSystemTrayAvailable():
            icon = QSystemTrayIcon.Information
            if level == "error":
                icon = QSystemTrayIcon.Critical
            elif level in ("warning", "warn"):
                icon = QSystemTrayIcon.Warning

            self._tray.showMessage(title, message, icon, 5000)
            return

        # Fallback to Windows PowerShell Toast in a background daemon thread
        if sys.platform == "win32":
            threading.Thread(
                target=self._powershell_notify,
                args=(title, message),
                daemon=True
            ).start()

    def _powershell_notify(self, title: str, message: str):
        try:
            escaped_title = title.replace('"', '`"').replace("'", "''")
            escaped_msg = message.replace('"', '`"').replace("'", "''")

            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastText02">
                        <text id="1">{escaped_title}</text>
                        <text id="2">{escaped_msg}</text>
                    </binding>
                </visual>
            </toast>
"@
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Trino Diff Studio")
            $notifier.Show($toast)
            """
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                timeout=5
            )
        except Exception:
            pass
