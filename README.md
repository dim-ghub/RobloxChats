# RobloxChats

A desktop chat client for Roblox with real-time messaging, desktop notifications, and a native Qt UI.

## Features

- Read and send Roblox chat messages from a desktop app
- Real-time incoming message polling with desktop notifications
- System tray integration with minimize-to-tray option
- Profile button in sidebar with settings access
- Single-instance guard (launching a second time focuses the existing window)
- Message grouping with avatar display
- Typing indicators

## Setup

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure your cookie:**
   On first launch, a settings dialog will prompt you for your `.ROBLOSECURITY` cookie. It is stored in a local `.env` file.

   You can also enter it manually in `.env`:
   ```env
   ROBLOSECURITY="_|WARNING:-DO-NOT-SHARE-THIS..."
   ```

   > **Warning:** Never share your `.ROBLOSECURITY` cookie with anyone.

## Usage

```bash
python main.py
```

### Options

| Flag | Description |
|------|-------------|
| `-m`, `--minimized` | Start minimized to system tray |
| `--install` | Install a `.desktop` shortcut for the current user |

### Settings

Click the profile button at the bottom of the sidebar to open settings, where you can update your cookie and toggle minimize-to-tray behavior.

## Project Structure

- `main.py` — Application entry point, UI, and all widget logic
- `roblox_api.py` — Roblox API wrapper (auth, conversations, messages, presence)
- `assets/` — Cached avatars and app icon
- `.env` — Stores your `.ROBLOSECURITY` cookie (git-ignored)
- `config.json` — App settings like minimize-to-tray (git-ignored)
