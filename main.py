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
    QSystemTrayIcon, QMenu, QSplitter, QMessageBox
)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer

from desktop_notifier import DesktopNotifier, Icon, Button, Attachment
from desktop_notifier.common import Capability
import requests

from roblox_api import api

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

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
                res = requests.get("https://www.google.com/s2/favicons?domain=roblox.com&sz=128")
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
            pass # GUI is in another thread, user can click the tray icon to open
            
        seen_messages = set()
        
        # Wait until authenticated
        while api.my_user_id is None:
            if not self.running: return
            await asyncio.sleep(1)
            
        # Pre-populate seen
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
                            str_sender_id = str(sender_id)
                            info = user_data.get(str_sender_id, {})
                            sender_display = info.get("display_name") or info.get("name") or str_sender_id
                            
                            self.new_message_signal.emit({
                                "conv_id": conv_id,
                                "sender_display": sender_display,
                                "content": content
                            })
                            
                            avatar_url = api.get_user_avatar(sender_id)
                            avatar_path = None
                            if avatar_url:
                                avatar_path = os.path.join(ASSETS_DIR, f"roblox_avatar_{sender_id}.png")
                                if not os.path.exists(avatar_path):
                                    res = await asyncio.to_thread(requests.get, avatar_url)
                                    if res.status_code == 200:
                                        with open(avatar_path, "wb") as f:
                                            f.write(res.content)
                                            
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
        self.resize(800, 600)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.setup_login_tab()
        self.setup_chat_tab()
        self.setup_tray()
        
        self.notifier_thread = NotifierThread()
        self.notifier_thread.new_message_signal.connect(self.on_new_message)
        self.notifier_thread.start()
        
        load_dotenv()
        cookie = os.environ.get("ROBLOSECURITY")
        if cookie:
            self.cookie_input.setText(cookie)
            self.login()
            
        if not start_minimized:
            self.show()
            
    def setup_login_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("Enter .ROBLOSECURITY cookie...")
        self.cookie_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.login)
        
        self.status_label = QLabel("Not logged in.")
        
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
        else:
            self.status_label.setText("Login failed. Check cookie validity.")
            
    def setup_chat_tab(self):
        tab = QWidget()
        layout = QHBoxLayout()
        
        self.conv_list = QListWidget()
        self.conv_list.itemClicked.connect(self.on_conv_selected)
        
        right_panel = QVBoxLayout()
        self.msg_list = QListWidget()
        
        input_layout = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.msg_input.returnPressed.connect(self.send_message)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(self.send_btn)
        
        right_panel.addWidget(self.msg_list)
        right_panel.addLayout(input_layout)
        
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.conv_list)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 550])
        
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
            title = conv.get("title")
            if not title:
                # generate title from participants if title is empty
                participants = conv.get("participants", [])
                user_data = conv.get("user_data", {})
                names = []
                for p in participants:
                    p_id = str(p.get("targetId"))
                    if p_id != str(api.my_user_id) and p_id in user_data:
                        names.append(user_data[p_id].get("display_name", p_id))
                title = ", ".join(names) if names else cid
                
            self.conv_map[cid] = conv
            
            # Store cid as user data in the QListWidgetItem
            from PyQt6.QtWidgets import QListWidgetItem
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, cid)
            self.conv_list.addItem(item)
            
    def on_conv_selected(self, item):
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self.current_conv_id = cid
            self.load_messages(cid)
                
    def load_messages(self, cid):
        self.msg_list.clear()
        msgs = api.fetch_messages(cid)
        for m in reversed(msgs):
            sender_id = str(m.get("sender_user_id", m.get("senderTargetId", m.get("senderUserId"))))
            content = m.get("content", "")
            
            prefix = "Me" if sender_id == str(api.my_user_id) else sender_id
            
            # try to get display name
            if cid in self.conv_map:
                user_data = self.conv_map[cid].get("user_data", {})
                if sender_id in user_data:
                    prefix = user_data[sender_id].get("display_name", sender_id)
                    
            self.msg_list.addItem(f"{prefix}: {content}")
            
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
            self.msg_list.addItem(f'{data["sender_display"]}: {data["content"]}')
            # Scroll to bottom
            self.msg_list.scrollToBottom()
            
    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        
        logo_path = os.path.join(ASSETS_DIR, "roblox_logo.png")
        if os.path.exists(logo_path):
            self.tray.setIcon(QIcon(logo_path))
        else:
            # Fallback icon if logo not downloaded yet
            self.tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
            
        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()
        
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
    
    window = MainWindow(args.minimized)
    
    def on_quit():
        window.notifier_thread.running = False
        window.notifier_thread.wait()
        
    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
