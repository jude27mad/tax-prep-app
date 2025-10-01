import httpx
from typing import Any

class EfileClient:
  def __init__(self, base_url: str, timeout: float = 15.0):
    self.base_url = base_url
    self.timeout = timeout

  async def send(self, data: bytes, *, content_type: str = "application/json") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=self.timeout) as client:
      headers = {"Content-Type": content_type}
      r = await client.post(f"{self.base_url}/efile", content=data, headers=headers)
      r.raise_for_status()
      if content_type == "application/xml":
        return {"status": "sent", "body": r.text}
      return r.json()
