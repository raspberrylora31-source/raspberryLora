#!/usr/bin/env python3
"""Download the public YOLOv5 gun+knife weights to models/best.pt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from detector import (  # noqa: E402
    DEFAULT_WEAPON_MODEL,
    WEAPON_WEIGHT_SOURCES,
    ensure_weapon_weights,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a public YOLOv5 weapon-detection checkpoint"
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_WEAPON_MODEL,
        help=f"Destination path (default: {DEFAULT_WEAPON_MODEL})",
    )
    args = parser.parse_args()
    print("Source:")
    for source in WEAPON_WEIGHT_SOURCES:
        print(f"  {source['label']}")
        print(f"    {source['url']}")
        print(f"    classes={list(source['classes'])}")
    path = ensure_weapon_weights(args.output, download=True)
    print(f"Weapon model ready: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
