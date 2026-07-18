import asyncio
import os
import json
import websockets
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
                if not getattr(api, "appear_offline", False):
                    api.send_heartbeat()
            except:
                pass
            
            for _ in range(15):
                if not self.running: return
                time.sleep(1)



class RealtimeChatThread(QThread):
    typing_received_signal = pyqtSignal(str, str, bool)
    new_message_signal = pyqtSignal(dict)
    open_chat_signal = pyqtSignal(str)
    presence_signal = pyqtSignal(dict)
    read_receipt_signal = pyqtSignal(str, bool)
    
    def __init__(self, api_ref, main_window_ref):
        super().__init__()
        self.api = api_ref
        self.main_window_ref = main_window_ref
        self.running = True

    def run(self):
        asyncio.run(self.run_realtime())

    def stop(self):
        self.running = False
        
    async def heartbeat_loop(self):
        while self.running:
            try:
                if self.api.my_user_id and not getattr(self.api, "appear_offline", False):
                    await asyncio.to_thread(self.api.send_heartbeat)
            except:
                pass
            for _ in range(15):
                if not self.running: break
                await asyncio.sleep(1)

    async def run_realtime(self):
        logo_path = os.path.join(ASSETS_DIR, "roblox_logo.png")
        if not os.path.exists(logo_path):
            try:
                res = await asyncio.to_thread(requests.get, "https://www.google.com/s2/favicons?domain=roblox.com&sz=128", timeout=10)
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

        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        url = "wss://realtime-signalr.roblox.com/userhub"
        
        while self.running:

            if not self.api.my_user_id:
                await asyncio.sleep(1)
                continue
                
            cookie = getattr(self.api, "cookie", None) or os.getenv("ROBLOSECURITY")
            if not cookie:
                await asyncio.sleep(1)
                continue

            headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
            try:
                async with websockets.connect(url, additional_headers=headers) as ws:
                    handshake = '{"protocol":"json","version":1}\x1e'
                    await ws.send(handshake)
                    
                    while self.running:
                        if getattr(self, "clear_requested", False):
                            self.clear_requested = False
                            try:
                                await notifier.clear_all()
                            except:
                                pass
                                
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                            for msg_part in msg.split('\x1e'):
                                if not msg_part:
                                    continue
                                data = json.loads(msg_part)
                                if data.get("type") == 1 and data.get("target") == "notification":
                                    args = data.get("arguments", [])
                                    if not args:
                                        continue
                                        
                                    payload_type = args[0]
                                    
                                    if payload_type == "desktop-notifications-windows" and len(args) >= 2:
                                        try:
                                            payload = json.loads(args[1])
                                            content = payload.get("content", {})
                                            if content.get("notificationType") == "ChatNewMessage":
                                                def_state = content.get("states", {}).get("default", {})
                                                v_items = def_state.get("visualItems", [])
                                                
                                                avatar_url = None
                                                sender_display = "Unknown"
                                                msg_text = ""
                                                conv_id = None
                                                
                                                for v in v_items:
                                                    if "thumbnail" in v:
                                                        avatar_url = v["thumbnail"].get("id")
                                                    elif "textBody" in v:
                                                        sender_display = v["textBody"].get("title", {}).get("text", sender_display)
                                                        msg_text = v["textBody"].get("label", {}).get("text", msg_text)
                                                        actions = v["textBody"].get("actions", [])
                                                        if actions:
                                                            path = actions[0].get("path", "")
                                                            if "chatId=" in path:
                                                                conv_id = path.split("chatId=")[1].split("&")[0]
                                                                
                                                if conv_id:
                                                    self.new_message_signal.emit({
                                                        "conv_id": conv_id,
                                                        "sender_display": sender_display,
                                                        "content": msg_text,
                                                        "avatar_url": avatar_url,
                                                    })
                                                    
                                                    if not getattr(self.main_window_ref, "app_active", False):
                                                        icon_obj = None
                                                        attachment_obj = None
                                                        if avatar_url:
                                                            try:
                                                                img_res = await asyncio.to_thread(requests.get, avatar_url, timeout=5)
                                                                if img_res.status_code == 200:
                                                                    tmp_path = os.path.join(ASSETS_DIR, f"tmp_{conv_id}.png")
                                                                    with open(tmp_path, "wb") as f:
                                                                        f.write(img_res.content)
                                                                    if sys.platform.startswith("linux"):
                                                                        icon_obj = Icon(name=logo_path)
                                                                        attachment_obj = Attachment(path=Path(tmp_path))
                                                                    else:
                                                                        icon_obj = Icon(path=Path(tmp_path))
                                                            except:
                                                                pass
                                                                
                                                        def make_callback(cid):
                                                            def _cb():
                                                                self.open_chat_signal.emit(cid)
                                                            return _cb
                                                            
                                                        cb = make_callback(conv_id)
                                                        await notifier.send(
                                                            title=sender_display,
                                                            message=msg_text,
                                                            icon=icon_obj,
                                                            attachment=attachment_obj,
                                                            on_clicked=cb,
                                                            buttons=[Button(title="Reply", on_pressed=cb)]
                                                        )
                                        except Exception as e:
                                            print(f"Error parsing desktop-notifications-windows: {e}")
                                            
                                    elif payload_type == "PresenceBulkNotifications" and len(args) >= 2:
                                        try:
                                            presences = json.loads(args[1])
                                            pres_dict = {}
                                            for p in presences:
                                                uid = p.get("UserId")
                                                p_report = p.get("PresenceReport", {})
                                                if uid and "userPresenceType" in p_report:
                                                    pres_dict[str(uid)] = (p_report["userPresenceType"], p_report.get("lastLocation", ""))
                                            if pres_dict:
                                                self.presence_signal.emit(pres_dict)
                                        except Exception as e:
                                            print(f"Error parsing PresenceBulkNotifications: {e}")
                                            
                                    elif payload_type == "CommunicationChannels" and len(args) >= 2:
                                        try:
                                            payload = json.loads(args[1])
                                            inner_type = payload.get("Type")
                                            conv_id = payload.get("ChannelId")
                                            
                                            if inner_type == "ParticipantTyping":
                                                actor_id = payload.get("Actor", {}).get("Id")
                                                is_typing = payload.get("IsTyping", False)
                                                if actor_id and str(actor_id) != str(self.api.my_user_id):
                                                    self.typing_received_signal.emit(conv_id, str(actor_id), is_typing)
                                            elif inner_type == "ChannelMetadataUpdated":
                                                meta_type = payload.get("MetadataUpdateType")
                                                if meta_type == "ChannelUnread":
                                                    self.read_receipt_signal.emit(conv_id, True)
                                            elif inner_type == "ChannelMarkedRead":
                                                actor_id = payload.get("Actor", {}).get("Id")
                                                if actor_id and str(actor_id) == str(self.api.my_user_id):
                                                    self.read_receipt_signal.emit(conv_id, False)
                                        except Exception as e:
                                            print(f"Error parsing CommunicationChannels: {e}")
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            break
            except Exception as e:
                await asyncio.sleep(5)
