"""Generate the GitHub release body from CHANGELOG.md (English only).

Usage:
  python .github/release_notes.py <tag> [prev_tag] > release_notes.md
  python .github/release_notes.py --title <tag>     # "vX.Y.Z - <summary>"

- Extracts the "## vX.Y.Z" section of CHANGELOG.md for <tag> and drops
  technical subsections (bold titles matching the blacklist below), so the
  release page stays user-facing.
- Versions between prev_tag (exclusive) and <tag> that never got their own
  release are summarized as one "Also includes vX.Y.Z: <intro line>" each.
- Appends a "Full Changelog" compare link when prev_tag is given.
- Falls back to a CHANGELOG link when the section is missing, so a release
  is never published with an empty body.
"""
import re
import sys

REPO = "noahsarkcc/smartdiff"
CHANGELOG = "CHANGELOG.md"

# Bold subsection titles that are developer/infra detail, not user-facing.
BLACKLIST = re.compile(r"tests?|api|infrastructure|internal|\bci\b", re.I)

SECTION_RE = re.compile(r"^## v(\d+(?:\.\d+)*)([^\n]*)\n(.*?)(?=^## v|\Z)",
                        re.M | re.S)
BOLD_TITLE_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")


def parse_version(s) -> tuple:
    nums = []
    for p in str(s).strip().lstrip("vV").split("."):
        m = re.match(r"\d+", p.strip())
        nums.append(int(m.group()) if m else 0)
    return tuple(nums) if nums else (0,)


def load_sections():
    """Return [(version_tuple, heading_line, body)] in file order (newest first)."""
    try:
        with open(CHANGELOG, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    out = []
    for m in SECTION_RE.finditer(text):
        heading = f"## v{m.group(1)}{m.group(2)}".rstrip()
        out.append((parse_version(m.group(1)), heading, m.group(3)))
    return out


def filter_technical(body: str) -> str:
    """Drop blacklisted bold-titled subsections from a section body."""
    lines = []
    skipping = False
    for line in body.splitlines():
        m = BOLD_TITLE_RE.match(line.strip())
        if m:
            skipping = bool(BLACKLIST.search(m.group(1)))
        if not skipping:
            lines.append(line.rstrip())
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def intro_line(body: str) -> str:
    """First plain text line of a section body (the one-liner summary)."""
    for line in body.splitlines():
        s = line.strip()
        if s and not BOLD_TITLE_RE.match(s) and not s.startswith("-"):
            return s
    return ""


def main():
    args = sys.argv[1:]
    title_mode = "--title" in args
    if title_mode:
        args.remove("--title")
    if not args:
        print("usage: release_notes.py [--title] <tag> [prev_tag]", file=sys.stderr)
        return 1
    cur = parse_version(args[0])
    prev = parse_version(args[1]) if len(args) > 1 and args[1] else None

    sections = load_sections()

    if title_mode:
        cur_tag = "v" + ".".join(str(n) for n in cur)
        current = next((s for s in sections if s[0] == cur), None)
        summary = intro_line(current[2]).rstrip(".").strip() if current else ""
        title = f"{cur_tag} - {summary}" if summary else cur_tag
        sys.stdout.buffer.write((title + "\n").encode("utf-8"))
        return 0
    parts = []

    current = next((s for s in sections if s[0] == cur), None)
    if current:
        parts.append(f"{current[1]}\n\n{filter_technical(current[2])}")
    else:
        parts.append(
            f"See [CHANGELOG.md](https://github.com/{REPO}/blob/main/CHANGELOG.md) "
            f"for details.")

    if prev is not None:
        between = [s for s in sections if prev < s[0] < cur]
        for ver, _heading, body in sorted(between, reverse=True):
            tag = "v" + ".".join(str(n) for n in ver)
            summary = intro_line(body)
            parts.append(f"Also includes **{tag}**: {summary}" if summary
                         else f"Also includes **{tag}** (see CHANGELOG).")
        prev_tag = "v" + ".".join(str(n) for n in prev)
        cur_tag = "v" + ".".join(str(n) for n in cur)
        parts.append(f"**Full Changelog**: "
                     f"https://github.com/{REPO}/compare/{prev_tag}...{cur_tag}")

    sys.stdout.buffer.write(("\n\n".join(parts) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
