from pathlib import Path

class RetentionStore:
  def __init__(self, base_dir: str):
    self.base = Path(base_dir)
    self.base.mkdir(parents=True, exist_ok=True)

  def put(self, key: str, data: bytes) -> str:
    p = self.base / key
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p)

  def get(self, key: str) -> bytes:
    p = self.base / key
    return p.read_bytes()
