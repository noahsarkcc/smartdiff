"""
System tray integration for SmartDiff.

Hides the console window and provides a tray icon with a menu:
- Open browser
- Show log file
- Open workspace directory
- Quit

`pystray` runs its event loop on the calling (main) thread, so server.py
starts Flask in a background thread and hands control here. When `pystray`
or `Pillow` are missing, `start_tray()` returns False so the caller can
fall back to the legacy console mode.
"""
import os
import sys
import webbrowser

try:
    import pystray
    from pystray import MenuItem as Item, Menu
    from PIL import Image, ImageDraw
    AVAILABLE = True
except Exception:
    AVAILABLE = False


def _make_icon_image(size: int = 64) -> "Image.Image":
    """Generate a simple SmartDiff icon (rounded square + 'SD' text)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 16)
    radius = max(4, size // 8)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=(35, 134, 54, 255),       # GitHub green
        outline=(255, 255, 255, 255),
        width=max(1, size // 32),
    )
    # Two thin diff bars (one short, one long)
    bar_h = max(2, size // 14)
    left = size // 4
    right = size - size // 4
    mid_y = size // 2
    draw.rectangle(
        [left, mid_y - bar_h * 2, left + (right - left) // 2, mid_y - bar_h],
        fill=(255, 255, 255, 230),
    )
    draw.rectangle(
        [left, mid_y + bar_h, right, mid_y + bar_h * 2],
        fill=(255, 255, 255, 230),
    )
    return img


def start_tray(port: int, log_path: str, workspace_resolver, shutdown_fn,
               app_name: str = "SmartDiff") -> bool:
    """Launch the tray icon. Blocks until the user quits.

    - port: Flask server port (for the "Open browser" menu item).
    - log_path: absolute path to the server log file.
    - workspace_resolver: callable returning the current workspace directory,
      or empty string when none is configured.
    - shutdown_fn: callable invoked when user picks "Quit".
    """
    if not AVAILABLE:
        return False

    def _open_browser(_icon=None, _item=None):
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    def _open_log(_icon=None, _item=None):
        # Prefer the in-app /log viewer: newest-first, auto-refresh, dark.
        # Fall back to the raw file (Notepad / xdg-open) only when the
        # browser cannot be launched.
        try:
            webbrowser.open(f"http://localhost:{port}/log")
            return
        except Exception:
            pass
        try:
            if log_path and os.path.isfile(log_path):
                if os.name == "nt":
                    os.startfile(log_path)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", log_path])
        except Exception:
            pass

    def _open_workspace(_icon=None, _item=None):
        try:
            wd = workspace_resolver() if callable(workspace_resolver) else ""
            if wd and os.path.isdir(wd):
                if os.name == "nt":
                    os.startfile(os.path.normpath(wd))
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", wd])
        except Exception:
            pass

    def _quit(icon, _item=None):
        try:
            if callable(shutdown_fn):
                shutdown_fn()
        finally:
            try:
                icon.stop()
            except Exception:
                pass
            # Hard-exit because Flask's dev server has no clean shutdown when
            # bound to 127.0.0.1 without the Werkzeug shutdown hook.
            os._exit(0)

    menu = Menu(
        Item("打开浏览器 / Open browser", _open_browser, default=True),
        Item("显示日志 / Show log", _open_log),
        Item("打开工作目录 / Open workspace", _open_workspace),
        Menu.SEPARATOR,
        Item("退出 / Quit", _quit),
    )

    icon = pystray.Icon(app_name, _make_icon_image(64), app_name, menu)
    icon.run()
    return True
