#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Show summary of WATCH_LOG")
    parser.add_argument("--path", default="WATCH_LOG.md")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(json.dumps({"entries": 0, "message": "WATCH_LOG not found"}, indent=2))
        return

    text = path.read_text(encoding="utf-8")
    entries = len(re.findall(r"^##\s", text, flags=re.MULTILINE))
    scenes = [int(value) for value in re.findall(r"Scenes processed:\s(\d+)", text)]
    surfaced = len(re.findall(r"^\- Scene\s\d+", text, flags=re.MULTILINE))

    print(
        json.dumps(
            {
                "entries": entries,
                "total_scenes": sum(scenes),
                "surfaced_reactions": surfaced,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
