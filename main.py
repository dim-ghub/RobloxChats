#!/usr/bin/env python3
import sys
import os
import argparse
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLineEdit, QPushButton, QListWidget, QLabel,
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

QSS_THEME = """
QMainWindow, QTabWidget::pane {
    background-color: #313338;
    border: none;
}
QTabBar::tab {
    background-color: #1e1f22;
    color: #949ba4;
    padding: 8px 16px;
    border: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #313338;
    color: #ffffff;
}
QWidget {
    color: #dbdee1;
    font-family: 'Segoe UI', Inter, Helvetica, sans-serif;
    font-size: 14px;
}
QLineEdit {
    background-color: #383a40;
    color: #dbdee1;
    border: none;
    border-radius: 8px;
    padding: 12px;
}
QPushButton {
    background-color: #5865f2;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #4752c4;
}
QListWidget {
    background-color: #2b2d31;
    border: none;
    outline: none;
}
QListWidget::item:selected {
    background-color: #3f4147;
    border-radius: 4px;
}
QListWidget::item:hover {
    background-color: #35373c;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: #1e1f22;
    width: 2px;
}
"""

def get_circular_pixmap(image_path, size=48):
    if not image_path or not os.path.exists(image_path):
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("#313338"))
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

class ConversationWidget(QWidget):
    def __init__(self, title, preview_text, avatar_path=None):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        
        avatar_lbl = QLabel()
        avatar_lbl.setPixmap(get_circular_pixmap(avatar_path, 40))
        avatar_lbl.setFixedSize(40, 40)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #dbdee1;")
        
        preview_lbl = QLabel()
        preview_lbl.setStyleSheet("color: #949ba4;")
        preview_lbl.setFont(QFont("Segoe UI", 10))
        
        # Elide text
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
    def __init__(self, content, is_self, sender_name=None, avatar_path=None):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        
        bubble_color = "#4752c4" if is_self else "#383a40"
        text_color = "#ffffff" if is_self else "#dbdee1"
        
        bubble_layout = QVBoxLayout()
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        
        if not is_self and sender_name:
            name_lbl = QLabel(sender_name)
            name_lbl.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: bold;")
            bubble_layout.addWidget(name_lbl)
            
        content_lbl = QLabel(content)
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet(f"color: {text_color}; font-size: 14px; background: transparent;")
        
        bubble_layout.addWidget(content_lbl)
        
        bubble_container = QWidget()
        bubble_container.setLayout(bubble_layout)
        bubble_container.setStyleSheet(f"""
            QWidget {{
                background-color: {bubble_color};
                border-radius: 8px;
            }}
        """)
        bubble_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        
        if is_self:
            layout.addStretch()
            layout.addWidget(bubble_container)
        else:
            if avatar_path:
                avatar_lbl = QLabel()
                avatar_lbl.setPixmap(get_circular_pixmap(avatar_path, 32))
                avatar_lbl.setFixedSize(32, 32)
                layout.addWidget(avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)
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
            except Exception as e:
                logging.error(f"Failed to download logo: {e}")
                
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
        except Exception as e:
            logging.error(f"Error pre-populating messages: {e}")
                
        logging.info("Started background notification listener.")
        
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
                                "content": content
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
            except Exception as e:
                logging.error(f"Polling error: {e}")
                
            for _ in range(5):
                if not self.running: return
                await asyncio.sleep(1)


class MainWindow(QMainWindow):
    def __init__(self, start_minimized):
        super().__init__()
        self.setWindowTitle("RobloxChats")
        self.resize(900, 650)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.setup_login_tab()
        self.setup_chat_tab()
        
        load_dotenv()
        self.cookie = os.environ.get("ROBLOSECURITY")
        if self.cookie:
            self.cookie_input.setText(self.cookie)
            
        if not start_minimized:
            self.show()
            
        QTimer.singleShot(100, self.post_init)
        
    def post_init(self):
        self.setup_tray()
        
        self.notifier_thread = NotifierThread()
        self.notifier_thread.new_message_signal.connect(self.on_new_message)
        self.notifier_thread.start()
        
        if self.cookie:
            self.login()
            
    def setup_login_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("Enter .ROBLOSECURITY cookie...")
        self.cookie_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.login)
        
        self.status_label = QLabel("Not logged in.")
        
        layout.addStretch()
        layout.addWidget(QLabel("Roblox Cookie (.ROBLOSECURITY):"))
        layout.addWidget(self.cookie_input)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.status_label)
        layout.addStretch()
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Login")
        
    def login(self):
        cookie = self.cookie_input.text().strip()
        if not cookie: return
        api.update_cookie(cookie)
        
        with open(".env", "w") as f:
            f.write(f"ROBLOSECURITY={cookie}\n")
            
        user_id = api.get_current_user()
        if user_id:
            self.status_label.setText(f"Logged in successfully. User ID: {user_id}")
            self.refresh_chats()
            self.tabs.setCurrentIndex(1)
        else:
            self.status_label.setText("Login failed. Check cookie validity.")
            
    def setup_chat_tab(self):
        tab = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.conv_list = QListWidget()
        self.conv_list.itemClicked.connect(self.on_conv_selected)
        
        right_panel = QVBoxLayout()
        
        self.msg_list = QListWidget()
        self.msg_list.setStyleSheet("background-color: #313338;")
        self.msg_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(16, 8, 16, 16)
        
        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("Message...")
        self.msg_input.returnPressed.connect(self.send_message)
        
        input_layout.addWidget(self.msg_input)
        
        right_panel.addWidget(self.msg_list)
        right_panel.addLayout(input_layout)
        
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #313338;")
        right_widget.setLayout(right_panel)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.conv_list)
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 600])
        splitter.setHandleWidth(1)
        
        layout.addWidget(splitter)
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Chats")
        
        self.current_conv_id = None
        self.conv_map = {}
        
    def refresh_chats(self):
        self.conv_list.clear()
        convs = api.fetch_conversations()
        
        for conv in convs:
            cid = conv.get("id")
            self.conv_map[cid] = conv
            
            user_data = conv.get("user_data", {})
            title = conv.get("name") or conv.get("title")
            avatar_path = None
            
            if not title:
                # generate title
                participants = conv.get("participant_user_ids", [])
                if not participants and "participants" in conv:
                    participants = [p.get("targetId") for p in conv["participants"]]
                    
                names = []
                for p_id in participants:
                    if str(p_id) != str(api.my_user_id):
                        names.append(extract_name(p_id, user_data))
                        if not avatar_path:
                            avatar_path = download_avatar_sync(p_id)
                title = ", ".join(names) if names else cid
            else:
                # Group chat, try to find an avatar of a participant
                for u in user_data.values():
                    uid = u.get("id")
                    if str(uid) != str(api.my_user_id):
                        avatar_path = download_avatar_sync(uid)
                        break

            preview = conv.get("preview_message", {}).get("content", "No messages yet")
            
            item = QListWidgetItem()
            widget = ConversationWidget(title, preview, avatar_path)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, cid)
            
            self.conv_list.addItem(item)
            self.conv_list.setItemWidget(item, widget)
            
    def on_conv_selected(self, item):
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self.current_conv_id = cid
            self.load_messages(cid)
                
    def load_messages(self, cid):
        self.msg_list.clear()
        msgs = api.fetch_messages(cid)
        user_data = self.conv_map.get(cid, {}).get("user_data", {})
        
        for m in reversed(msgs):
            sender_id = str(m.get("sender_user_id", m.get("senderTargetId", m.get("senderUserId"))))
            content = m.get("content", "")
            
            is_self = (sender_id == str(api.my_user_id))
            
            if not is_self:
                sender_display = extract_name(sender_id, user_data)
                avatar_path = download_avatar_sync(sender_id)
            else:
                sender_display = None
                avatar_path = None
                
            item = QListWidgetItem()
            widget = MessageWidget(content, is_self, sender_display, avatar_path)
            item.setSizeHint(widget.sizeHint())
            
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, widget)
            
        self.msg_list.scrollToBottom()
            
    def send_message(self):
        if not self.current_conv_id: return
        text = self.msg_input.text().strip()
        if not text: return
        
        if api.send_message(self.current_conv_id, text):
            self.msg_input.clear()
            self.load_messages(self.current_conv_id)
        else:
            QMessageBox.warning(self, "Error", "Failed to send message.")
            
    def on_new_message(self, data):
        if self.current_conv_id == data["conv_id"]:
            is_self = data.get("sender_id") == str(api.my_user_id)
            avatar_path = None
            if not is_self:
                avatar_path = os.path.join(ASSETS_DIR, f"roblox_avatar_{data.get('sender_id')}.png")
                
            item = QListWidgetItem()
            widget = MessageWidget(data["content"], is_self, data.get("sender_display"), avatar_path)
            item.setSizeHint(widget.sizeHint())
            
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, widget)
            self.msg_list.scrollToBottom()
            
            # also refresh sidebar preview
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
        self.tray.showMessage(
            "RobloxChats",
            "Application minimized to tray.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

def main():
    parser = argparse.ArgumentParser(description="RobloxChats Desktop Client")
    parser.add_argument("-m", "--minimized", action="store_true", help="Start minimized in system tray")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS_THEME)
    
    window = MainWindow(args.minimized)
    
    def on_quit():
        window.notifier_thread.running = False
        window.notifier_thread.wait()
        
    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
