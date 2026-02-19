#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from watch_session import _model_dump, _parse_target, fetch_script_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch script text only")
    parser.add_argument("query", help="Title query")
    parser.add_argument("--movie", action="store_true", help="Treat query as movie")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--episode", type=int, default=None)
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--timeout-sec", type=int, default=15)
    args = parser.parse_args()

    target = _parse_target(args.query, movie=args.movie, season=args.season, episode=args.episode)
    source, trace, warnings = fetch_script_text(target, timeout_sec=args.timeout_sec, source_url=args.source_url)
    payload = {
        "target": _model_dump(target),
        "source": _model_dump(source),
        "trace": trace,
        "warnings": warnings,
        "script_preview": (source.script_text or "")[:1000],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
