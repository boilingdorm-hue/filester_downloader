"""
filester.me - Retry Failed Downloads Only
Usage: python filester_retry.py
"""

import re
import time
import requests
from pathlib import Path

DOWNLOAD_DIR = "filester_downloads"
URLS_FILE    = "urls.txt"
FAILED_FILE  = "failed.txt"   # Failed slugs will be saved here
DELAY        = 2.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://filester.me/",
    "Origin":  "https://filester.me",
}


def load_urls(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def get_token(slug: str, session: requests.Session) -> dict | None:
    try:
        r = session.post(
            "https://filester.me/v2/api/public/download",
            json={"file_slug": slug},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("success"):
            return data
        print(f"  [!] API error: {data}")
    except Exception as e:
        print(f"  [!] Failed to get token: {e}")
    return None


def download(info: dict, dest: Path, session: requests.Session) -> bool:
    server = info["server"].rstrip("/")
    file   = info["file"]
    token  = info["token"]
    name   = info.get("name", file)

    url  = f"{server}/v2/{file}?token={token}"
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    dest.mkdir(parents=True, exist_ok=True)
    fp   = dest / safe

    if fp.exists():
        print(f"  [✓] Already exists: {safe}")
        return True

    print(f"  [↓] Downloading: {safe}")
    try:
        with session.get(url, headers=HEADERS, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0))
            done  = 0
            with open(fp, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(
                            f"\r       {done/total*100:.0f}%  {done//1024}/{total//1024} KB",
                            end="",
                            flush=True,
                        )
            print(f"\r  [✓] Completed: {done//1024} KB → {safe}      ")
        return True
    except requests.RequestException as e:
        print(f"\n  [!] Error: {e}")
        if fp.exists():
            fp.unlink()
        return False


def find_failed(urls: list[str], dest: Path) -> list[str]:
    """
    Scan all URLs in urls.txt.

    Files that cannot retrieve a token (therefore their filename cannot be
    determined) or whose downloaded file is missing are considered failed.

    Simpler approach:
    If failed.txt exists, read it.
    Otherwise, ask the user.
    """
    failed_path = Path(FAILED_FILE)
    if failed_path.exists():
        slugs = [
            l.strip()
            for l in failed_path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")
        ]
        print(f"  Read {len(slugs)} slug(s) from {FAILED_FILE}.")
        return [f"https://filester.me/d/{s}" for s in slugs]

    # If failed.txt doesn't exist:
    # Try every URL, retrieve the filename, then check if it exists.
    print("failed.txt not found. Checking all URLs...")
    session = requests.Session()
    missing = []

    for i, page_url in enumerate(urls, 1):
        slug = page_url.rstrip("/").split("/")[-1]
        print(f"  [{i}/{len(urls)}] Checking {slug}...", end="\r")

        info = get_token(slug, session)
        if not info:
            missing.append(page_url)
            continue

        safe = re.sub(r'[<>:"/\\|?*]', "_", info.get("name", info["file"]))
        if not (dest / safe).exists():
            missing.append(page_url)

        time.sleep(0.3)

    print(f"\nFound {len(missing)} missing file(s).")
    return missing


def main():
    dest = Path(DOWNLOAD_DIR)
    urls = load_urls(URLS_FILE)

    print("=" * 50)
    print("filester.me — Missing / Failed File Downloader")
    print("=" * 50)

    # Check failed.txt first (it can also be edited manually)
    failed_path = Path(FAILED_FILE)
    if failed_path.exists():
        retry_urls = load_urls(FAILED_FILE)

        # failed.txt may contain full URLs or just slugs
        retry_urls = [
            u if u.startswith("http") else f"https://filester.me/d/{u}"
            for u in retry_urls
        ]

        print(f"Loaded {len(retry_urls)} URL(s) from failed.txt.")

    else:
        print("failed.txt not found.")
        print("Which mode would you like to use?")
        print("  1) Enter slug(s) manually (e.g. fAzQm0Z)")
        print("  2) Scan urls.txt and find missing files (slower)")

        choice = input("Choice (1/2): ").strip()

        if choice == "1":
            slugs = []
            print("Enter slugs (leave blank to finish):")

            while True:
                s = input("  Slug: ").strip()
                if not s:
                    break
                slugs.append(s)

            retry_urls = [f"https://filester.me/d/{s}" for s in slugs]

        else:
            retry_urls = find_failed(urls, dest)

    if not retry_urls:
        print("No files to retry.")
        return

    print(f"\nRetrying {len(retry_urls)} file(s).\n")

    session = requests.Session()
    ok = fail = 0
    still_failed = []

    for i, page_url in enumerate(retry_urls, 1):
        slug = page_url.rstrip("/").split("/")[-1]
        print(f"[{i}/{len(retry_urls)}] {slug}")

        info = get_token(slug, session)
        if not info:
            fail += 1
            still_failed.append(slug)
            continue

        if download(info, dest, session):
            ok += 1
        else:
            fail += 1
            still_failed.append(slug)

        if i < len(retry_urls):
            time.sleep(DELAY)

    print("\n── Summary ─────────────────")
    print(f"Successful: {ok}")
    print(f"Failed:     {fail}")

    if still_failed:
        Path(FAILED_FILE).write_text("\n".join(still_failed), encoding="utf-8")
        print(f"Remaining failed downloads have been saved to {FAILED_FILE}.")
        print("Run the script again to retry them.")


if __name__ == "__main__":
    main()