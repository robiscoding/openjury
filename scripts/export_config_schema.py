#!/usr/bin/env python3
"""Export JuryConfig JSON Schema for IDE autocomplete and validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from openjury.config import JuryConfig  # noqa: E402

OUTPUT = REPO_ROOT / "docs" / "config.schema.json"


def main() -> None:
    schema = JuryConfig.model_json_schema()
    OUTPUT.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
