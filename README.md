# Roblox Chat Notifier

A Python script that listens to your Roblox chats using the `platform-chat-api` and sends desktop notifications (via `notify-send`) when you receive new messages.

## Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your Token:**
   Create a `.env` file in the root directory (you can use `.env.example` as a template if you have one) and set your `.ROBLOSECURITY` cookie:
   ```env
   ROBLOSECURITY="_|WARNING:-DO-NOT-SHARE-THIS..."
   ```
   *Warning: Never share your `.ROBLOSECURITY` token with anyone.*

## Usage

Simply run the script. It will run continuously in the background and poll for new messages every 5 seconds.

```bash
./chat_notifier.py
```
