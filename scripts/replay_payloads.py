#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.efile.transmit import EfileClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay stored EFILE payloads")
    parser.add_argument("payload_dir", help="Directory containing *_envelope.xml files")
    parser.add_argument("--endpoint", required=True, help="Base URL of the EFILE endpoint")
    return parser.parse_args()


def _extract_sbmt_ref_id(path: Path) -> str:
    name = path.stem
    return name.split("_")[0] if "_" in name else "UNKNOWN"


async def _send_file(client: EfileClient, path: Path) -> tuple[str, str, str]:
    response = await client.send(path.read_bytes(), content_type="application/xml")
    return path.name, response.get("status", "sent"), _extract_sbmt_ref_id(path)


async def _run(args: argparse.Namespace) -> None:
    client = EfileClient(args.endpoint)
    tasks = []
    payload_dir = Path(args.payload_dir)
    for path in sorted(payload_dir.glob("*_envelope.xml")):
        tasks.append(_send_file(client, path))
    for name, status, sbmt_ref_id in await asyncio.gather(*tasks):
        print(f"{name} [sbmt_ref_id={sbmt_ref_id}]: {status}")


def main() -> None:
    args = parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
