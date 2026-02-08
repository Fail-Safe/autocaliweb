#!/usr/bin/env python3
"""Purge on-disk KEPUB files from a Calibre library tree.

Why this exists
---------------
Older Autocaliweb/Calibre-Web KEPUB generation bugs could leave behind `.kepub` files
with incorrect content. If Kobo now always downloads a freshly generated KEPUB from
EPUB, those stale `.kepub` files are no longer needed and can be removed.

Safety defaults
---------------
- Dry-run by default (no deletions).
- Only deletes a `.kepub`/`.kepub.epub` when a corresponding `.epub` exists in the
  same directory (so we don't delete the only available format).

Examples
--------
Dry-run:
  python scripts/purge_kepubs.py --root /calibre-library

Apply deletions:
  python scripts/purge_kepubs.py --root /calibre-library --apply

Include `.kepub.epub` files too (enabled by default):
  python scripts/purge_kepubs.py --root /calibre-library --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Iterable, Iterator


@dataclass(frozen=True)
class Candidate:
    kepub_path: str
    epub_path: str
    size_bytes: int


def _iter_kepub_candidates(root: str, include_kepub_epub: bool) -> Iterator[tuple[str, int]]:
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            lower = name.lower()
            if lower.endswith('.kepub'):
                path = os.path.join(dirpath, name)
            elif include_kepub_epub and lower.endswith('.kepub.epub'):
                path = os.path.join(dirpath, name)
            else:
                continue

            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0

            yield path, size


def _expected_epub_path(kepub_path: str) -> str:
    lower = kepub_path.lower()
    if lower.endswith('.kepub.epub'):
        base = kepub_path[: -len('.kepub.epub')]
    elif lower.endswith('.kepub'):
        base = kepub_path[: -len('.kepub')]
    else:
        base = os.path.splitext(kepub_path)[0]

    return base + '.epub'


def find_deletions(root: str, include_kepub_epub: bool) -> list[Candidate]:
    deletions: list[Candidate] = []
    for kepub_path, size in _iter_kepub_candidates(root, include_kepub_epub):
        epub_path = _expected_epub_path(kepub_path)
        if os.path.isfile(epub_path):
            deletions.append(Candidate(kepub_path=kepub_path, epub_path=epub_path, size_bytes=size))
    return deletions


def _fmt_bytes(n: int) -> str:
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    value = float(n)
    for u in units:
        if value < 1024.0 or u == units[-1]:
            if u == 'B':
                return f'{int(value)} {u}'
            return f'{value:.2f} {u}'
        value /= 1024.0
    return f'{n} B'


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description='Purge stale .kepub files from a Calibre library tree.')
    parser.add_argument('--root', required=True, help='Calibre library root (e.g. /calibre-library)')
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Actually delete files. Without this flag, runs in dry-run mode.',
    )
    parser.add_argument(
        '--no-kepub-epub',
        action='store_true',
        help='Do not include .kepub.epub files (only .kepub).',
    )

    args = parser.parse_args(list(argv))

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f'ERROR: root is not a directory: {root}', file=sys.stderr)
        return 2

    include_kepub_epub = not args.no_kepub_epub

    deletions = find_deletions(root, include_kepub_epub)
    total_bytes = sum(c.size_bytes for c in deletions)

    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'{mode}: found {len(deletions)} deletable KEPUB file(s) under {root} ({_fmt_bytes(total_bytes)})')

    # Print paths for transparency.
    for c in deletions:
        print(f'- {c.kepub_path}  (kept EPUB: {os.path.basename(c.epub_path)})')

    if not args.apply:
        print('Dry-run complete. Re-run with --apply to delete these files.')
        return 0

    deleted = 0
    failed = 0
    for c in deletions:
        try:
            os.remove(c.kepub_path)
            deleted += 1
        except OSError as e:
            failed += 1
            print(f'ERROR: failed to delete {c.kepub_path}: {e}', file=sys.stderr)

    print(f'APPLY complete: deleted={deleted} failed={failed}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
