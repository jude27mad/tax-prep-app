#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime

from app.efile.t183 import purge_expired


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge expired encrypted T183 records")
    parser.add_argument("base_dir", help="Base directory where T183 records are stored")
    args = parser.parse_args()
    removed = purge_expired(args.base_dir, as_of=datetime.utcnow())
    for path in removed:
        print(path)


if __name__ == "__main__":
    main()
