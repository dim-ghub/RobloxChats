import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt

from utils import load_config, save_config


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RobloxChats Settings")
        self.setFixedSize(400, 260)
        
        layout = QVBoxLayout()
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("Enter .ROBLOSECURITY cookie...")
        self.cookie_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        if os.environ.get("ROBLOSECURITY"):
            self.cookie_input.setText(os.environ.get("ROBLOSECURITY"))
        
        config = load_config()
        self.tray_checkbox = QCheckBox("Minimize to tray when closed")
        self.tray_checkbox.setChecked(config.get("minimize_to_tray", True))
        
        self.login_btn = QPushButton("Save & Login")
        self.login_btn.clicked.connect(self.accept)
        
        layout.addStretch()
        layout.addWidget(QLabel("Roblox Cookie (.ROBLOSECURITY):"))
        layout.addWidget(self.cookie_input)
        layout.addWidget(self.tray_checkbox)
        layout.addSpacing(8)
        layout.addWidget(self.login_btn)
        layout.addStretch()
        self.setLayout(layout)
        
    def get_cookie(self):
        return self.cookie_input.text().strip()
    
    def get_minimize_to_tray(self):
        return self.tray_checkbox.isChecked()
