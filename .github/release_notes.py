"""Extract the release-notes section for a tag from the bilingual changelogs.

Usage: python .github/release_notes.py v1.4.0 > release_notes.md

Looks up the "## vX.Y.Z" section in CHANGELOG.zh-CN.md and CHANGELOG.md
(run from the repo root) and prints both, zh first. Falls back to a link
to the changelog when the section is missing, so the release is never
published with an empty body.
"""
import io
import re
import sys

REPO = "noahsarkcc/smartdiff"


def extract_section(path: str, version: str):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(
        rf"^(## v{re.escape(version)}\b[^\n]*\n.*?)(?=^## v|\Z)",
        text, re.M | re.S)
    return m.group(1).strip() if m else None


def main():
    if len(sys.argv) < 2:
        print("usage: release_notes.py <tag>", file=sys.stderr)
        return 1
    version = sys.argv[1].strip().lstrip("vV")
    zh = extract_section("CHANGELOG.zh-CN.md", version)
    en = extract_section("CHANGELOG.md", version)

    parts = []
    if zh:
        parts.append(zh)
    if en:
        parts.append(en)
    if not parts:
        parts.append(
            f"See [CHANGELOG.md](https://github.com/{REPO}/blob/main/CHANGELOG.md) "
            f"for details.")

    out = "\n\n---\n\n".join(parts) + "\n"
    sys.stdout.buffer.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
