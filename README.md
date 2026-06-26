# GoPro Media Library Downloader

Downloads videos and photos from your GoPro cloud library by date, with optional
cloud deletion once everything is safely on disk.

## Setup

```powershell
pip install requests
```

## Getting your session cookies

1. Open [gopro.com/media-library](https://gopro.com/media-library) and log in
2. Press **F12** to open DevTools → go to the **Network** tab
3. Refresh the page and click any request going to `api.gopro.com`
4. In the **Headers** panel, find the `cookie:` request header
5. Copy the entire value and paste it into `cookie.txt`

> Cookies expire after a few hours. If you get a 401 error mid-run, grab fresh
> cookies and re-run — already-downloaded files will be skipped automatically.

## Examples

### Preview a single date (no files saved)

```powershell
python download.py --cookie-file cookie.txt --date 30-04-2023 --dry-run
```

### Download a single date

```powershell
python download.py --cookie-file cookie.txt --date 30-04-2023
```

Files are saved to `./gopro_downloads/30-04-2023/`.

### Download a date range

```powershell
python download.py --cookie-file cookie.txt --from 01-04-2023 --to 30-04-2023
```

Files are saved to `./gopro_downloads/01-04-2023_to_30-04-2023/`.

### Download and delete from GoPro cloud if everything succeeds

```powershell
python download.py --cookie-file cookie.txt --date 30-04-2023 --delete-after
```

The cloud delete only runs if **every** file downloaded without error.
If anything fails, nothing is deleted.

### Save to a custom folder (e.g. an external drive)

```powershell
python download.py --cookie-file cookie.txt --date 30-04-2023 --output "D:\GoPro Backup\30-04-2023"
```

### Pass cookies inline instead of a file

```powershell
python download.py --cookies "datadome=abc123; gp_access_token=eyJhbGci..." --date 30-04-2023
```

## Typical workflow for clearing your subscription

1. Dry-run a date to confirm the right files are listed
2. Run with `--delete-after` to download and remove from the cloud
3. Repeat for the next date (or use a range to do a whole month at once)

```powershell
# Check
python download.py --cookie-file cookie.txt --from 01-04-2023 --to 30-04-2023 --dry-run

# Download and clear
python download.py --cookie-file cookie.txt --from 01-04-2023 --to 30-04-2023 --delete-after
```

## All flags

| Flag | Description |
|------|-------------|
| `--cookie-file <path>` | Path to a file containing the cookie string (recommended) |
| `--cookies <string>` | Cookie string pasted directly on the command line |
| `--token <value>` | Just the `gp_access_token` value if you extracted it manually |
| `--date DD-MM-YYYY` | Download media from a single date |
| `--from DD-MM-YYYY` | Start of date range (inclusive, use with `--to`) |
| `--to DD-MM-YYYY` | End of date range (inclusive, use with `--from`) |
| `--output <path>` | Folder to save files into (default: `./gopro_downloads/<date>`) |
| `--dry-run` | List matching files without downloading or deleting anything |
| `--delete-after` | Delete from GoPro cloud once all files are confirmed on disk |
