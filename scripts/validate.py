"""Validate distributable skill metadata, references and provider manifests."""
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(root=ROOT):
    errors = []
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        try:
            if not text.startswith("---\n"):
                raise ValueError("missing frontmatter (or UTF-8 BOM present)")
            front = yaml.safe_load(text.split("---", 2)[1])
            if front.get("name") != path.parent.name:
                raise ValueError("name must match the skill folder")
            description = front.get("description")
            if not isinstance(description, str) or not description.strip() or len(description) > 1024:
                raise ValueError("description must be a nonempty string of at most 1024 characters")
        except (ValueError, IndexError, AttributeError, yaml.YAMLError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    # Validate links in active instructions and public README, excluding fenced code.
    for path in [root / "README.md", *(root / "skills").rglob("*.md")]:
        text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if re.match(r"[a-z]+://|#", link):
                continue
            target = link.split("#", 1)[0]
            if target and not (path.parent / target).exists():
                errors.append(f"{path.relative_to(root)}: missing reference {link}")
    for folder in (".claude-plugin", ".cursor-plugin"):
        try:
            manifest = json.loads((root / folder / "plugin.json").read_text(encoding="utf-8"))
            if manifest.get("name") != "claudor-loop" or not manifest.get("version"):
                errors.append(f"{folder}: missing name/version")
        except (OSError, ValueError) as exc:
            errors.append(f"{folder}: {exc}")
    marketplace = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    if marketplace["plugins"][0]["name"] != "claudor-loop":
        errors.append("Claude marketplace plugin name mismatch")
    if not (root / "skills/claudor-loop/scripts/runner.py").is_file():
        errors.append("Missing shared runner")
    return errors


if __name__ == "__main__":
    failures = validate()
    print("\n".join(failures) if failures else "Skill metadata, references and manifests passed.")
    sys.exit(bool(failures))
