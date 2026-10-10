"""
Dashboard LMU : application Windows.

Ouvre le dashboard dans sa propre fenêtre (moteur Edge WebView2 intégré à Windows),
sans navigateur. Le pont télémétrie tourne en arrière-plan dans la même application.

    F11 : plein écran      D : mode démo
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bridge"))

import webview  # pywebview

import lmu_bridge


def free_port(preferred: int = 8080) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Aucun port libre")


class Api:
    """Fonctions appelables depuis la page (window.pywebview.api)."""

    def __init__(self) -> None:
        self.window = None

    def toggle_fullscreen(self) -> None:
        if self.window:
            self.window.toggle_fullscreen()


def main() -> None:
    bridge = lmu_bridge.Bridge(30)
    threading.Thread(target=bridge.run, daemon=True).start()

    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), lmu_bridge.make_handler(bridge))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    api = Api()
    api.window = webview.create_window(
        "Dashboard LMU",
        f"http://127.0.0.1:{port}/",
        js_api=api,
        width=1600,
        height=900,
        min_size=(960, 540),
        background_color="#000000",
        text_select=False,
    )
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    main()
