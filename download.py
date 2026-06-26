#!/usr/bin/env python3
"""
GoPro Media Library Downloader
Downloads all media from your GoPro cloud library.

HOW TO GET YOUR COOKIES:
1. Open https://gopro.com/media-library in Chrome and log in
2. Open DevTools (F12) → Network tab
3. Refresh the page, click any request to api.gopro.com
4. In the Headers section, find the "cookie" request header
5. Copy the ENTIRE cookie string value

Then run:
    python download.py --cookies "paste_entire_cookie_string_here"

Or save the cookie string to a file and use:
    python download.py --cookie-file cookies.txt

You can also extract just the gp_access_token value from the cookie string
and pass it with:
    python download.py --token "eyJhbGci..."
"""

import sys
import time
import argparse
import requests
from pathlib import Path
from urllib.parse import urlencode

BASE_URL = "https://api.gopro.com"
MEDIA_FIELDS = (
    "filename,id,height,width,item_count,orientation,play_as,"
    "ready_to_view,resolution,source_duration,token,type,"
    "captured_at,created_at,file_size,camera_model,content_title"
)

DATE = "06-05-2023"
# Flip DD-MM-YYYY → YYYY-MM-DD to match the captured_at field from the API
_DATE_ISO = "-".join(reversed(DATE.split("-")))


def build_session(cookies_str: str | None = None, token: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "accept": "application/vnd.gopro.jk.media+json; version=2.0.0",
        "accept-language": "en-GB,en;q=0.9",
        "origin": "https://gopro.com",
        "referer": "https://gopro.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
    })

    if cookies_str:
        # Parse "key=value; key2=value2; ..." into a dict
        for part in cookies_str.split(";"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                session.cookies.set(k.strip(), v.strip(), domain="api.gopro.com")
    elif token:
        session.cookies.set("gp_access_token", token, domain="api.gopro.com")

    return session


def list_all_media(session: requests.Session) -> list[dict]:
    """Fetch every media item from the library, handling pagination."""
    all_media = []
    page = 1
    per_page = 100

    print("Fetching media list from GoPro cloud...")

    while True:
        params = {
            "fields": MEDIA_FIELDS,
            "order_by": "created_at",
            "per_page": per_page,
            "page": page,
        }
        url = f"{BASE_URL}/media/search?{urlencode(params)}"

        resp = session.get(url, timeout=30)
        if resp.status_code == 401:
            print("ERROR: Session expired or invalid. Please grab fresh cookies from your browser.")
            sys.exit(1)
        resp.raise_for_status()

        data = resp.json()
        media_list = data.get("_embedded", {}).get("media", [])
        all_media.extend(media_list)

        total = data.get("_pages", {}).get("total_items", len(all_media))
        print(f"  Page {page}: got {len(media_list)} items  ({len(all_media)} / {total} total)")

        if len(all_media) >= total or not media_list:
            break

        page += 1
        time.sleep(0.3)

    print(f"\nFound {len(all_media)} media items.\n")
    return all_media


def get_download_url(session: requests.Session, media_id: str) -> str | None:
    """Ask the API for the original-quality download URL for a media item."""
    resp = session.get(f"{BASE_URL}/media/{media_id}/download", timeout=30)
    if resp.status_code != 200:
        return None
    data = resp.json()

    # The response nests the URL under _embedded.variations or directly
    variations = data.get("_embedded", {}).get("variations", [])
    if variations:
        # Prefer the highest-quality / largest variation
        best = max(variations, key=lambda v: v.get("width", 0) or 0)
        return best.get("url") or variations[0].get("url")

    return data.get("url")


def download_file(url: str, dest_path: Path, session: requests.Session) -> bool:
    """Stream-download a file with a simple progress display."""
    try:
        with session.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        mb_done = downloaded / 1024 / 1024
                        mb_total = total / 1024 / 1024
                        print(f"\r    {pct:3d}%  {mb_done:.1f} / {mb_total:.1f} MB", end="", flush=True)
            print()
        return True
    except Exception as e:
        print(f"\n    Download error: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def delete_media(session: requests.Session, media_ids: list[str]):
    """Delete media items from the GoPro cloud library by ID."""
    ids_param = ",".join(media_ids)
    resp = session.delete(f"{BASE_URL}/media?ids={ids_param}", timeout=30)
    if resp.status_code in (200, 204):
        print(f"  Deleted {len(media_ids)} item(s) from GoPro cloud.")
    else:
        print(f"  Delete request returned {resp.status_code} — items may not have been removed.")


def download_all(
    session: requests.Session,
    output_dir: Path,
    dry_run: bool = False,
    delete_after: bool = False,
):
    all_items = list_all_media(session)
    media_items = [m for m in all_items if (m.get("captured_at") or "").startswith(_DATE_ISO)]

    print(f"Filtered to {len(media_items)} item(s) captured on {DATE}.\n")

    if not media_items:
        print("No media found for that date.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    succeeded, skipped, failed = 0, 0, 0
    downloaded_ids = []

    for i, item in enumerate(media_items, 1):
        filename = item.get("filename") or f"media_{item['id']}"
        dest = output_dir / filename

        if dest.exists():
            print(f"[{i}/{len(media_items)}] SKIP  {filename}")
            skipped += 1
            downloaded_ids.append(item["id"])  # already on disk — safe to delete
            continue

        captured = (item.get("captured_at") or "")[:10]
        size_mb = (item.get("file_size") or 0) / 1024 / 1024
        media_type = item.get("type", "")
        print(f"[{i}/{len(media_items)}] {filename}  {media_type}  {captured}  {size_mb:.0f} MB")

        if dry_run:
            print("    [dry-run]")
            continue

        url = get_download_url(session, item["id"])
        if not url:
            print("    Could not get download URL — skipping")
            failed += 1
            continue

        ok = download_file(url, dest, session)
        if ok:
            succeeded += 1
            downloaded_ids.append(item["id"])
        else:
            failed += 1
        time.sleep(0.2)

    print(f"\nDone.  Downloaded: {succeeded}  Skipped (already exist): {skipped}  Failed: {failed}")

    if delete_after and not dry_run:
        if failed > 0:
            print(f"\nSkipping cloud delete — {failed} file(s) failed to download.")
        elif len(downloaded_ids) == len(media_items):
            print(f"\nAll {len(media_items)} file(s) accounted for locally. Deleting from GoPro cloud...")
            delete_media(session, downloaded_ids)
        else:
            print("\nSkipping cloud delete — not all files were accounted for.")


def main():
    parser = argparse.ArgumentParser(
        description="Download all videos from your GoPro cloud library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    auth = parser.add_mutually_exclusive_group(required=True)
    auth.add_argument("--cookies", help="Full cookie string copied from browser DevTools")
    auth.add_argument("--cookie-file", help="Path to a text file containing the cookie string")
    auth.add_argument("--token", help="Just the gp_access_token value from the cookie")

    parser.add_argument(
        "--output", default=f"./gopro_downloads/{DATE}",
        help=f"Directory to save files (default: ./gopro_downloads/{DATE})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List files without downloading them",
    )
    parser.add_argument(
        "--delete-after", action="store_true",
        help="Delete files from GoPro cloud after ALL of them download successfully",
    )
    args = parser.parse_args()

    cookies_str = None
    token = None

    if args.cookies:
        cookies_str = args.cookies
    elif args.cookie_file:
        cookies_str = Path(args.cookie_file).read_text(encoding="utf-8").strip()
    elif args.token:
        token = args.token

    session = build_session(cookies_str=cookies_str, token=token)

    download_all(
        session=session,
        output_dir=Path(args.output),
        dry_run=args.dry_run,
        delete_after=args.delete_after,
    )


if __name__ == "__main__":
    main()
