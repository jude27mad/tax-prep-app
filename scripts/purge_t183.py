#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.efile.t183 import purge_expired, purge_t2183


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge expired encrypted T183 records")
    parser.add_argument("base_dir", help="Base directory where T183 records are stored")
    args = parser.parse_args()
    as_of = datetime.now(timezone.utc)
    removed = purge_expired(args.base_dir, as_of=as_of)
    removed += purge_t2183(args.base_dir, as_of=as_of)
    for path in removed:
        print(path)


if __name__ == "__main__":
    main()
