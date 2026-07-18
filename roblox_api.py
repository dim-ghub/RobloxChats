import os
import requests
import logging

logging.getLogger("urllib3").setLevel(logging.WARNING)

class RobloxAPI:
    def __init__(self):
        self.session = requests.Session()
        self.cookie = None
        self.my_user_id = None
        
    def update_cookie(self, cookie):
        self.cookie = cookie
        self.session.cookies.set(".ROBLOSECURITY", cookie)
        
    def check_csrf(self, response):
        if response.status_code == 403 and "x-csrf-token" in response.headers:
            self.session.headers.update({"x-csrf-token": response.headers["x-csrf-token"]})
            return True
        return False

    def get_current_user(self):
        res = self.session.get("https://users.roblox.com/v1/users/authenticated", timeout=10)
        if self.check_csrf(res):
            res = self.session.get("https://users.roblox.com/v1/users/authenticated", timeout=10)
        if res.status_code == 200:
            self.my_user_id = res.json().get("id")
            return self.my_user_id
        logging.error(f"Failed to authenticate: {res.status_code} {res.text}")
        return None

    def fetch_conversations(self):
        url = "https://apis.roblox.com/platform-chat-api/v1/get-user-conversations?pageNumber=1&pageSize=30"
        res = self.session.get(url, timeout=10)
        if self.check_csrf(res):
            res = self.session.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data if isinstance(data, list) else data.get("conversations", data.get("data", []))
        logging.error(f"Failed to fetch conversations: {res.status_code} {res.text}")
        return []

    def fetch_messages(self, conv_id, cursor=None):
        url = f"https://apis.roblox.com/platform-chat-api/v1/get-conversation-messages?conversation_id={conv_id}&pageSize=50"
        if cursor:
            url += f"&cursor={cursor}"
        res = self.session.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            msgs = data if isinstance(data, list) else data.get("messages", data.get("data", data))
            next_cursor = data.get("next_cursor") if isinstance(data, dict) else None
            return msgs, next_cursor
        logging.error(f"Failed to fetch messages for conv {conv_id}: {res.status_code} {res.text}")
        return [], None

    def send_message(self, conv_id, text):
        url = "https://apis.roblox.com/platform-chat-api/v1/send-messages"
        payload = {
            "conversation_id": conv_id,
            "messages": [{"content": text}]
        }
        try:
            res = self.session.post(url, json=payload, timeout=10)
            if self.check_csrf(res):
                res = self.session.post(url, json=payload, timeout=10)
            if res.status_code in [200, 204]:
                return True
            return False
        except:
            return False
            
    def update_typing_status(self, conv_id, is_typing=True):
        url = "https://apis.roblox.com/platform-chat-api/v1/update-typing-status"
        payload = {
            "conversation_id": conv_id,
            "is_typing": is_typing
        }
        try:
            res = self.session.post(url, json=payload, timeout=5)
            if self.check_csrf(res):
                self.session.post(url, json=payload, timeout=5)
        except:
            pass
            
    def get_presence(self, user_ids):
        url = "https://presence.roblox.com/v1/presence/users"
        payload = {"userIds": [int(uid) for uid in user_ids]}
        try:
            res = self.session.post(url, json=payload, timeout=10)
            if self.check_csrf(res):
                res = self.session.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                return res.json().get("userPresences", [])
        except:
            pass
        return []
        
    def send_heartbeat(self):
        url = "https://apis.roblox.com/user-heartbeats-api/pulse"
        try:
            res = self.session.post(url, timeout=5)
            if self.check_csrf(res):
                self.session.post(url, timeout=5)
        except:
            pass

    def get_user_avatar(self, user_id):
        res = self.session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=48x48&format=Png&isCircular=false", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "data" in data and len(data["data"]) > 0:
                return data["data"][0].get("imageUrl")
        return None

api = RobloxAPI()
