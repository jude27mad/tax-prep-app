#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app.efile.error_map import explain_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan CRA summaries for reject codes")
    parser.add_argument("summary_root", help="Directory containing daily summary JSON files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.summary_root)
    totals: Counter[str] = Counter()
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for submission in payload.get("submissions", []):
            response = submission.get("response", {})
            codes = submission.get("reject_codes") or response.get("codes") or []
            sbmt_id = submission.get("sbmt_ref_id")
            for code in codes:
                totals[(code, sbmt_id)] += 1
    for (code, sbmt_id), count in totals.most_common():
        suffix = f" (sbmt_ref_id={sbmt_id})" if sbmt_id else ""
        print(f"{code}: {count}{suffix} :: {explain_error(code)}")


if __name__ == "__main__":
    main()
