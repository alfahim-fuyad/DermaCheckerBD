#!/usr/bin/env python3
"""Rename the user-visible brand 'DermaCheckerBD' / 'DermaCheckerBD' to 'DermaCheckerBD'
across all source files. Does NOT rename the internal Python package `dermacheckerbd`
(that's not user-visible)."""
import os
import re
import sys

ROOT = "/home/z/my-project"

# Files to scan. Skip binary PDFs, .git, skills, staticfiles, __pycache__, db.
SKIP_DIRS = {".git", "skills", "staticfiles", "__pycache__", "db", "media", "upload"}
SKIP_EXTENSIONS = {".pdf", ".pyc", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico"}

# 1) Service names in render.yaml
SERVICE_NAME_RENAMES = [
    ("dermacheckerbd-web",     "dermacheckerbd-web"),
    ("dermacheckerbd-db",      "dermacheckerbd-db"),
    ("dermacheckerbd-migrate", "dermacheckerbd-migrate"),
    ("dermacheckerbd",         "dermacheckerbd"),  # DB name 'dermacheckerbd' -> 'dermacheckerbd'
]

# 2) User-visible brand renames (apply AFTER service renames if needed)
BRAND_RENAMES = [
    # Navbar/footer split-brand pattern: `DermaCheckerBD`
    # Replace with a single span containing the full brand.
    ('DermaCheckerBD',
     'DermaCheckerBD'),
    # Full forms
    ('DermaCheckerBD', 'DermaCheckerBD'),
    ('DermaCheckerBD Assistant', 'DermaCheckerBD Assistant'),
    ('DermaCheckerBD', 'DermaCheckerBD'),  # standalone fallback (last)
]


def should_skip(path: str) -> bool:
    parts = path.split(os.sep)
    for skip in SKIP_DIRS:
        if skip in parts:
            return True
    ext = os.path.splitext(path)[1].lower()
    if ext in SKIP_EXTENSIONS:
        return True
    return False


def walk_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if should_skip(full):
                continue
            yield full


def transform(text: str) -> tuple[str, int]:
    """Apply all renames in order. Return (new_text, total_replacements)."""
    total = 0
    # Service renames first (lowercase identifiers)
    for old, new in SERVICE_NAME_RENAMES:
        text, n = re.subn(re.escape(old), new, text)
        total += n
    # Brand renames (longest first to avoid partial matches)
    for old, new in BRAND_RENAMES:
        text, n = re.subn(re.escape(old), new, text)
        total += n
    return text, total


def main():
    grand_total = 0
    files_changed = []
    for full in walk_files():
        try:
            with open(full, "r", encoding="utf-8") as f:
                original = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        new_text, n = transform(original)
        if n > 0:
            with open(full, "w", encoding="utf-8") as f:
                f.write(new_text)
            files_changed.append((full, n))
            grand_total += n
    print(f"Total replacements: {grand_total}")
    print(f"Files changed: {len(files_changed)}")
    for path, n in sorted(files_changed):
        rel = os.path.relpath(path, ROOT)
        print(f"  {n:3d}  {rel}")


if __name__ == "__main__":
    main()
