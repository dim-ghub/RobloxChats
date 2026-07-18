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
        res = self.session.get("https://users.roblox.com/v1/users/authenticated")
        if self.check_csrf(res):
            res = self.session.get("https://users.roblox.com/v1/users/authenticated")
        if res.status_code == 200:
            self.my_user_id = res.json().get("id")
            return self.my_user_id
        logging.error(f"Failed to authenticate: {res.status_code} {res.text}")
        return None

    def fetch_conversations(self):
        url = "https://apis.roblox.com/platform-chat-api/v1/get-user-conversations?pageNumber=1&pageSize=30"
        res = self.session.get(url)
        if self.check_csrf(res):
            res = self.session.get(url)
        if res.status_code == 200:
            data = res.json()
            return data if isinstance(data, list) else data.get("conversations", data.get("data", []))
        logging.error(f"Failed to fetch conversations: {res.status_code} {res.text}")
        return []

    def fetch_messages(self, conv_id):
        url = f"https://apis.roblox.com/platform-chat-api/v1/get-conversation-messages?conversation_id={conv_id}&pageSize=50"
        res = self.session.get(url)
        if res.status_code == 200:
            data = res.json()
            return data if isinstance(data, list) else data.get("messages", data.get("data", data))
        logging.error(f"Failed to fetch messages for conv {conv_id}: {res.status_code} {res.text}")
        return []

    def send_message(self, conv_id, text):
        url = "https://apis.roblox.com/platform-chat-api/v1/send-messages"
        payload = {
            "conversation_id": conv_id,
            "messages": [{"content": text}]
        }
        res = self.session.post(url, json=payload)
        if self.check_csrf(res):
            res = self.session.post(url, json=payload)
        if res.status_code == 200:
            return True
        logging.error(f"Failed to send message: {res.status_code} {res.text}")
        return False

    def get_user_avatar(self, user_id):
        res = self.session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=48x48&format=Png&isCircular=false")
        if res.status_code == 200:
            data = res.json()
            if "data" in data and len(data["data"]) > 0:
                return data["data"][0].get("imageUrl")
        return None

api = RobloxAPI()
