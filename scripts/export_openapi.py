from __future__ import annotations

import json
from pathlib import Path

from markguardiola.api.app import app


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    destination = repository_root / "contracts" / "openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(destination)


if __name__ == "__main__":
    main()
