import asyncio
import pathlib
import sys

p = str(pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, p) if p not in sys.path else None

# Ensure Playwright can spawn subprocesses on Windows (needs Proactor loop policy).
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
