#!/usr/bin/env python
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail if coverage below threshold")
    parser.add_argument("coverage_xml", help="Path to coverage XML report")
    parser.add_argument("--minimum", type=float, default=85.0, help="Minimum coverage percentage")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tree = ET.parse(args.coverage_xml)
    root = tree.getroot()
    line_rate = float(root.attrib.get("line-rate", 0.0)) * 100
    if line_rate < args.minimum:
        raise SystemExit(f"Coverage {line_rate:.2f}% below threshold {args.minimum}%")
    print(f"Coverage OK: {line_rate:.2f}% >= {args.minimum}%")


if __name__ == "__main__":
    main()
