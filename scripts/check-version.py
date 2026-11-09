"""Check release metadata without loading credentials or application services."""
import json
import re
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = (root / "VERSION").read_text().strip()
assert re.fullmatch(r"0|[1-9]\d*", version.split(".")[0]) and re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version), "Use X.Y.Z semantic versioning"
assert tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]["version"] == version
assert json.loads((root / "web/package.json").read_text())["version"] == version
lock = tomllib.loads((root / "backend/uv.lock").read_text())
assert next(p for p in lock["package"] if p["name"] == "brightwater")["version"] == version
print("Release metadata agrees:", version)
