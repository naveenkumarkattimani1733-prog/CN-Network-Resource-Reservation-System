"""Command-line TCP client for bandwidth reservation requests."""

import argparse
import json
import socket
import sys

from config import SERVER_IP, SERVER_PORT


def send_request(server: str, port: int, payload: dict) -> dict:
    request = (json.dumps(payload) + "\n").encode("utf-8")
    with socket.create_connection((server, port), timeout=5) as sock:
        sock.settimeout(8)
        sock.sendall(request)
        chunks = bytearray()
        while b"\n" not in chunks:
            block = sock.recv(4096)
            if not block:
                break
            chunks.extend(block)
            if len(chunks) > 65536:
                raise RuntimeError("Server response was too large")
    if not chunks:
        raise RuntimeError("Reservation server returned an empty response")
    return json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))


def print_response(response: dict):
    print(json.dumps(response, indent=2))
    if response.get("accepted") is False or response.get("released") is False or response.get("ok") is False:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Network Resource Reservation client")
    parser.add_argument("--server", default=SERVER_IP, help=f"Reservation server IP (default: {SERVER_IP})")
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    reserve = subparsers.add_parser("reserve", help="Request a bandwidth reservation")
    reserve.add_argument("--bandwidth", type=float, required=True, help="Requested bandwidth in Mbps")
    reserve.add_argument("--duration", type=int, required=True, help="Reservation duration in seconds")

    release = subparsers.add_parser("release", help="Release an active reservation")
    release.add_argument("--reservation-id", required=True)

    subparsers.add_parser("status", help="Show capacity and active reservations")
    subparsers.add_parser("list", help="Show active and recently completed reservations")

    args = parser.parse_args()
    if args.command == "reserve":
        payload = {"action": "RESERVE", "bandwidth_mbps": args.bandwidth, "duration_sec": args.duration}
    elif args.command == "release":
        payload = {"action": "RELEASE", "reservation_id": args.reservation_id}
    elif args.command == "status":
        payload = {"action": "STATUS"}
    else:
        payload = {"action": "LIST"}

    try:
        print_response(send_request(args.server, args.port, payload))
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
