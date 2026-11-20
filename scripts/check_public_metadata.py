#!/usr/bin/env python3
"""Reject personal contact information and unrelated owner-project URLs in public metadata.

Only reports file, line and rule name; never echoes a possible credential.
The pack archives and git author records are separate from these source checks.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SELF = "osm-offline-packs"
OWNER = "b3nnyray13"

EMAIL = re.compile(r"[A-Za-z0-9._%+\-\[\]]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
GITHUB_LINK = re.compile(r"https?://(?:www\.)?github\.com/" + re.escape(OWNER)
                         + r"/([\w.\-]+)", re.IGNORECASE)
TOKEN_LIKE = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{25,}\b"),
)

def public_files():
    for name in ("README.md", "catalog.json", "regions.json", "data/truck-bans-extra.tsv"):
        p = ROOT / name
        if p.is_file():
            yield p
    for folder in ("scripts", ".github/workflows"):
        directory = ROOT / folder
        if directory.is_dir():
            for p in sorted(directory.rglob("*")):
                if p.is_file() and p.suffix.lower() in {".py", ".sh", ".yml", ".yaml", ".json", ".md", ".txt"}:
                    yield p

def inspect():
    problems = []
    for p in public_files():
        # Text-only public-source gate; release assets and Git history require
        # separate inspection by the owner before publishing.
        for number, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            flags = []
            for match in EMAIL.finditer(line):
                address = match.group(0)
                # GitHub Actions bot is a non-addressable platform identity,
                # not the owner's contact address.
                if not re.fullmatch(r"\d+\+github-actions\[bot\]@users\.noreply\.github\.com",
                                    address, re.IGNORECASE):
                    flags.append("unexpected-email")
            for match in GITHUB_LINK.finditer(line):
                if match.group(1).lower() != SELF:
                    flags.append("link-to-another-owner-repository")
            if any(regex.search(line) for regex in TOKEN_LIKE):
                flags.append("credential-shaped-text")
            for reason in set(flags):
                problems.append(f"{p.relative_to(ROOT)}:{number}: {reason}")
    return problems

def main():
    problems = inspect()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("Public metadata privacy check: PASS (source/catalog only; not release assets or Git history).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
