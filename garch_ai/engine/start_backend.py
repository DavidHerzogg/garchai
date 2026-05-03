import argparse
import logging
import socket
import sys
import traceback
import os


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = int(os.getenv("PORT", 8000))


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def get_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass

    return None


def print_access_urls(port: int) -> None:
    lan_ip = get_lan_ip()
    print("")
    print("GARCH AI backend is starting")
    print(f"Bind address: http://0.0.0.0:{port}")
    print(f"Same device:  http://127.0.0.1:{port}/ping")
    print(f"Same device:  http://localhost:{port}/ping")
    if lan_ip:
        print(f"Phone/LAN:    http://{lan_ip}:{port}/ping")
        print(f"App .env:     EXPO_PUBLIC_ENGINE_URL=http://{lan_ip}:{port}")
    else:
        print("Phone/LAN:    Could not detect LAN IP automatically.")
        print("              Run ipconfig and use your IPv4 address.")
    print("")


def main() -> int:
    configure_logging()

    parser = argparse.ArgumentParser(description="Start the GARCH AI FastAPI backend.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = parser.parse_args()

    if not port_is_available(args.host, args.port):
        print(
            f"ERROR: Port {args.port} is already in use or blocked on {args.host}.",
            file=sys.stderr,
        )
        print("Find the process with:", file=sys.stderr)
        print(f"  netstat -ano | findstr :{args.port}", file=sys.stderr)
        print("Then stop that process or start with another port:", file=sys.stderr)
        print(f"  python start_backend.py --port 8001", file=sys.stderr)
        return 1

    print_access_urls(args.port)

    try:
        import uvicorn

        uvicorn.run(
            "server:app",
            host=args.host,
            port=args.port,
            log_level="info",
            access_log=True,
        )
        return 0
    except Exception:
        print("ERROR: Backend crashed during startup.", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
