import logging
import os
import threading
from datetime import datetime

from dotenv import load_dotenv

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QLabel, QDialog,
    QSystemTrayIcon, QMenu, QSplitter, QMessageBox,
    QListWidgetItem, QSizePolicy, QFrame, QListView
)
from PyQt6.QtGui import QIcon, QPixmap, QAction
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent

from roblox_api import api
from constants import ASSETS_DIR
from utils import load_config, save_config, get_circular_pixmap, download_avatar_sync, extract_name
from widgets import (
    BubbleWidget, InputContainerWidget, SendButton,
    ConversationWidget, QuoteFrame, MessageWidget, ChatListDelegate
)
from threads import ChatLoaderThread, MessageSenderThread, PresencePollingThread, NotifierThread
from dialogs import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, start_minimized):
        super().__init__()
        self.setWindowTitle("RobloxChats")
        self.resize(1000, 700)
        self.app_active = False
        self.config = load_config()
        
        self.setup_ui()
        
        load_dotenv()
        self.cookie = os.environ.get("ROBLOSECURITY")
        
        if not start_minimized:
            self.show()
            
        self.typing_timer = QTimer()
        self.typing_timer.setInterval(4000)
        self.typing_timer.timeout.connect(self.send_typing_indicator)
            
        QTimer.singleShot(100, self.post_init)
        
    def changeEvent(self, event):
        if event.type() in (QEvent.Type.ActivationChange, QEvent.Type.WindowStateChange):
            self.app_active = self.isActiveWindow() and self.isVisible() and not self.isMinimized()
            if self.app_active and hasattr(self, 'notifier_thread'):
                self.notifier_thread.clear_requested = True
        super().changeEvent(event)
        
    def hideEvent(self, event):
        self.app_active = False
        super().hideEvent(event)
        
    def showEvent(self, event):
        self.app_active = self.isActiveWindow() and not self.isMinimized()
        if self.app_active and hasattr(self, 'notifier_thread'):
            self.notifier_thread.clear_requested = True
        super().showEvent(event)
        
    def setup_ui(self):
        central = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        sidebar_container = QWidget()
        sidebar_container.setObjectName("sidebar_container")
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        
        self.conv_list = QListWidget()
        self.conv_list.setObjectName("conv_list")
        self.conv_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.conv_list.setItemDelegate(ChatListDelegate(self.conv_list))
        self.conv_list.itemClicked.connect(self.on_conv_selected)
        sidebar_layout.addWidget(self.conv_list)
        
        self.profile_btn = QPushButton()
        self.profile_btn.setObjectName("profile_btn")
        self.profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_btn.clicked.connect(self.open_settings)
        self.profile_btn.setFixedHeight(48)
        self.profile_btn.setStyleSheet("""
            QPushButton#profile_btn {
                border: none;
                border-radius: 12px;
                background-color: palette(light);
            }
            QPushButton#profile_btn:hover {
                background-color: palette(midlight);
            }
            QPushButton#profile_btn:pressed {
                background-color: palette(mid);
            }
        """)
        
        profile_layout = QHBoxLayout()
        profile_layout.setContentsMargins(12, 8, 12, 8)
        profile_layout.setSpacing(10)
        
        self.profile_avatar = QLabel()
        self.profile_avatar.setFixedSize(32, 32)
        self.profile_avatar.setStyleSheet("background: transparent;")
        profile_layout.addWidget(self.profile_avatar)
        
        self.profile_name = QLabel("Not logged in")
        self.profile_name.setStyleSheet("font-size: 13px; background: transparent;")
        profile_layout.addWidget(self.profile_name, 1)
        
        settings_icon = QLabel("\u2699")
        settings_icon.setStyleSheet("font-size: 18px; background: transparent; color: palette(placeholderText);")
        settings_icon.setFixedWidth(24)
        settings_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(settings_icon)
        
        self.profile_btn.setLayout(profile_layout)
        
        profile_wrapper = QWidget()
        profile_wrapper_layout = QVBoxLayout()
        profile_wrapper_layout.setContentsMargins(4, 0, 4, 4)
        profile_wrapper_layout.addWidget(self.profile_btn)
        profile_wrapper.setLayout(profile_wrapper_layout)
        sidebar_layout.addWidget(profile_wrapper)
        
        sidebar_container.setLayout(sidebar_layout)
        
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        
        self.msg_list = QListWidget()
        self.msg_list.setObjectName("msg_list")
        self.msg_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.msg_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.msg_list.verticalScrollBar().valueChanged.connect(self.on_scroll_changed)
        
        input_container = InputContainerWidget()
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)
        
        self.msg_input = QLineEdit()
        self.msg_input.setObjectName("msg_input")
        self.msg_input.setMaxLength(160)
        self.msg_input.setPlaceholderText("Send a message")
        self.msg_input.setStyleSheet("background: transparent; color: palette(text); border: none; padding: 12px 16px; font-size: 14px;")
        self.msg_input.returnPressed.connect(self.send_message)
        self.msg_input.textChanged.connect(self.on_input_changed)
        
        self.send_btn = SendButton("\u2191")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.msg_input)
        
        btn_wrapper = QWidget()
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(4, 4, 4, 4)
        btn_layout.addWidget(self.send_btn)
        btn_wrapper.setLayout(btn_layout)
        input_layout.addWidget(btn_wrapper)
        
        input_container.setLayout(input_layout)
        
        self.system_msg_lbl = QLabel("")
        self.system_msg_lbl.setStyleSheet("color: palette(placeholderText); font-size: 12px; font-weight: bold; padding: 4px;")
        self.system_msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.system_msg_lbl.setWordWrap(True)
        self.system_msg_lbl.hide()
        
        bottom_panel = QVBoxLayout()
        bottom_panel.setContentsMargins(16, 8, 16, 16)
        bottom_panel.addWidget(self.system_msg_lbl)
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
        self.current_next_cursor = None
        self.is_loading_history = False
        self.conv_map = {}
        self.presence_map = {}
        self.unread_convs = set()
        
    def post_init(self):
        self.setup_tray()
        
        self.notifier_thread = NotifierThread(self)
        self.notifier_thread.new_message_signal.connect(self.on_new_message)
        self.notifier_thread.open_chat_signal.connect(self.force_open_chat)
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
                self.config["minimize_to_tray"] = dialog.get_minimize_to_tray()
                save_config(self.config)
                if not api.get_current_user():
                    QMessageBox.warning(self, "Error", "Invalid cookie. Restart app to try again.")
                    return
            else:
                return
                
        self._update_profile_button()
        self.refresh_chats()
    
    def _update_profile_button(self):
        name = api.my_display_name or api.my_username or "User"
        self.profile_name.setText(name)
        
        avatar_path = os.path.join(ASSETS_DIR, f"roblox_avatar_{api.my_user_id}.png")
        if not os.path.exists(avatar_path):
            avatar_path = download_avatar_sync(str(api.my_user_id))
        
        pixmap = get_circular_pixmap(avatar_path, 32) if avatar_path else QPixmap(32, 32)
        self.profile_avatar.setPixmap(pixmap)
    
    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.cookie_input.setText(self.cookie or "")
        dialog.tray_checkbox.setChecked(self.config.get("minimize_to_tray", True))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_cookie = dialog.get_cookie()
            if new_cookie != self.cookie:
                api.update_cookie(new_cookie)
                with open(".env", "w") as f:
                    f.write(f"ROBLOSECURITY={new_cookie}\n")
                self.cookie = new_cookie
                if api.get_current_user():
                    self._update_profile_button()
                    self.refresh_chats()
                else:
                    QMessageBox.warning(self, "Error", "Invalid cookie.")
            self.config["minimize_to_tray"] = dialog.get_minimize_to_tray()
            save_config(self.config)
            
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
            unread = cid in self.unread_convs
            
            item = QListWidgetItem()
            widget = ConversationWidget(title, preview, avatar_path, presence_type, unread)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, cid)
            
            self.conv_list.addItem(item)
            self.conv_list.setItemWidget(item, widget)
            
        self.presence_thread.set_user_ids(tracked_users)
            
    def on_presence_updated(self, pres_dict):
        changed = False
        for uid, p_type in pres_dict.items():
            if self.presence_map.get(uid) != p_type:
                self.presence_map[uid] = p_type
                changed = True
        if changed:
            self.refresh_chats()
            
    def on_scroll_changed(self, value):
        if value == 0 and self.current_next_cursor and not self.is_loading_history:
            self.is_loading_history = True
            self.loader_thread = ChatLoaderThread(self.current_conv_id, self.conv_map, cursor=self.current_next_cursor)
            self.loader_thread.finished_signal.connect(self.on_messages_loaded)
            self.loader_thread.start()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'msg_list'):
            w = self.msg_list.viewport().width()
            for i in range(self.msg_list.count()):
                item = self.msg_list.item(i)
                widget = self.msg_list.itemWidget(item)
                if widget and hasattr(widget, 'update_width'):
                    widget.update_width(w)
                    h = widget.heightForWidth(w) if widget.hasHeightForWidth() else widget.sizeHint().height()
                    item.setSizeHint(QSize(w - 10, h))

    def on_conv_selected(self, item):
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid:
            self.current_conv_id = cid
            self.current_next_cursor = None
            self.is_loading_history = False
            self.system_msg_lbl.hide()
            
            if cid in self.unread_convs:
                self.unread_convs.remove(cid)
                self.refresh_chats()
                
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
            
    def format_timestamp(self, dt):
        now = datetime.now(dt.tzinfo)
        time_str = dt.strftime("%I:%M %p").lstrip("0")
        if time_str.startswith(":"):
            time_str = "12" + time_str
            
        if dt.date() == now.date():
            return time_str
            
        delta_days = (now.date() - dt.date()).days
        if delta_days == 1:
            return f"Yesterday | {time_str}"
            
        if delta_days < 7:
            return f"{dt.strftime('%A')} | {time_str}"
            
        if dt.year == now.year:
            day = str(dt.day)
            return f"{dt.strftime('%b')} {day} | {time_str}"
            
        day = str(dt.day)
        return f"{dt.strftime('%b')} {day} {dt.year} | {time_str}"
            
    def scroll_to_message(self, msg_id):
        for i in range(self.msg_list.count()):
            item = self.msg_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == msg_id:
                self.msg_list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
                widget = self.msg_list.itemWidget(item)
                if widget and hasattr(widget, 'trigger_highlight'):
                    widget.trigger_highlight()
                break
                
    def force_open_chat(self, conv_id):
        self.show()
        self.activateWindow()
        self.raise_()
        for i in range(self.conv_list.count()):
            item = self.conv_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == conv_id:
                self.conv_list.setCurrentItem(item)
                self.on_conv_selected(item)
                break
                
    def _update_all_groupings(self):
        for i in range(self.msg_list.count()):
            item = self.msg_list.item(i)
            widget = self.msg_list.itemWidget(item)
            if not isinstance(widget, MessageWidget):
                continue
                
            prev_w = None
            for j in range(i-1, -1, -1):
                pw = self.msg_list.itemWidget(self.msg_list.item(j))
                if isinstance(pw, MessageWidget):
                    prev_w = pw
                    break
                    
            next_w = None
            for j in range(i+1, self.msg_list.count()):
                nw = self.msg_list.itemWidget(self.msg_list.item(j))
                if isinstance(nw, MessageWidget):
                    next_w = nw
                    break
                    
            same_prev = False
            if prev_w and getattr(prev_w, 'sender_id', None) == getattr(widget, 'sender_id', None) and getattr(widget, 'timestamp', None) and getattr(prev_w, 'timestamp', None):
                if (widget.timestamp - prev_w.timestamp).total_seconds() <= 300:
                    same_prev = True
                    
            same_next = False
            if next_w and getattr(next_w, 'sender_id', None) == getattr(widget, 'sender_id', None) and getattr(widget, 'timestamp', None) and getattr(next_w, 'timestamp', None):
                if (next_w.timestamp - widget.timestamp).total_seconds() <= 300:
                    same_next = True
            
            if same_prev and same_next: pos = "middle"
            elif same_prev: pos = "bottom"
            elif same_next: pos = "top"
            else: pos = "single"
                
            widget.set_group_pos(pos)
            item.setSizeHint(widget.sizeHint())

    def on_messages_loaded(self, msgs, user_data, next_cursor, is_prepend):
        self.current_next_cursor = next_cursor if next_cursor else None
        
        if not is_prepend:
            self.msg_list.clear()
            
        old_scroll_max = self.msg_list.verticalScrollBar().maximum()
        old_scroll_val = self.msg_list.verticalScrollBar().value()
        
        last_time = None
        last_sender = None
        insert_row = 0
        
        for m in reversed(msgs):
            msg_type = m.get("type", "user")
            content = m.get("content", "")
            if msg_type == "system":
                self.system_msg_lbl.setText(content)
                self.system_msg_lbl.show()
                continue
                
            sender_id = str(m.get("sender_user_id", m.get("senderTargetId", m.get("senderUserId"))))
            created_at_str = m.get("created_at")
            
            reply_data = None
            replies_to = m.get("replies_to")
            if replies_to:
                rep_sender_id = str(replies_to.get("sender_user_id"))
                if rep_sender_id == str(api.my_user_id):
                    rep_sender_name = "You"
                else:
                    rep_sender_name = extract_name(rep_sender_id, user_data) if rep_sender_id else "Unknown"
                reply_data = {
                    "sender": rep_sender_name,
                    "content": replies_to.get("content", ""),
                    "id": replies_to.get("id")
                }
            
            if created_at_str:
                try:
                    dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).astimezone()
                    if last_time is None or (dt - last_time).total_seconds() > 300:
                        ts_item = QListWidgetItem()
                        lbl = QLabel(self.format_timestamp(dt))
                        lbl.setStyleSheet("color: palette(placeholderText); font-size: 12px; font-weight: bold; padding: 16px 0px 8px 0px;")
                        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        ts_item.setSizeHint(lbl.sizeHint())
                        
                        if is_prepend:
                            self.msg_list.insertItem(insert_row, ts_item)
                            self.msg_list.setItemWidget(ts_item, lbl)
                            insert_row += 1
                        else:
                            self.msg_list.addItem(ts_item)
                            self.msg_list.setItemWidget(ts_item, lbl)
                            
                        last_sender = None
                    last_time = dt
                except:
                    pass
            
            is_self = (sender_id == str(api.my_user_id))
            
            avatar_path = None
            if not is_self and sender_id != last_sender:
                avatar_path = download_avatar_sync(sender_id)
                
            item = QListWidgetItem()
            msg_id = m.get("id")
            if msg_id:
                item.setData(Qt.ItemDataRole.UserRole, msg_id)
            dt_val = None
            if created_at_str:
                try: dt_val = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).astimezone()
                except: pass
            widget = MessageWidget(content, is_self, avatar_path, reply_data, animate=True, sender_id=sender_id, timestamp=dt_val)
            widget.update_width(self.msg_list.viewport().width())
            widget.reply_clicked.connect(self.go_to_message)
            
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            
            item.setSizeHint(widget.sizeHint())
            
            if is_prepend:
                self.msg_list.insertItem(insert_row, item)
                self.msg_list.setItemWidget(item, widget)
                insert_row += 1
            else:
                self.msg_list.addItem(item)
                self.msg_list.setItemWidget(item, widget)
                
            last_sender = sender_id
            
        self._update_all_groupings()
        
        if is_prepend:
            QApplication.processEvents()
            new_scroll_max = self.msg_list.verticalScrollBar().maximum()
            delta = new_scroll_max - old_scroll_max
            self.msg_list.verticalScrollBar().setValue(old_scroll_val + delta)
        if not is_prepend:
            self.msg_list.scrollToBottom()
            
        self.is_loading_history = False
        
    def go_to_message(self, msg_id):
        for i in range(self.msg_list.count()):
            item = self.msg_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == msg_id:
                self.msg_list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)
                widget = self.msg_list.itemWidget(item)
                if hasattr(widget, 'trigger_highlight'):
                    widget.trigger_highlight()
                break

    def on_input_changed(self, text):
        if text and self.current_conv_id:
            if not self.typing_timer.isActive():
                self.send_typing_indicator()
                self.typing_timer.start()
        else:
            self.typing_timer.stop()
            
    def send_typing_indicator(self):
        if self.current_conv_id:
            threading.Thread(target=lambda: api.update_typing_status(self.current_conv_id, True), daemon=True).start()
            
    def send_message(self):
        if not self.current_conv_id: return
        text = self.msg_input.text().strip()
        if not text: return
        
        self.msg_input.clear()
        
        item = QListWidgetItem()
        now = datetime.now().astimezone()
        widget = MessageWidget(text, True, None, animate=True, sender_id=str(api.my_user_id), timestamp=now)
        item.setSizeHint(widget.sizeHint())
        self.msg_list.addItem(item)
        self.msg_list.setItemWidget(item, widget)
        self._update_all_groupings()
        self.msg_list.scrollToBottom()
        
        self.sender_thread = MessageSenderThread(self.current_conv_id, text)
        self.sender_thread.start()
        
    def on_new_message(self, data):
        cid = data["conv_id"]
        if self.current_conv_id == cid:
            is_self = data.get("sender_id") == str(api.my_user_id)
            if is_self:
                return 
                
            avatar_path = os.path.join(ASSETS_DIR, f"roblox_avatar_{data.get('sender_id')}.png")
            item = QListWidgetItem()
            msg_id = data.get("id")
            if msg_id:
                item.setData(Qt.ItemDataRole.UserRole, msg_id)
                
            dt_val = None
            if data.get("created_at"):
                try: dt_val = datetime.fromisoformat(data.get("created_at").replace("Z", "+00:00")).astimezone()
                except: pass
                
            widget = MessageWidget(data["content"], is_self, avatar_path, None, animate=True, sender_id=str(data.get("sender_id")), timestamp=dt_val)
            widget.reply_clicked.connect(self.go_to_message)
            item.setSizeHint(widget.sizeHint())
            
            self.msg_list.addItem(item)
            self.msg_list.setItemWidget(item, widget)
            self._update_all_groupings()
            self.msg_list.scrollToBottom()
        else:
            self.unread_convs.add(cid)
            
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
        if self.config.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
        else:
            event.accept()
            QApplication.quit()
