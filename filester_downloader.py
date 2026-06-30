"""
filester.me Bulk Downloader - v4
Usage:
  1. Put one Filester link per line into urls.txt
  2. python filester_downloader.py
"""

import re
import time
import requests
from pathlib import Path

# ── Settings ─────────────────────────────────────────────────────────────────
URLS_FILE    = "urls.txt"
DOWNLOAD_DIR = "filester_downloads"
DELAY        = 2.0
# ─────────────────────────────────────────────────────────────────────────────

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
        print(f"[!] {path} not found. Please create it.")
        return []
    urls = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def get_token(slug: str, session: requests.Session) -> dict | None:
    try:
        r = session.post(
            "https://filester.me/v2/api/public/download",
            json={"file_slug": slug},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
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

    url = f"{server}/v2/{file}?token={token}"

    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    dest.mkdir(parents=True, exist_ok=True)
    fp = dest / safe

    if fp.exists():
        print(f"  [✓] Already exists, skipped: {safe}")
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


def main():
    urls = load_urls(URLS_FILE)
    if not urls:
        return

    dest = Path(DOWNLOAD_DIR)
    print(f"Total files: {len(urls)}  →  {dest.resolve()}\n")

    session = requests.Session()
    ok = fail = 0

    for i, page_url in enumerate(urls, 1):
        slug = page_url.rstrip("/").split("/")[-1]
        print(f"[{i}/{len(urls)}] {slug}")

        info = get_token(slug, session)
        if not info:
            fail += 1
            continue

        if download(info, dest, session):
            ok += 1
        else:
            fail += 1

        if i < len(urls):
            time.sleep(DELAY)

    print("\n── Summary ─────────────────")
    print(f"Successful: {ok}")
    print(f"Failed:     {fail}")


if __name__ == "__main__":
    main()