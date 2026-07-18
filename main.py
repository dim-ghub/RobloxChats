#!/usr/bin/env python3
import sys
import os
import argparse
import asyncio
import logging
import dateutil.parser
import time
from pathlib import Path
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QLabel, QDialog,
    QSystemTrayIcon, QMenu, QSplitter, QMessageBox, QListWidgetItem, QSizePolicy
)
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QPainterPath, QColor, QFont
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize

from desktop_notifier import DesktopNotifier, Icon, Button, Attachment
from desktop_notifier.common import Capability
import requests

from roblox_api import api

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

QSS_CUSTOM_WIDGETS = """
/* Remove backgrounds from lists so they inherit the OS theme */
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}

/* Floating Sidebar Container */
QWidget#sidebar_container {
    background-color: palette(base);
    border-radius: 16px;
    margin: 8px;
}

/* Chat Bubbles using standard Palette colors */
MessageWidget[is_self="true"] QWidget#bubble_container {
    background-color: palette(highlight);
    border-radius: 16px;
}
MessageWidget[is_self="false"] QWidget#bubble_container {
    background-color: palette(alternate-base);
    border-radius: 16px;
}
QLabel#self_msg_text {
    color: palette(highlighted-text);
    font-size: 14px;
    background: transparent;
}
QLabel#other_msg_text {
    color: palette(text);
    font-size: 14px;
    background: transparent;
}

/* Timestamp */
QLabel#timestamp_label {
    color: palette(placeholderText);
    font-size: 12px;
    font-weight: bold;
    padding: 16px 0px 8px 0px;
}

/* Input Area mimicking the AI app */
QWidget#input_container {
    background-color: palette(base);
    border-radius: 24px;
    border: 1px solid palette(mid);
}
QLineEdit#msg_input {
    background: transparent;
    color: palette(text);
    border: none;
    padding: 12px 16px;
    font-size: 14px;
}
QPushButton#send_btn {
    background-color: palette(button);
    color: palette(button-text);
    border-radius: 16px;
    font-size: 16px;
    font-weight: bold;
    margin: 4px;
    border: none;
}
QPushButton#send_btn:hover {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
"""

def get_circular_pixmap(image_path, size=48):
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
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return target

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RobloxChats Settings")
        self.setFixedSize(400, 200)
        
        layout = QVBoxLayout()
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("Enter .ROBLOSECURITY cookie...")
        self.cookie_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        if os.environ.get("ROBLOSECURITY"):
            self.cookie_input.setText(os.environ.get("ROBLOSECURITY"))
        
        self.login_btn = QPushButton("Save & Login")
        self.login_btn.clicked.connect(self.accept)
        
        layout.addStretch()
        layout.addWidget(QLabel("Roblox Cookie (.ROBLOSECURITY):"))
        layout.addWidget(self.cookie_input)
        layout.addWidget(self.login_btn)
        layout.addStretch()
        self.setLayout(layout)
        
    def get_cookie(self):
        return self.cookie_input.text().strip()

class ConversationWidget(QWidget):
    def __init__(self, title, preview_text, avatar_path=None, presence_type=0):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Avatar with Presence Dot
        avatar_lbl = QLabel()
        avatar_lbl.setPixmap(get_circular_pixmap(avatar_path, 40))
        avatar_lbl.setFixedSize(40, 40)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        # Presence status string
        presence_str = ""
        if presence_type == 1:
            presence_str = " (Online)"
        elif presence_type == 2:
            presence_str = " (In-Game)"
        elif presence_type == 3:
            presence_str = " (Studio)"
            
        title_lbl = QLabel(f"{title}{presence_str}")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        
        preview_lbl = QLabel()
        preview_lbl.setFont(QFont("Segoe UI", 10))
        preview_lbl.setStyleSheet("color: palette(placeholderText);")
        
        metrics = preview_lbl.fontMetrics()
        preview_text = preview_text.replace("\n", " ")
        elided = metrics.elidedText(preview_text, Qt.TextElideMode.ElideRight, 170)
        preview_lbl.setText(elided)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(preview_lbl)
        text_layout.addStretch()
        
        layout.addWidget(avatar_lbl)
        layout.addLayout(text_layout)
        layout.addStretch()
        
        self.setLayout(layout)

class MessageWidget(QWidget):
    def __init__(self, content, is_self, avatar_path=None):
        super().__init__()
        self.setProperty("is_self", "true" if is_self else "false")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        
        bubble_layout = QVBoxLayout()
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        
        content_lbl = QLabel(content)
        content_lbl.setWordWrap(True)
        content_lbl.setObjectName("self_msg_text" if is_self else "other_msg_text")
        
        bubble_layout.addWidget(content_lbl)
        
        bubble_container = QWidget()
        bubble_container.setObjectName("bubble_container")
        bubble_container.setLayout(bubble_layout)
        bubble_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        
        if is_self:
            layout.addStretch()
            layout.addWidget(bubble_container)
        else:
            if avatar_path:
                avatar_lbl = QLabel()
                avatar_lbl.setPixmap(get_circular_pixmap(avatar_path, 36))
                avatar_lbl.setFixedSize(36, 36)
                layout.addWidget(avatar_lbl, alignment=Qt.AlignmentFlag.AlignBottom)
            else:
                spacer = QWidget()
                spacer.setFixedSize(36, 36)
                layout.addWidget(spacer)
            layout.addWidget(bubble_container)
            layout.addStretch()
            
        self.setLayout(layout)

def extract_name(user_id, user_data_dict):
    str_id = str(user_id)
    if str_id in user_data_dict:
        u = user_data_dict[str_id]
        return u.get("display_name") or u.get("name") or u.get("combined_name") or str_id
    return str_id

def download_avatar_sync(user_id):
    avatar_url = api.get_user_avatar(user_id)
    if avatar_url:
        path = os.path.join(ASSETS_DIR, f"roblox_avatar_{user_id}.png")
        if not os.path.exists(path):
            try:
                res = requests.get(avatar_url, timeout=10)
                if res.status_code == 200:
                    with open(path, "wb") as f:
                        f.write(res.content)
            except Exception as e:
                logging.error(f"Avatar dl fail: {e}")
        return path
    return None

class ChatLoaderThread(QThread):
    finished_signal = pyqtSignal(list, dict)
    
    def __init__(self, conv_id, conv_map):
        super().__init__()
        self.conv_id = conv_id
        self.conv_map = conv_map
        
    def run(self):
        msgs = api.fetch_messages(self.conv_id)
        user_data = self.conv_map.get(self.conv_id, {}).get("user_data", {})
        self.finished_signal.emit(msgs, user_data)

class MessageSenderThread(QThread):
    finished_signal = pyqtSignal(bool)
    
    def __init__(self, conv_id, text):
        super().__init__()
        self.conv_id = conv_id
        self.text = text
        
    def run(self):
        success = api.send_message(self.conv_id, self.text)
        self.finished_signal.emit(success)

class PresencePollingThread(QThread):
    presence_signal = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.user_ids = set()
        
    def set_user_ids(self, user_ids):
        self.user_ids = set(user_ids)
        
    def run(self):
        while self.running:
            try:
                if self.user_ids:
                    presences = api.get_presence(list(self.user_ids))
                    pres_dict = {str(p["userId"]): p["userPresenceType"] for p in presences}
                    self.presence_signal.emit(pres_dict)
                api.send_heartbeat()
            except:
                pass
            
            for _ in range(15):
                if not self.running: return
                time.sleep(1)


class NotifierThread(QThread):
    new_message_signal = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        
    def run(self):
        asyncio.run(self.main_loop())
        
    async def main_loop(self):
        logo_path = os.path.join(ASSETS_DIR, "roblox_logo.png")
        if not os.path.exists(logo_path):
            try:
                res = requests.get("https://www.google.com/s2/favicons?domain=roblox.com&sz=128", timeout=10)
                if res.status_code == 200:
                    with open(logo_path, "wb") as f:
                        f.write(res.content)
            except:
                pass
                
        app_icon_obj = None
        if os.path.exists(logo_path):
            if sys.platform.startswith("linux"):
                app_icon_obj = Icon(name=logo_path)
            else:
                app_icon_obj = Icon(path=Path(logo_path))
                
        notifier = DesktopNotifier(
            app_name="RobloxChats",
            app_icon=app_icon_obj
        )
        
        if sys.platform.startswith("linux"):
            original_get_capabilities = notifier._backend.get_capabilities
            async def patched_get_capabilities():
                caps = await original_get_capabilities()
                return frozenset(c for c in caps if c != Capability.ON_CLICKED)
            notifier._backend.get_capabilities = patched_get_capabilities
            
        def on_clicked():
            pass
            
        seen_messages = set()
        
        while api.my_user_id is None:
            if not self.running: return
            await asyncio.sleep(1)
            
        try:
            convs = await asyncio.to_thread(api.fetch_conversations)
            for conv in convs[:5]:
                msgs = await asyncio.to_thread(api.fetch_messages, conv.get("id"))
                for m in msgs:
                    seen_messages.add(m.get("id"))
        except:
            pass
                
        while self.running:
            try:
                convs = await asyncio.to_thread(api.fetch_conversations)
                for conv in convs[:5]:
                    conv_id = conv.get("id")
                    msgs = await asyncio.to_thread(api.fetch_messages, conv_id)
                    for m in msgs:
                        msg_id = m.get("id")
                        if msg_id and msg_id not in seen_messages:
                            seen_messages.add(msg_id)
                            sender_id = m.get("sender_user_id", m.get("senderTargetId", m.get("senderUserId")))
                            
                            if not sender_id or str(sender_id) == str(api.my_user_id):
                                continue
                            
                            content = m.get("content", "")
                            user_data = conv.get("user_data", {})
                            sender_display = extract_name(sender_id, user_data)
                            
                            self.new_message_signal.emit({
                                "conv_id": conv_id,
                                "sender_id": str(sender_id),
                                "sender_display": sender_display,
                                "content": content,
                                "created_at": m.get("created_at")
                            })
                            
                            avatar_path = await asyncio.to_thread(download_avatar_sync, sender_id)
                            icon_obj = None
                            attachment_obj = None
                            if avatar_path:
                                if sys.platform.startswith("linux"):
                                    icon_obj = Icon(name=logo_path)
                                    attachment_obj = Attachment(path=Path(avatar_path))
                                else:
                                    icon_obj = Icon(path=Path(avatar_path))
                                    
                            await notifier.send(
                                title=sender_display,
                                message=content,
                                icon=icon_obj,
                                attachment=attachment_obj,
                                on_clicked=on_clicked,
                                buttons=[Button(title="Open in browser", on_pressed=on_clicked)]
                            )
            except:
                pass
                
            for _ in range(5):
                if not self.running: return
                await asyncio.sleep(1)


class MainWindow(QMainWindow):
    def __init__(self, start_minimized):
        super().__init__()
        self.setWindowTitle("RobloxChats")
        self.resize(1000, 700)
        
        self.setup_ui()
        
        load_dotenv()
        self.cookie = os.environ.get("ROBLOSECURITY")
        
        if not start_minimized:
            self.show()
            
        self.typing_timer = QTimer()
        self.typing_timer.setInterval(4000)
        self.typing_timer.timeout.connect(self.send_typing_indicator)
            
        QTimer.singleShot(100, self.post_init)
        
    def setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Floating Sidebar
        sidebar_container = QWidget()
        sidebar_container.setObjectName("sidebar_container")
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        
        self.conv_list = QListWidget()
        self.conv_list.itemClicked.connect(self.on_conv_selected)
        sidebar_layout.addWidget(self.conv_list)
        sidebar_container.setLayout(sidebar_layout)
        
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        
        self.msg_list = QListWidget()
        self.msg_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        
        input_container = QWidget()
        input_container.setObjectName("input_container")
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)
        
        self.msg_input = QLineEdit()
        self.msg_input.setObjectName("msg_input")
        self.msg_input.setPlaceholderText("Send a message")
        self.msg_input.returnPressed.connect(self.send_message)
        self.msg_input.textChanged.connect(self.on_input_changed)
        
        self.send_btn = QPushButton("↑")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(self.send_btn)
        input_container.setLayout(input_layout)
        
        bottom_panel = QVBoxLayout()
        bottom_panel.setContentsMargins(24, 16, 24, 24)
        bottom_panel.addWidget(input_container)
        
        right_panel.addWidget(self.msg_list)
        right_panel.addLayout(bottom_panel)
        
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(sidebar_container)
        splitter.addWidget(right_widget)
        splitter.setSizes([320, 680])
        splitter.setHandleWidth(1)
        
        layout.addWidget(splitter)
        central.setLayout(layout)
        self.setCentralWidget(central)
        
        self.current_conv_id = None
        self.conv_map = {}
        self.presence_map = {}
        
    def post_init(self):
        self.setup_tray()
        
        self.notifier_thread = NotifierThread()
        self.notifier_thread.new_message_signal.connect(self.on_new_message)
        self.notifier_thread.start()
        
        self.presence_thread = PresencePollingThread()
        self.presence_thread.presence_signal.connect(self.on_presence_updated)
        self.presence_thread.start()
        
        self.check_login()
        
    def check_login(self):
        valid = False
        if self.cookie:
            api.update_cookie(self.cookie)
            valid = api.get_current_user() is not None
            
        if not valid:
            dialog = SettingsDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_cookie = dialog.get_cookie()
                api.update_cookie(new_cookie)
                with open(".env", "w") as f:
                    f.write(f"ROBLOSECURITY={new_cookie}\n")
                self.cookie = new_cookie
                if not api.get_current_user():
                    QMessageBox.warning(self, "Error", "Invalid cookie. Restart app to try again.")
                    return
            else:
                return
                
        self.refresh_chats()
            
    def refresh_chats(self):
        self.conv_list.clear()
        convs = api.fetch_conversations()
        
        tracked_users = set()
        
        for conv in convs:
            cid = conv.get("id")
            self.conv_map[cid] = conv
            
            user_data = conv.get("user_data", {})
            title = conv.get("name") or conv.get("title")
            avatar_path = None
            presence_type = 0
            
            participants = conv.get("participant_user_ids", [])
            if not participants and "participants" in conv:
                participants = [p.get("targetId") for p in conv["participants"]]
                
            for p_id in participants:
                if str(p_id) != str(api.my_user_id):
                    tracked_users.add(p_id)
            
            if not title:
                names = []
                for p_id in participants:
                    if str(p_id) != str(api.my_user_id):
                        names.append(extract_name(p_id, user_data))
                        if not avatar_path:
                            avatar_path = download_avatar_sync(p_id)
                            presence_type = self.presence_map.get(str(p_id), 0)
                title = ", ".join(names) if names else cid
            else:
                for u in user_data.values():
                    uid = u.get("id")
                    if str(uid) != str(api.my_user_id):
                        avatar_path = download_avatar_sync(uid)
                        presence_type = self.presence_map.get(str(uid), 0)
                        break

            preview = conv.get("preview_message", {}).get("content", "No messages yet")
            
            item = QListWidgetItem()
            widget = ConversationWidget(title, preview, avatar_path, presence_type)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, cid)
            
            self.conv_list.addItem(item)
            self.conv_list.setItemWidget(item, widget)
            
        self.presence_thread.set_user_ids(tracked_users)
            
    def on_presence_updated(self, pres_dict):
        # Only refresh if presence changed
        changed = False
        for uid, p_type in pres_dict.items():
            if self.presence_map.get(uid) != p_type:
                self.presence_map[uid] = p_type
                changed = True
        if changed:
            self.refresh_chats()
            
    def on_conv_selected(self, item):
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self.current_conv_id = cid
            self.msg_list.clear()
            loading_item = QListWidgetItem()
            lbl = QLabel("Loading messages...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: palette(placeholderText); padding: 20px;")
            loading_item.setSizeHint(lbl.sizeHint())
            self.msg_list.addItem(loading_item)
            self.msg_list.setItemWidget(loading_item, lbl)
            
            self.loader_thread = ChatLoaderThread(cid, self.conv_map)
            self.loader_thread.finished_signal.connect(self.on_messages_loaded)
            self.loader_thread.start()
            
    def on_messages_loaded(self, msgs, user_data):
        self.msg_list.clear()
        
        last_time = None
        last_sender = None
        
        for m in reversed(msgs):
            sender_id = str(m.get("sender_user_id", m.get("senderTargetId", m.get("senderUserId"))))
            content = m.get("content", "")
            created_at_str = m.get("created_at")
            
            if created_at_str:
                dt = dateutil.parser.isoparse(created_at_str)
                if last_time is None or (dt - last_time).total_seconds() > 3600:
                    ts_item = QListWidgetItem()
                    lbl = QLabel(dt.strftime("%B %d, %Y %I:%M %p"))
                    lbl.setObjectName("timestamp_label")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    ts_item.setSizeHint(lbl.sizeHint())
                    self.msg_list.addItem(ts_item)
                    self.msg_list.setItemWidget(ts_item, lbl)
                    last_sender = None
                last_time = dt
            
            is_self = (sender_id == str(api.my_user_id))
            
            avatar_path = None
            if not is_self and sender_id != last_sender:
                avatar_path = download_avatar_sync(sender_id)
                
            item = QListWidgetItem()
            widget = MessageWidget(content, is_self, avatar_path)
            
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            
            item.setSizeHint(widget.sizeHint())
            
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, widget)
            last_sender = sender_id
            
        self.msg_list.scrollToBottom()
        
    def on_input_changed(self, text):
        if text and self.current_conv_id:
            if not self.typing_timer.isActive():
                self.send_typing_indicator()
                self.typing_timer.start()
        else:
            self.typing_timer.stop()
            
    def send_typing_indicator(self):
        if self.current_conv_id:
            # We fire and forget this network request on a throwaway thread to avoid blocking GUI
            t = QThread.create(lambda: api.update_typing_status(self.current_conv_id, True))
            t.start()
            
    def send_message(self):
        if not self.current_conv_id: return
        text = self.msg_input.text().strip()
        if not text: return
        
        self.msg_input.clear()
        
        # Optimistic UI update
        item = QListWidgetItem()
        widget = MessageWidget(text, True, None)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        item.setSizeHint(widget.sizeHint())
        self.msg_list.addItem(item)
        self.msg_list.setItemWidget(item, widget)
        self.msg_list.scrollToBottom()
        
        # Background send
        self.sender_thread = MessageSenderThread(self.current_conv_id, text)
        # We no longer reload everything on success since we optimistically updated.
        # But we could optionally handle failure if success == False
        self.sender_thread.start()
        
    def on_new_message(self, data):
        if self.current_conv_id == data["conv_id"]:
            is_self = data.get("sender_id") == str(api.my_user_id)
            if is_self:
                return # Already handled by optimistic UI update
                
            avatar_path = os.path.join(ASSETS_DIR, f"roblox_avatar_{data.get('sender_id')}.png")
            item = QListWidgetItem()
            widget = MessageWidget(data["content"], is_self, avatar_path)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            item.setSizeHint(widget.sizeHint())
            
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, widget)
            self.msg_list.scrollToBottom()
            
            self.refresh_chats()
            
    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        
        logo_path = os.path.join(ASSETS_DIR, "roblox_logo.png")
        if os.path.exists(logo_path):
            self.tray.setIcon(QIcon(logo_path))
        else:
            self.tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
            
        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            logging.warning("System tray is not available on this environment.")
        
        self.tray.activated.connect(self.tray_icon_activated)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()
        
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        # Removed tray notification as requested

def main():
    parser = argparse.ArgumentParser(description="RobloxChats Desktop Client")
    parser.add_argument("-m", "--minimized", action="store_true", help="Start minimized in system tray")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS_CUSTOM_WIDGETS)
    
    window = MainWindow(args.minimized)
    
    def on_quit():
        window.notifier_thread.running = False
        window.notifier_thread.wait()
        window.presence_thread.running = False
        window.presence_thread.wait()
        
    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
