import os
import requests
import logging
import uuid
import time

logging.getLogger("urllib3").setLevel(logging.WARNING)

class RobloxAPI:
    def __init__(self):
        self.session = requests.Session()
        self.cookie = None
        self.session_id = str(uuid.uuid4())
        self.my_user_id = None
        self.my_username = None
        self.my_display_name = None
        
    def update_cookie(self, cookie):
        self.cookie = cookie
        self.session.cookies.set(".ROBLOSECURITY", cookie)
        
    def check_csrf(self, response):
        if response.status_code == 403 and "x-csrf-token" in response.headers:
            self.session.headers.update({"x-csrf-token": response.headers["x-csrf-token"]})
            return True
        return False

    def get_current_user(self):
        for attempt in range(3):
            try:
                res = self.session.get("https://users.roblox.com/v1/users/authenticated", timeout=10)
                if self.check_csrf(res):
                    res = self.session.get("https://users.roblox.com/v1/users/authenticated", timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    self.my_user_id = data.get("id")
                    self.my_username = data.get("name")
                    self.my_display_name = data.get("displayName")
                    return self.my_user_id
                elif res.status_code == 401:
                    logging.error(f"Unauthorized: {res.status_code} {res.text}")
                    return None
                else:
                    logging.error(f"Failed to authenticate: {res.status_code} {res.text}")
                    return None
            except requests.exceptions.RequestException:
                logging.error(f"Failed to connect to Roblox API (attempt {attempt+1}/3). Retrying in 2 seconds...")
                time.sleep(2)
        
        logging.error("Failed to connect to Roblox API after 3 attempts.")
        raise ConnectionError("Roblox is down or no internet connection.")

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
        payload = {
            "clientSideTimestampEpochMs": int(time.time() * 1000),
            "sessionInfo": {"sessionId": self.session_id},
            "locationInfo": {"websiteLocationInfo": {"url": "https://www.roblox.com/home"}}
        }
        try:
            res = self.session.post(url, json=payload, timeout=5)
            if self.check_csrf(res):
                self.session.post(url, json=payload, timeout=5)
        except Exception as e:
            logging.error(f"Heartbeat error: {e}")

    def get_user_avatar(self, user_id):
        res = self.session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=48x48&format=Png&isCircular=false", timeout=10)
        if res.status_code == 200:
            data = res.json()
            if "data" in data and len(data["data"]) > 0:
                return data["data"][0].get("imageUrl")
        return None

api = RobloxAPI()
