from __future__ import annotations

import json
from typing import Any


def print_json(data: Any) -> None:
    if hasattr(data, "model_dump"):
        print(json.dumps(data.model_dump(), indent=2))
        return
    print(json.dumps(data, indent=2))
