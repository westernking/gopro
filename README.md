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

## Setting the date

Edit the `DATE` variable near the top of `download.py`:

```python
DATE = "30-04-2023"   # DD-MM-YYYY
```

All commands below will filter to that date and save files into
`./gopro_downloads/<DATE>/`.

## Examples

### Preview what would be downloaded (no files saved)

```powershell
python download.py --cookie-file cookie.txt --dry-run
```

### Download files for the configured date

```powershell
python download.py --cookie-file cookie.txt
```

### Download and delete from GoPro cloud if everything succeeds

```powershell
python download.py --cookie-file cookie.txt --delete-after
```

The cloud delete only runs if **every** file downloaded without error.
If anything fails, nothing is deleted.

### Save to a custom folder (e.g. an external drive)

```powershell
python download.py --cookie-file cookie.txt --output "D:\GoPro Backup\30-04-2023"
```

### Pass cookies inline instead of a file

```powershell
python download.py --cookies "datadome=abc123; gp_access_token=eyJhbGci..." --dry-run
```

## Typical workflow for clearing your subscription

1. Set `DATE` to the date you want to clear
2. Dry-run to confirm the right files are listed
3. Run with `--delete-after` to download and remove from the cloud
4. Repeat for the next date

## All flags

| Flag | Description |
|------|-------------|
| `--cookie-file <path>` | Path to a file containing the cookie string (recommended) |
| `--cookies <string>` | Cookie string pasted directly on the command line |
| `--token <value>` | Just the `gp_access_token` value if you extracted it manually |
| `--output <path>` | Folder to save files into (default: `./gopro_downloads/<DATE>`) |
| `--dry-run` | List matching files without downloading or deleting anything |
| `--delete-after` | Delete from GoPro cloud once all files are confirmed on disk |
