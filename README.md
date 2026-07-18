# RobloxChats

A desktop chat client for Roblox with real-time messaging, desktop notifications, and a native Qt UI.

## Features

- Read and send Roblox chat messages from a desktop app
- Real-time incoming message polling with desktop notifications
- System tray integration with minimize-to-tray option
- Profile button in sidebar with settings access
- Single-instance guard (launching a second time focuses the existing window)
- Message grouping with avatar display
- Typing indicators (for recipient)

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

- `main.py` — Application entry point, single-instance guard, and CLI args
- `src/main_window.py` — Core UI logic and application state
- `src/widgets.py` — Reusable Qt UI widgets (messages, bubbles, chat items)
- `src/threads.py` — Background threads and SignalR WebSocket integration
- `src/roblox_api.py` — Roblox REST API wrapper (auth, presence, messages)
- `src/utils.py` — Helper utilities for avatars and caching
- `assets/` — Cached avatars and application icon
- `.env` — Stores your `.ROBLOSECURITY` cookie (git-ignored)
- `config.json` — App settings like minimize-to-tray (git-ignored)

## Contributing

The project is currently considered **feature complete**. However, pull requests are warmly welcome for any new additional features or bug fixes!
