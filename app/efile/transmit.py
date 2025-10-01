import asyncio
import time
from typing import Any, Optional

import httpx

from app.config import get_settings

_CIRCUITS: dict[str, dict[str, float | int]] = {}


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker is open for the requested endpoint."""


class EfileClient:
    def __init__(self, base_url: str, timeout: float = 15.0, *, label: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.label = label or self.base_url
        settings = get_settings()
        self.max_retries = settings.transmit_max_retries
        self.backoff = settings.transmit_backoff_factor
        self.circuit_threshold = settings.transmit_circuit_threshold
        self.circuit_cooldown = settings.transmit_circuit_cooldown

    def _state(self) -> dict[str, float | int]:
        state = _CIRCUITS.setdefault(self.label, {"failures": 0, "open_until": 0.0})
        now = time.time()
        open_until = float(state.get("open_until", 0.0))
        if open_until and now < open_until:
            raise CircuitOpenError(f"Circuit open for {self.label} until {open_until}")
        if open_until and now >= open_until:
            state["open_until"] = 0.0
            state["failures"] = 0
        return state

    @staticmethod
    def _record_failure(state: dict[str, float | int], cooldown: float, threshold: int) -> None:
        state["failures"] = int(state.get("failures", 0)) + 1
        if state["failures"] >= threshold:
            state["open_until"] = time.time() + cooldown

    @staticmethod
    def _record_success(state: dict[str, float | int]) -> None:
        state["failures"] = 0
        state["open_until"] = 0.0

    async def send(self, data: bytes, *, content_type: str = "application/json") -> dict[str, Any]:
        state = self._state()
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt < self.max_retries:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    headers = {"Content-Type": content_type}
                    response = await client.post(f"{self.base_url}/efile", content=data, headers=headers)
                    response.raise_for_status()
                    self._record_success(state)
                    if content_type == "application/xml":
                        return {"status": "sent", "body": response.text}
                    return response.json()
            except Exception as exc:  # pragma: no cover - network variability
                last_error = exc
                attempt += 1
                self._record_failure(state, self.circuit_cooldown, self.circuit_threshold)
                sleep_for = self.backoff * (2 ** (attempt - 1))
                await asyncio.sleep(sleep_for)
        raise RuntimeError(f"Failed to transmit after {self.max_retries} attempts: {last_error}")
