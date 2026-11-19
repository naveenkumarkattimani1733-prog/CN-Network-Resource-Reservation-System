"""Shared settings for the Network Resource Reservation System."""

CAPACITY_MBPS = 100
SERVER_IP = "10.0.0.4"
SERVER_PORT = 5000
SDN_SOCKET_PATH = "/tmp/nrr_sdn_controller.sock"
SERVER_SWITCH_PORT = 4
SERVER_SWITCH_PORT_NAME = "s1-eth4"

CLIENTS = {
    "10.0.0.1": {"name": "h1", "queue_id": 1},
    "10.0.0.2": {"name": "h2", "queue_id": 2},
    "10.0.0.3": {"name": "h3", "queue_id": 3},
}

MAX_RESERVATION_SECONDS = 3600
MIN_RESERVATION_SECONDS = 5
