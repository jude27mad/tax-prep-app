import httpx
from typing import Any

class EfileClient:
  def __init__(self, base_url: str, timeout: float = 15.0):
    self.base_url = base_url
    self.timeout = timeout

  async def send(self, data: bytes) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      r = await client.post(f"{self.base_url}/efile", content=data)
      r.raise_for_status()
      return r.json()
