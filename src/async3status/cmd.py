#!/usr/bin/env python3
"""
async3cmd - Send IPC commands to async3status.
"""

import os
import socket
import sys


def main():
    """Entry point for the async3cmd command."""
    if len(sys.argv) < 2:
        print("Usage: async3cmd <command>", file=sys.stderr)
        print("Example: async3cmd module dunst update", file=sys.stderr)
        sys.exit(1)

    command = " ".join(sys.argv[1:])
    socket_path = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
        "async3status.sock"
    )

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        sock.sendall((command + "\n").encode())
        sock.close()
    except FileNotFoundError:
        print(f"Error: Socket not found at {socket_path}", file=sys.stderr)
        print("Is async3status running?", file=sys.stderr)
        sys.exit(1)
    except ConnectionRefusedError:
        print(f"Error: Connection refused to {socket_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
