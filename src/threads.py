import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime

import requests
from desktop_notifier import DesktopNotifier, Icon, Button, Attachment
from desktop_notifier.common import Capability

from PyQt6.QtCore import QThread, pyqtSignal

from constants import ASSETS_DIR
from utils import extract_name, download_avatar_sync
from roblox_api import api


class ChatLoaderThread(QThread):
    finished_signal = pyqtSignal(list, dict, str, bool)
    
    def __init__(self, conv_id, conv_map, cursor=None):
        super().__init__()
        self.conv_id = conv_id
        self.conv_map = conv_map
        self.cursor = cursor
        
    def run(self):
        msgs, next_cursor = api.fetch_messages(self.conv_id, self.cursor)
        user_data = self.conv_map.get(self.conv_id, {}).get("user_data", {})
        self.finished_signal.emit(msgs, user_data, next_cursor or "", self.cursor is not None)


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
    open_chat_signal = pyqtSignal(str)
    
    def __init__(self, main_window_ref):
        super().__init__()
        self.running = True
        self.main_window_ref = main_window_ref
        
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
            
        seen_messages = set()
        
        while api.my_user_id is None:
            if not self.running: return
            await asyncio.sleep(1)
            
        try:
            convs = await asyncio.to_thread(api.fetch_conversations)
            for conv in convs[:5]:
                msgs, _ = await asyncio.to_thread(api.fetch_messages, conv.get("id"))
                for m in msgs:
                    seen_messages.add(m.get("id"))
        except:
            pass
                
        while self.running:
            if getattr(self, "clear_requested", False):
                self.clear_requested = False
                try:
                    await notifier.clear_all()
                except:
                    pass
                    
            try:
                convs = await asyncio.to_thread(api.fetch_conversations)
                for conv in convs[:5]:
                    conv_id = conv.get("id")
                    msgs, _ = await asyncio.to_thread(api.fetch_messages, conv_id)
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
                            
                            if not getattr(self.main_window_ref, "app_active", False):
                                avatar_path = await asyncio.to_thread(download_avatar_sync, sender_id)
                                icon_obj = None
                                attachment_obj = None
                                if avatar_path:
                                    if sys.platform.startswith("linux"):
                                        icon_obj = Icon(name=logo_path)
                                        attachment_obj = Attachment(path=Path(avatar_path))
                                    else:
                                        icon_obj = Icon(path=Path(avatar_path))
                                        
                                def make_callback(cid):
                                    def _cb():
                                        self.open_chat_signal.emit(cid)
                                    return _cb
                                    
                                cb = make_callback(conv_id)
                                        
                                await notifier.send(
                                    title=sender_display,
                                    message=content,
                                    icon=icon_obj,
                                    attachment=attachment_obj,
                                    on_clicked=cb,
                                    buttons=[Button(title="Reply", on_pressed=cb)]
                                )
            except:
                pass
                
            for _ in range(5):
                if not self.running: return
                await asyncio.sleep(1)
