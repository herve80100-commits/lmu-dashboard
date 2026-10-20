"""Serveur local : lit la télémétrie en continu et diffuse l'analyse au navigateur.

- GET /            → le dashboard (dossier web/)
- GET /stream      → flux temps réel (Server-Sent Events, ~10 images/s)
- GET /api/state   → dernier instantané en JSON
"""
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .analyzer import Analyzer

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class Engine:
    """Boucle de lecture : source → analyseur → instantané JSON partagé."""

    def __init__(self, source, hz: float = 50.0, publish_hz: float = 10.0):
        self.source = source
        self.analyzer = Analyzer()
        self.hz = hz
        self.publish_every = 1.0 / publish_hz
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.payload = json.dumps({"connected": False, "source": source.name})
        self.seq = 0
        self.stopped = threading.Event()

    def run(self) -> None:
        period = 1.0 / self.hz
        last_pub = 0.0
        while not self.stopped.is_set():
            start = time.monotonic()
            sample = self.source.read()
            if sample is not None:
                self.analyzer.update(sample)
            if start - last_pub >= self.publish_every:
                last_pub = start
                snap = self.analyzer.snapshot(self.source.name) if sample is not None \
                    else {"connected": False, "source": self.source.name}
                snap["hz"] = self.hz
                data = json.dumps(snap, separators=(",", ":"))
                with self.cond:
                    self.payload, self.seq = data, self.seq + 1
                    self.cond.notify_all()
            time.sleep(max(0.0, period - (time.monotonic() - start)))

    def wait(self, seq: int, timeout: float = 5.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != seq or self.stopped.is_set(), timeout)
            return self.seq, self.payload


def make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/stream":
                return self._stream()
            if path == "/api/state":
                return self._send(200, engine.payload.encode(), "application/json; charset=utf-8")
            return self._static(path)

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _static(self, path):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (WEB_DIR / rel).resolve()
            if WEB_DIR not in target.parents or not target.is_file():
                return self._send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            seq = -1
            try:
                while not engine.stopped.is_set():
                    seq, payload = engine.wait(seq)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    return Handler


def serve(engine: Engine, host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(engine))
    httpd.daemon_threads = True
    threading.Thread(target=engine.run, daemon=True).start()
    return httpd
