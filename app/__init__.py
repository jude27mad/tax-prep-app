"""
App bootstrap.

On Windows + pytest-asyncio + ProactorEventLoop you can hit
"event loop already running / cannot close a running loop".
Force the Selector policy early so the test runner can manage the loop cleanly.
"""
from __future__ import annotations

import sys
import asyncio

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        # If anything odd happens (older python, pypy, etc), just continue.
        pass
