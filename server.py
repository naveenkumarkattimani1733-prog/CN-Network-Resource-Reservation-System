"""TCP reservation server. Run this process inside Mininet host h4."""

import argparse
import json
import logging
import socketserver
import threading
import time

from config import CAPACITY_MBPS, SERVER_PORT
from reservation_manager import ReservationManager
from sdn_client import SdnControllerClient


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ReservationRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        client_ip = self.client_address[0]
        logging.info("Client connected: %s", client_ip)
        for raw_line in self.rfile:
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line.decode("utf-8"))
                response = self.server.manager.handle_request(payload, client_ip)
            except json.JSONDecodeError:
                response = {"ok": False, "error": "Invalid JSON request."}
            except Exception as exc:
                logging.exception("Request processing failed")
                response = {"ok": False, "error": f"Server error: {exc}"}
            encoded = (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
            self.wfile.write(encoded)
            self.wfile.flush()


def expiry_worker(manager: ReservationManager, stop_event: threading.Event):
    while not stop_event.wait(1.0):
        expired = manager.expire()
        if expired:
            logging.info("Expired reservations: %s", ", ".join(expired))


def main():
    parser = argparse.ArgumentParser(description="Network Resource Reservation TCP server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    parser.add_argument("--capacity-mbps", type=float, default=CAPACITY_MBPS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    controller = SdnControllerClient()
    manager = ReservationManager(controller, capacity_mbps=args.capacity_mbps)

    if manager.sync_policy():
        logging.info("SDN controller connected; initial empty reservation policy applied.")
    else:
        logging.warning("SDN controller is not ready yet: %s", manager.status().get("sdn_warning"))

    stop_event = threading.Event()
    worker = threading.Thread(target=expiry_worker, args=(manager, stop_event), daemon=True)
    worker.start()

    with ThreadedTCPServer((args.host, args.port), ReservationRequestHandler) as server:
        server.manager = manager
        logging.info("Reservation server listening on %s:%d (capacity %.1f Mbps)", args.host, args.port, args.capacity_mbps)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            logging.info("Stopping reservation server")
        finally:
            stop_event.set()
            worker.join(timeout=2)


if __name__ == "__main__":
    main()
