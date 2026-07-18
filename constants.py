import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
os.makedirs(ASSETS_DIR, exist_ok=True)

QSS_CUSTOM_WIDGETS = """
/* Remove backgrounds from lists so they inherit the OS theme */
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget#msg_list {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget#msg_list::item:selected {
    background: transparent;
}
QListWidget#msg_list::item:hover {
    background: transparent;
}
/* Floating Sidebar Container */
QWidget#sidebar_container {
    background-color: palette(button);
    border-radius: 16px;
    margin: 8px;
}
"""
