#!/usr/bin/env python3
import os
import time
import asyncio
import requests
import logging
import sys
import webbrowser
from pathlib import Path
from dotenv import load_dotenv
from desktop_notifier import DesktopNotifier, Icon, Button

load_dotenv()

# Configure basic logging
log_level = logging.DEBUG if os.environ.get("DEBUG") else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("chat_notifier.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
# Reduce urllib3 logging so it doesn't spam
logging.getLogger("urllib3").setLevel(logging.WARNING)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

COOKIE = os.environ.get("ROBLOSECURITY")

if not COOKIE:
    logging.error("Please set the ROBLOSECURITY environment variable in your .env file.")
    logging.error("Example: Add ROBLOSECURITY=\"_|WARNING:-DO-NOT-SHARE-THIS...\" to .env")
    exit(1)

session = requests.Session()
session.cookies.set(".ROBLOSECURITY", COOKIE)

def check_csrf(response):
    if response.status_code == 403 and "x-csrf-token" in response.headers:
        session.headers.update({"x-csrf-token": response.headers["x-csrf-token"]})
        return True
    return False

def get_current_user():
    res = session.get("https://users.roblox.com/v1/users/authenticated")
    if check_csrf(res):
        res = session.get("https://users.roblox.com/v1/users/authenticated")
    if res.status_code == 200:
        return res.json().get("id")
    logging.error(f"Failed to authenticate: {res.status_code} {res.text}")
    return None

def fetch_conversations():
    url = "https://apis.roblox.com/platform-chat-api/v1/get-user-conversations?pageNumber=1&pageSize=30"
    res = session.get(url)
    if check_csrf(res):
        res = session.get(url)
    if res.status_code == 200:
        data = res.json()
        return data if isinstance(data, list) else data.get("conversations", data.get("data", []))
    logging.error(f"Failed to fetch conversations: {res.status_code} {res.text}")
    return []

def fetch_messages(conv_id):
    url = f"https://apis.roblox.com/platform-chat-api/v1/get-conversation-messages?conversation_id={conv_id}&pageSize=10"
    res = session.get(url)
    if res.status_code == 200:
        data = res.json()
        return data if isinstance(data, list) else data.get("messages", data.get("data", data))
    logging.error(f"Failed to fetch messages for conv {conv_id}: {res.status_code} {res.text}")
    return []

def get_user_avatar(user_id):
    res = session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=48x48&format=Png&isCircular=false")
    if res.status_code == 200:
        data = res.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0].get("imageUrl")
    return None

def download_avatar(url, user_id):
    path = os.path.join(ASSETS_DIR, f"roblox_avatar_{user_id}.png")
    if not os.path.exists(path):
        res = requests.get(url)
        if res.status_code == 200:
            with open(path, "wb") as f:
                f.write(res.content)
    return path

def download_logo():
    path = os.path.join(ASSETS_DIR, "roblox_logo.png")
    if not os.path.exists(path):
        try:
            res = requests.get("https://www.google.com/s2/favicons?domain=roblox.com&sz=128")
            if res.status_code == 200:
                with open(path, "wb") as f:
                    f.write(res.content)
        except Exception as e:
            logging.error(f"Failed to download logo: {e}")
    return path if os.path.exists(path) else None

async def main():
    logging.info("Authenticating...")
    my_user_id = None
    while not my_user_id:
        try:
            my_user_id = await asyncio.to_thread(get_current_user)
            if not my_user_id:
                logging.error("Failed to authenticate. Check your ROBLOSECURITY cookie. Retrying in 10 seconds...")
                await asyncio.sleep(10)
        except Exception as e:
            logging.error(f"Network error during authentication: {e}. Retrying in 10 seconds...")
            await asyncio.sleep(10)
            
    logging.info(f"Authenticated successfully as user {my_user_id}")
    
    # Initialize cross-platform notifier
    logo_path = await asyncio.to_thread(download_logo)
    
    if sys.platform.startswith("linux"):
        app_icon_obj = Icon(name=logo_path) if logo_path else None
    else:
        app_icon_obj = Icon(path=Path(logo_path)) if logo_path else None
        
    notifier = DesktopNotifier(
        app_name="Roblox Chat",
        app_icon=app_icon_obj
    )
    
    def on_clicked():
        webbrowser.open("https://www.roblox.com/home")
    
    seen_messages = set()
    
    # Pre-populate seen messages
    convs = await asyncio.to_thread(fetch_conversations)
    for conv in convs:
        msgs = await asyncio.to_thread(fetch_messages, conv.get("id"))
        for m in msgs:
            seen_messages.add(m.get("id"))
            
    logging.info("Listening for new messages...")
    
    while True:
        try:
            convs = await asyncio.to_thread(fetch_conversations)
            # Just check top 5 recent conversations to save API requests
            for conv in convs[:5]:
                conv_id = conv.get("id")
                msgs = await asyncio.to_thread(fetch_messages, conv_id)
                for m in msgs:
                    msg_id = m.get("id")
                    if msg_id and msg_id not in seen_messages:
                        seen_messages.add(msg_id)
                        
                        sender_id = m.get("sender_user_id", m.get("senderTargetId", m.get("senderUserId")))
                        if not sender_id:
                            continue # skip if no sender id
                            
                        # Don't notify for our own messages
                        if sender_id == my_user_id:
                            continue
                            
                        content = m.get("content", "")
                        
                        # Find sender details in user_data
                        sender_name = str(sender_id)
                        sender_display = "Unknown"
                        
                        user_data = conv.get("user_data", {})
                        str_sender_id = str(sender_id)
                        if str_sender_id in user_data:
                            info = user_data[str_sender_id]
                            sender_name = info.get("name") or info.get("combined_name") or str_sender_id
                            sender_display = info.get("display_name") or info.get("combined_name") or str_sender_id
                        
                        title = f"{sender_display} (@{sender_name})"
                        logging.info(f"New message from {title}: {content}")
                        
                        # Get avatar
                        avatar_url = get_user_avatar(sender_id)
                        avatar_path = None
                        if avatar_url:
                            avatar_path = await asyncio.to_thread(download_avatar, avatar_url, sender_id)
                            
                        # Send desktop notification
                        if sys.platform.startswith("linux"):
                            icon_obj = Icon(name=avatar_path) if avatar_path else None
                        else:
                            icon_obj = Icon(path=Path(avatar_path)) if avatar_path else None
                            
                        try:
                            await notifier.send(
                                title=title,
                                message=content,
                                icon=icon_obj,
                                on_clicked=on_clicked,
                                buttons=[
                                    Button(title="Open in browser", on_pressed=on_clicked)
                                ]
                            )
                        except Exception as ex:
                            logging.error(f"Notification error: {ex}")
                        
        except Exception as e:
            logging.error(f"Error during polling: {e}")
            
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
