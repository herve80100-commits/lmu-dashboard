"""Lance le dashboard d'analyse Le Mans Ultimate.

    python run.py            → se connecte au jeu (Windows, plugin mémoire partagée activé)
    python run.py --demo     → télémétrie simulée, sans le jeu
"""
import argparse
import socket
import sys

from lmu_dashboard.server import Engine, serve


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> int:
    p = argparse.ArgumentParser(description="Dashboard d'analyse temps réel pour Le Mans Ultimate")
    p.add_argument("--demo", action="store_true", help="utiliser une télémétrie simulée (sans le jeu)")
    p.add_argument("--speed", type=float, default=1.0, help="démo : vitesse de simulation (ex. 4)")
    p.add_argument("--port", type=int, default=8080, help="port HTTP (défaut 8080)")
    p.add_argument("--host", default="0.0.0.0", help="adresse d'écoute (défaut : tout le réseau local)")
    p.add_argument("--hz", type=float, default=50.0, help="fréquence de lecture de la télémétrie (défaut 50)")
    args = p.parse_args()

    if args.demo:
        from lmu_dashboard.demo import DemoSource
        source = DemoSource(speed=args.speed)
    else:
        from lmu_dashboard.shared_memory import SharedMemorySource
        try:
            source = SharedMemorySource()
        except RuntimeError as exc:
            print(exc)
            return 1

    engine = Engine(source, hz=args.hz)
    if args.demo:
        print("Préparation de la démo (3 tours simulés)…")
        source.warmup(engine.analyzer, laps=3)
    httpd = serve(engine, args.host, args.port)
    print(f"LMU Analyzer prêt → http://localhost:{args.port}  (tablette / autre écran : http://{local_ip()}:{args.port})")
    if not args.demo:
        print("En attente de Le Mans Ultimate… (lance une session, le dashboard se met à jour tout seul)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stopped.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
