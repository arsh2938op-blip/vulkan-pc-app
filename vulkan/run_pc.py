#!/usr/bin/env python3
"""
Vulkan — PC control application entry point.

Usage:
    python run_pc.py                 # opens the desktop window
    python run_pc.py --browser       # serve only; open the UI yourself
    python run_pc.py --robot 1a2b    # connect to a specific robot serial
    python run_pc.py --port 9000
"""

import argparse
import socket
import threading
import time

from vulkan import config, server


def lan_ip():
    """Best-effort LAN IP so the console can print the phone URL."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    p = argparse.ArgumentParser(description="Vulkan robot control app")
    p.add_argument("--robot", help="robot serial (4 chars) or IP/hostname")
    p.add_argument("--port", type=int, default=config.PORT)
    p.add_argument("--host", default=config.HOST)
    p.add_argument("--browser", action="store_true",
                   help="don't open a native window; just serve")
    args = p.parse_args()

    if args.robot:
        config.DEFAULT_ROBOT = args.robot

    url = f"http://127.0.0.1:{args.port}/"
    print("\n  \033[94m=== VULKAN ===\033[0m")
    print(f"  Desktop UI : {url}")
    print(f"  Phone UI   : http://{lan_ip()}:{args.port}/m")
    print("  (phone must be on the same Wi-Fi as this PC)\n")

    if args.browser:
        server.run(args.host, args.port)
        return

    # Native window via pywebview, with the server on a background thread.
    try:
        import webview
    except ImportError:
        print("  pywebview not installed — serving in browser mode instead.")
        print("  (pip install pywebview, or just use --browser)\n")
        server.run(args.host, args.port)
        return

    t = threading.Thread(target=server.run, args=(args.host, args.port), daemon=True)
    t.start()
    time.sleep(1.2)  # let the server bind before the window loads it
    webview.create_window("Vulkan", url, width=1180, height=780,
                          background_color="#0a1628")
    webview.start()


if __name__ == "__main__":
    main()
