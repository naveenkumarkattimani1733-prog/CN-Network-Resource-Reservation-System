"""Thread-safe reservation logic, independent of the TCP and SDN layers."""

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import threading
import uuid
from typing import Dict, Optional

from config import (
    CAPACITY_MBPS,
    CLIENTS,
    MAX_RESERVATION_SECONDS,
    MIN_RESERVATION_SECONDS,
)


@dataclass
class Reservation:
    reservation_id: str
    client_id: str
    client_ip: str
    bandwidth_mbps: float
    duration_sec: int
    created_at: str
    expires_at: str
    status: str = "ACTIVE"

    def public_dict(self) -> dict:
        return asdict(self)


class ReservationManager:
    def __init__(self, controller, capacity_mbps: float = CAPACITY_MBPS):
        if capacity_mbps <= 0:
            raise ValueError("Capacity must be greater than zero")
        self.controller = controller
        self.capacity_mbps = float(capacity_mbps)
        self._lock = threading.RLock()
        self._active: Dict[str, Reservation] = {}
        self._history = deque(maxlen=200)
        self._sdn_synced = False
        self._last_sdn_error: Optional[str] = None

    def _reserved_total_locked(self) -> float:
        return round(sum(item.bandwidth_mbps for item in self._active.values()), 3)

    def _quotas_locked(self) -> Dict[str, float]:
        quotas = {ip: 0.0 for ip in CLIENTS}
        for item in self._active.values():
            quotas[item.client_ip] += item.bandwidth_mbps
        return {ip: round(value, 3) for ip, value in quotas.items()}

    def _apply_policy_locked(self) -> bool:
        try:
            self.controller.apply_quotas(self._quotas_locked(), self.capacity_mbps)
            self._sdn_synced = True
            self._last_sdn_error = None
            return True
        except Exception as exc:
            self._sdn_synced = False
            self._last_sdn_error = str(exc)
            return False

    def sync_policy(self) -> bool:
        with self._lock:
            return self._apply_policy_locked()

    def _expire_locked(self, now: datetime) -> list:
        expired = []
        for reservation_id, item in list(self._active.items()):
            expiry = datetime.fromisoformat(item.expires_at)
            if expiry <= now:
                del self._active[reservation_id]
                item.status = "EXPIRED"
                self._history.append(item.public_dict())
                expired.append(reservation_id)
        if expired:
            self._apply_policy_locked()
        return expired

    def expire(self) -> list:
        with self._lock:
            return self._expire_locked(datetime.now(timezone.utc))

    def reserve(self, client_ip: str, bandwidth_mbps: float, duration_sec: int) -> dict:
        if client_ip not in CLIENTS:
            return {"accepted": False, "reason": "This host is not registered as a project client."}
        try:
            bandwidth = float(bandwidth_mbps)
            duration = int(duration_sec)
        except (TypeError, ValueError):
            return {"accepted": False, "reason": "Bandwidth and duration must be numbers."}
        if bandwidth <= 0 or bandwidth > self.capacity_mbps:
            return {"accepted": False, "reason": f"Bandwidth must be greater than 0 and no more than {self.capacity_mbps:g} Mbps."}
        if duration < MIN_RESERVATION_SECONDS or duration > MAX_RESERVATION_SECONDS:
            return {"accepted": False, "reason": f"Duration must be between {MIN_RESERVATION_SECONDS} and {MAX_RESERVATION_SECONDS} seconds."}

        with self._lock:
            now = datetime.now(timezone.utc)
            self._expire_locked(now)
            currently_reserved = self._reserved_total_locked()
            available = round(self.capacity_mbps - currently_reserved, 3)
            if bandwidth > available + 1e-9:
                return {
                    "accepted": False,
                    "reason": "Insufficient available bandwidth.",
                    "requested_mbps": bandwidth,
                    "available_mbps": available,
                }

            reservation_id = "R-" + uuid.uuid4().hex[:8].upper()
            item = Reservation(
                reservation_id=reservation_id,
                client_id=CLIENTS[client_ip]["name"],
                client_ip=client_ip,
                bandwidth_mbps=round(bandwidth, 3),
                duration_sec=duration,
                created_at=now.isoformat(timespec="seconds"),
                expires_at=(now + timedelta(seconds=duration)).isoformat(timespec="seconds"),
            )
            self._active[reservation_id] = item
            if not self._apply_policy_locked():
                del self._active[reservation_id]
                failure = self._last_sdn_error or "The SDN controller did not apply the policy."
                self._apply_policy_locked()
                return {"accepted": False, "reason": f"Reservation not committed because SDN policy installation failed: {failure}"}

            return {
                "accepted": True,
                "message": "Reservation accepted and SDN policy installed.",
                "reservation": item.public_dict(),
                "resource": self._resource_locked(),
            }

    def release(self, client_ip: str, reservation_id: str) -> dict:
        with self._lock:
            self._expire_locked(datetime.now(timezone.utc))
            item = self._active.get(reservation_id)
            if item is None:
                return {"released": False, "reason": "Reservation was not found or has already expired."}
            if item.client_ip != client_ip:
                return {"released": False, "reason": "Only the client that created a reservation can release it."}
            del self._active[reservation_id]
            item.status = "RELEASED"
            self._history.append(item.public_dict())
            synced = self._apply_policy_locked()
            return {
                "released": True,
                "message": "Reservation released.",
                "reservation": item.public_dict(),
                "resource": self._resource_locked(),
                "sdn_synced": synced,
                "sdn_warning": self._last_sdn_error,
            }

    def _resource_locked(self) -> dict:
        reserved = self._reserved_total_locked()
        return {
            "capacity_mbps": self.capacity_mbps,
            "reserved_mbps": reserved,
            "available_mbps": round(self.capacity_mbps - reserved, 3),
            "utilization_percent": round((reserved / self.capacity_mbps) * 100, 2),
        }

    def status(self) -> dict:
        with self._lock:
            self._expire_locked(datetime.now(timezone.utc))
            return {
                "resource": self._resource_locked(),
                "active_reservations": [item.public_dict() for item in self._active.values()],
                "sdn_synced": self._sdn_synced,
                "sdn_warning": self._last_sdn_error,
            }

    def list_reservations(self) -> dict:
        with self._lock:
            self._expire_locked(datetime.now(timezone.utc))
            return {
                "active": [item.public_dict() for item in self._active.values()],
                "recent_history": list(self._history),
            }

    def handle_request(self, payload: dict, client_ip: str) -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Request must be a JSON object."}
        action = str(payload.get("action", "")).upper()
        if action == "RESERVE":
            result = self.reserve(client_ip, payload.get("bandwidth_mbps"), payload.get("duration_sec"))
            return {"ok": True, **result}
        if action == "RELEASE":
            result = self.release(client_ip, str(payload.get("reservation_id", "")))
            return {"ok": True, **result}
        if action == "STATUS":
            return {"ok": True, **self.status()}
        if action == "LIST":
            return {"ok": True, **self.list_reservations()}
        return {"ok": False, "error": "Unknown action. Use RESERVE, RELEASE, STATUS or LIST."}
