"""One-off migration: replace legacy arbitrary hex Tailwind classes with semantic tokens."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Longest / most specific first
REPLACEMENTS: list[tuple[str, str]] = [
    ("focus-visible:ring-offset-[#0B0B0B]", "focus-visible:ring-offset-background"),
    ("focus-visible:ring-[#C9A96E]/60", "focus-visible:ring-accent/60"),
    ("focus-visible:ring-[#C9A96E]/50", "focus-visible:ring-accent/50"),
    ("focus:ring-1 focus:ring-[#C9A96E]/50", "focus:ring-1 focus:ring-accent/50"),
    ("bg-[#0B0B0B]/95", "bg-background/95"),
    ("bg-[#0B0B0B]/88", "bg-background/88"),
    ("bg-[#0B0B0B]/70", "bg-background/70"),
    ("border-[rgba(201,169,110,0.32)]", "border-accent/32"),
    ("border-[rgba(201,169,110,0.28)]", "border-accent/28"),
    ("border-[rgba(201,169,110,0.22)]", "border-accent/22"),
    ("border-[rgba(201,169,110,0.4)]", "border-accent/40"),
    ("border-[#C9A96E]/85", "border-accent/85"),
    ("border-[#C9A96E]/60", "border-accent/60"),
    ("border-[#C9A96E]/55", "border-accent/55"),
    ("border-[#C9A96E]/50", "border-accent/50"),
    ("border-[#C9A96E]/45", "border-accent/45"),
    ("border-[#C9A96E]/40", "border-accent/40"),
    ("border-[#C9A96E]/35", "border-accent/35"),
    ("border-[#C9A96E]/30", "border-accent/30"),
    ("border-[#C9A96E]/25", "border-accent/25"),
    ("border-[#C9A96E]/20", "border-accent/20"),
    ("border-[#C9A96E]", "border-accent"),
    ("hover:border-[#C9A96E]/70", "hover:border-accent/70"),
    ("hover:border-[#C9A96E]", "hover:border-accent"),
    ("hover:bg-[#C9A96E]/10", "hover:bg-accent/10"),
    ("hover:bg-[#C9A96E]", "hover:bg-accent"),
    ("has-[:checked]:border-[#C9A96E]", "has-[:checked]:border-accent"),
    ("bg-[#C9A96E]", "bg-accent"),
    ("bg-[#141414]", "bg-surface"),
    ("bg-[#0A0A0A]", "bg-void"),
    ("bg-[#101010]", "bg-ink"),
    ("bg-[#111111]", "bg-canvas"),
    ("bg-[#121212]", "bg-elevated"),
    ("bg-[#0B0B0B]", "bg-background"),
    ("text-[#F5F1E8]", "text-heading"),
    ("text-[#F3EFE7]", "text-cream"),
    ("text-[#E4DFD5]", "text-foreground"),
    ("text-[#D9D2C6]", "text-drift"),
    ("text-[#D8D1C5]", "text-note"),
    ("text-[#D8BB86]", "text-accent-hover"),
    ("text-[#D7D2C9]", "text-nav"),
    ("text-[#D7A3A3]", "text-danger"),
    ("text-[#C9A96E]", "text-accent"),
    ("text-[#C6BFB2]", "text-mist"),
    ("text-[#BDB6AA]", "text-muted"),
    ("text-[#8f8a80]", "text-placeholder"),
    ("text-[#8A8278]", "text-placeholder"),
    ("text-[#6f685a]", "text-dim"),
    ("text-[#e7bcbc]", "text-danger-soft"),
    ("placeholder:text-[#6f685a]", "placeholder:text-dim"),
    ("accent-[#C9A96E]", "accent-accent"),
    ("ring-[#C9A96E]/50", "ring-accent/50"),
    ("focus:border-[#C9A96E]", "focus:border-accent"),
    ("hover:text-[#E4DFD5]", "hover:text-foreground"),
    ("hover:text-[#C9A96E]", "hover:text-accent"),
    ("hover:text-[#D8BB86]", "hover:text-accent-hover"),
    ("hover:border-[#E4DFD5]", "hover:border-foreground"),
    ("border-[#0B0B0B]", "border-background"),
    ("text-[#0B0B0B]", "text-background"),
    ("border-l-[#C9A96E]", "border-l-accent"),
    ("text-white", "text-nav"),
]


def main() -> int:
    changed = 0
    for path in sorted(ROOT.rglob("*.html")):
        rel = path.relative_to(ROOT)
        if "venv" in rel.parts or "node_modules" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            changed += 1
            print(rel)
    print(f"Updated {changed} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
