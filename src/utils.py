import json
import logging
import os
import stat
import sys
import time

import requests

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen, QPalette
from PyQt6.QtCore import Qt

from constants import ASSETS_DIR, CONFIG_PATH, SCRIPT_DIR


def get_circular_pixmap(image_path, size=48, presence_type=0, unread=False):
    if not image_path or not os.path.exists(image_path):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
    else:
        pixmap = QPixmap(image_path).scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
    
    target = QPixmap(size, size)
    target.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    
    bg_color = QApplication.palette().color(QPalette.ColorRole.Button)
    if bg_color.lightness() < 128:
        bg_color = bg_color.lighter(120)
    else:
        bg_color = bg_color.darker(110)
    painter.fillPath(path, bg_color)
    
    painter.drawPixmap(0, 0, pixmap)
    painter.setClipPath(QPainterPath())
    
    if presence_type > 0:
        colors = {1: QColor("#00FF00"), 2: QColor("#0096FF"), 3: QColor("#FFA500")}
        color = colors.get(presence_type, QColor("#00FF00"))
        r = size // 5
        painter.setBrush(color)
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawEllipse(size - r*2 - 2, size - r*2 - 2, r*2, r*2)
        
    if unread:
        r = size // 5
        painter.setBrush(QColor("#FF0000"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, r*2, r*2)
        
    painter.end()
    return target


def load_config():
    defaults = {"minimize_to_tray": True}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            defaults.update(data)
        except Exception:
            pass
    return defaults


def save_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def extract_name(user_id, user_data_dict):
    str_id = str(user_id)
    if str_id in user_data_dict:
        u = user_data_dict[str_id]
        return u.get("display_name") or u.get("name") or u.get("combined_name") or str_id
    return str_id


def download_avatar_sync(user_id):
    from roblox_api import api
    path = os.path.join(ASSETS_DIR, f"roblox_avatar_{user_id}.png")
    if os.path.exists(path):
        mtime = os.path.getmtime(path)
        if time.time() - mtime < 3600:
            return path
            
    avatar_url = api.get_user_avatar(user_id)
    if avatar_url:
        try:
            res = requests.get(avatar_url, timeout=10)
            if res.status_code == 200:
                with open(path, "wb") as f:
                    f.write(res.content)
        except Exception as e:
            logging.error(f"Avatar dl fail: {e}")
        return path
    return None


def install_desktop_shortcut():
    import shutil

    app_path = os.path.abspath(os.path.join(SCRIPT_DIR, "main.py"))
    os.chmod(app_path, os.stat(app_path).st_mode | stat.S_IEXEC)

    bin_dir = os.path.expanduser("~/.local/bin")
    os.makedirs(bin_dir, exist_ok=True)
    launcher = os.path.join(bin_dir, "robloxchats")
    with open(launcher, "w") as f:
        f.write(f"#!/bin/sh\nexec /usr/bin/env python3 {app_path} \"$@\"\n")
    os.chmod(launcher, os.stat(launcher).st_mode | stat.S_IEXEC)

    icon_line = "Icon=utilities-terminal"
    src_icon = os.path.join(ASSETS_DIR, "roblox_logo.png")
    if os.path.exists(src_icon):
        icon_dir = os.path.expanduser("~/.local/share/icons/hicolor/128x128/apps")
        os.makedirs(icon_dir, exist_ok=True)
        dest_icon = os.path.join(icon_dir, "robloxchats.png")
        shutil.copy2(src_icon, dest_icon)
        icon_line = "Icon=robloxchats"

    desktop_content = f"""[Desktop Entry]
Type=Application
Name=RobloxChats
Exec=robloxchats
{icon_line}
Terminal=false
Categories=Network;Chat;
"""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    desktop_file = os.path.join(apps_dir, "robloxchats.desktop")
    with open(desktop_file, "w") as f:
        f.write(desktop_content)
    print(f"Installed .desktop shortcut to {desktop_file}")
    sys.exit(0)
