"""
App bootstrap.

On Windows + pytest-asyncio + ProactorEventLoop you can hit
"event loop already running / cannot close a running loop".
Force the Selector policy early so the test runner can manage the loop cleanly.
"""
from __future__ import annotations

import sys
import asyncio
from contextlib import suppress

if sys.platform.startswith("win"):
    with suppress(Exception):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
