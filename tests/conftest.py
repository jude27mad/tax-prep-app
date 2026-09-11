import os
import pathlib
import secrets
import sys

os.environ.setdefault("AUTH_SESSION_SECRET", secrets.token_urlsafe(32))

p = str(pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, p) if p not in sys.path else None
