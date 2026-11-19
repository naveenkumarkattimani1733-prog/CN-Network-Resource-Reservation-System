"""Small client used by the reservation server to contact the SDN controller."""

import json
import socket
from typing import Dict

from config import SDN_SOCKET_PATH


class SdnControllerError(RuntimeError):
    pass


class SdnControllerClient:
    def __init__(self, socket_path: str = SDN_SOCKET_PATH, timeout: float = 4.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def _request(self, payload: dict) -> dict:
        data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)
                sock.sendall(data)
                chunks = bytearray()
                while b"\n" not in chunks:
                    part = sock.recv(4096)
                    if not part:
                        break
                    chunks.extend(part)
                    if len(chunks) > 65536:
                        raise SdnControllerError("Controller response was too large")
        except (OSError, TimeoutError) as exc:
            raise SdnControllerError(f"Cannot contact SDN controller: {exc}") from exc

        if not chunks:
            raise SdnControllerError("The SDN controller closed the control connection")
        try:
            response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SdnControllerError("The SDN controller returned an invalid response") from exc
        if not response.get("ok"):
            raise SdnControllerError(response.get("error", "SDN policy update failed"))
        return response

    def apply_quotas(self, quotas: Dict[str, float], capacity_mbps: float) -> dict:
        return self._request({
            "action": "APPLY",
            "capacity_mbps": capacity_mbps,
            "quotas": quotas,
        })

    def reset(self, capacity_mbps: float) -> dict:
        return self.apply_quotas({}, capacity_mbps)
