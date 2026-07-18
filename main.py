#!/usr/bin/env python3
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from constants import QSS_CUSTOM_WIDGETS
from utils import install_desktop_shortcut
from main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="RobloxChats Desktop Client")
    parser.add_argument("-m", "--minimized", "--minimize", action="store_true", help="Start minimized in system tray")
    parser.add_argument("--install", action="store_true", help="Install a .desktop shortcut for the current user")
    args, _ = parser.parse_known_args()
    
    if args.install:
        install_desktop_shortcut()
        
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(QSS_CUSTOM_WIDGETS)
    
    server_name = "RobloxChats_" + str(os.stat(os.path.expanduser("~")).st_dev) + "_" + str(os.getuid())

    socket = QLocalSocket()
    socket.connectToServer(server_name)

    if socket.waitForConnected(500):
        socket.write(b"activate")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        print("Another instance is already running. Focused existing window.")
        sys.exit(0)

    socket.close()
    QLocalServer.removeServer(server_name)
    local_server = QLocalServer()
    local_server.listen(server_name)
    
    window = MainWindow(args.minimized)

    def on_new_connection():
        if not window.isVisible():
            window.show()
        elif window.isMinimized():
            window.showNormal()
        window.activateWindow()
        window.raise_()

    local_server.newConnection.connect(on_new_connection)
    
    def on_quit():
        window.notifier_thread.running = False
        window.notifier_thread.wait()
        window.presence_thread.running = False
        window.presence_thread.wait()
        local_server.close()
        
    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
