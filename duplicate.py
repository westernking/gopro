#!/usr/bin/env python3
"""
Duplicate media finder

Scans one or more directory trees for duplicate files using a three-pass strategy:
  1. Group by file size       (stat only — no file reads)
  2. Hash first 64 KB         (eliminates most false candidates cheaply)
  3. Full MD5 hash            (only for files still tied after pass 2)

Usage:
    python3 duplicate.py "/Volumes/SanDisk Extreme 3TB/Media Library/Videos" \\
                         "/Volumes/SanDisk Extreme 3TB/Media Library/Video Projects"

    python3 duplicate.py <DIR> [DIR ...] --output report.txt
    python3 duplicate.py <DIR> [DIR ...] --all-files
"""

import sys
import hashlib
import argparse
from pathlib import Path
from collections import defaultdict

PARTIAL_BYTES = 64 * 1024  # 64 KB for the fast first-pass hash

MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".mts", ".m2ts", ".mpg", ".mpeg",
    ".wmv", ".m4v", ".3gp", ".hevc", ".heic", ".jpg", ".jpeg", ".png",
    ".gif", ".raw", ".dng", ".cr2", ".nef", ".arw",
}


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def partial_hash(path: Path) -> str | None:
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read(PARTIAL_BYTES)).hexdigest()
    except OSError:
        return None


def full_hash(path: Path) -> str | None:
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def collect_files(roots: list[Path], extensions: set[str] | None) -> list[Path]:
    files = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size == 0:
                continue
            if extensions and path.suffix.lower() not in extensions:
                continue
            files.append(path)
            if len(files) % 500 == 0:
                print(f"\r  {len(files)} files found...", end="", flush=True)
    print(f"\r  {len(files)} files found.      ")
    return files


def find_duplicates(roots: list[Path], extensions: set[str] | None) -> list[list[Path]]:
    print("Pass 1: collecting files...")
    all_files = collect_files(roots, extensions)

    # Pass 1 — group by size
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in all_files:
        try:
            by_size[path.stat().st_size].append(path)
        except OSError:
            pass

    size_groups = {sz: paths for sz, paths in by_size.items() if len(paths) > 1}
    size_candidate_count = sum(len(v) for v in size_groups.values())
    print(f"Pass 2: {size_candidate_count} files share a size — hashing first {PARTIAL_BYTES // 1024} KB...")

    # Pass 2 — partial hash
    by_partial: dict[tuple[int, str], list[Path]] = defaultdict(list)
    done = 0
    for size, paths in size_groups.items():
        for path in paths:
            h = partial_hash(path)
            if h is not None:
                by_partial[(size, h)].append(path)
            done += 1
            if done % 100 == 0:
                print(f"\r  {done}/{size_candidate_count}", end="", flush=True)
    print(f"\r  {done}/{size_candidate_count}      ")

    partial_groups = {k: v for k, v in by_partial.items() if len(v) > 1}
    partial_candidate_count = sum(len(v) for v in partial_groups.values())
    print(f"Pass 3: {partial_candidate_count} files remain — computing full hashes...")

    # Pass 3 — full hash
    by_full: dict[tuple[int, str], list[Path]] = defaultdict(list)
    done = 0
    for (size, _), paths in partial_groups.items():
        for path in paths:
            h = full_hash(path)
            if h is not None:
                by_full[(size, h)].append(path)
            done += 1
            if done % 10 == 0:
                print(f"\r  {done}/{partial_candidate_count}", end="", flush=True)
    print(f"\r  {done}/{partial_candidate_count}      ")

    return [paths for paths in by_full.values() if len(paths) > 1]


def decide_deletions(group: list[Path], primary: Path) -> list[Path]:
    """Return the paths to delete from a duplicate group.

    If any copy lives under the primary directory, delete all copies outside it.
    If no copy is in primary, keep the first path alphabetically and delete the rest.
    """
    in_primary = [p for p in group if p.is_relative_to(primary)]
    outside = [p for p in group if not p.is_relative_to(primary)]

    if in_primary:
        return outside
    else:
        return sorted(group)[1:]


def purge_duplicates(groups: list[list[Path]], primary: Path, dry_run: bool) -> None:
    to_delete = [path for group in groups for path in decide_deletions(group, primary)]

    if not to_delete:
        print("\nNothing to delete.")
        return

    total_size = sum(p.stat().st_size for p in to_delete)
    tag = "[dry-run] " if dry_run else ""
    print(f"\n{tag}Files to delete: {len(to_delete)}   Space to free: {fmt_size(total_size)}\n")

    deleted_bytes = 0
    errors = 0
    for path in to_delete:
        size = path.stat().st_size
        if dry_run:
            print(f"  [dry-run] {path}  ({fmt_size(size)})")
        else:
            try:
                path.unlink()
                print(f"  Deleted  {path}  ({fmt_size(size)})")
                deleted_bytes += size
            except OSError as e:
                print(f"  ERROR    {path}: {e}")
                errors += 1

    if not dry_run:
        print(f"\nDone.  Freed: {fmt_size(deleted_bytes)}")
        if errors:
            print(f"  {errors} error(s) encountered — see above.")


def build_report(groups: list[list[Path]]) -> tuple[str, int]:
    total_savings = 0
    lines: list[str] = []

    sorted_groups = sorted(groups, key=lambda g: g[0].stat().st_size, reverse=True)

    for group in sorted_groups:
        size = group[0].stat().st_size
        savings = size * (len(group) - 1)
        total_savings += savings
        lines.append(f"\n{'─' * 72}")
        lines.append(
            f"  {fmt_size(size)} each   {len(group)} copies   "
            f"{fmt_size(savings)} wasted"
        )
        for path in group:
            lines.append(f"    {path}")

    lines.append(f"\n{'═' * 72}")
    lines.append(f"  {len(groups)} duplicate group(s) found.")
    lines.append(f"  Potential space saving: {fmt_size(total_savings)}")

    return "\n".join(lines), total_savings


def main():
    parser = argparse.ArgumentParser(
        description="Find duplicate media files and report potential disk savings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "dirs", nargs="+", metavar="DIR",
        help="One or more directories to scan",
    )
    parser.add_argument(
        "--all-files", action="store_true",
        help="Scan all file types, not just media files",
    )
    parser.add_argument(
        "--output", metavar="FILE",
        help="Write the full report to a text file (summary still printed to terminal)",
    )
    parser.add_argument(
        "--primary", metavar="DIR",
        help="Primary directory whose copies are always kept (default: first DIR argument)",
    )
    parser.add_argument(
        "--purge", action="store_true",
        help="Delete duplicate files outside the primary directory",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="With --purge: show what would be deleted without removing anything",
    )
    args = parser.parse_args()

    if args.dry_run and not args.purge:
        parser.error("--dry-run requires --purge")

    roots = []
    for d in args.dirs:
        p = Path(d)
        if not p.is_dir():
            print(f"ERROR: '{d}' is not a directory.", file=sys.stderr)
            sys.exit(1)
        roots.append(p)

    primary = Path(args.primary) if args.primary else roots[0]
    if not primary.is_dir():
        print(f"ERROR: primary directory '{primary}' does not exist.", file=sys.stderr)
        sys.exit(1)

    extensions = None if args.all_files else MEDIA_EXTENSIONS

    print()
    groups = find_duplicates(roots, extensions)
    report, total_savings = build_report(groups)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nFull report written to: {args.output}")
        print(f"{len(groups)} duplicate group(s)  —  potential saving: {fmt_size(total_savings)}")
    else:
        print(report)

    if args.purge:
        purge_duplicates(groups, primary, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
