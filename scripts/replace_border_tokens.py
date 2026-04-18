"""Map border-accent/{opacity} to border-edge / border-edge-strong (CSS vars --color-border, --color-border-strong)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Longer / compound first
EXACT = [
    ("hover:border-accent/70", "hover:border-edge-strong"),
    ("hover:border-accent/35", "hover:border-edge"),
    ("focus-visible:ring-accent/60", "focus-visible:ring-edge-strong"),
    ("focus-visible:ring-accent/50", "focus-visible:ring-edge-strong"),
    ("focus:ring-1 focus:ring-accent/50", "focus:ring-1 focus:ring-edge-strong"),
]

# Strong tier (>= ~0.4)
for n in (85, 70, 60, 55, 50, 45, 40):
    EXACT.append((f"border-accent/{n}", "border-edge-strong"))

# Soft tier
for n in (35, 32, 30, 28, 25, 22, 20):
    EXACT.append((f"border-accent/{n}", "border-edge"))

# Checkbox / ring that used accent opacity
EXTRA = [
    ("border-accent/55", "border-edge-strong"),
    ("ring-accent/50", "ring-edge-strong"),
    ("ring-accent/60", "ring-edge-strong"),
    ("border-l-accent", "border-l-edge-strong"),
]

# Deduplicate EXACT order: run EXACT then EXTRA
REPLACEMENTS: list[tuple[str, str]] = []
seen: set[tuple[str, str]] = set()
for a, b in EXACT + EXTRA:
    if (a, b) not in seen:
        seen.add((a, b))
        REPLACEMENTS.append((a, b))


def main() -> int:
    nfiles = 0
    for path in sorted(ROOT.rglob("*.html")):
        if "venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            nfiles += 1
            print(path.relative_to(ROOT))
    print(f"Updated {nfiles} HTML files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
