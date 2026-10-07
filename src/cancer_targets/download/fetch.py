"""Resumable, checksummed HTTP downloads."""
import hashlib, logging, os, time
from pathlib import Path
import requests

log = logging.getLogger("ct.fetch")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}

def sha256(path: Path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()

PLAIN_UA = {"User-Agent": "cancer-targets/0.1 (python-requests)"}

def download(url: str, dest: Path, expected_sha256: str | None = None, retries: int = 4,
             timeout: int = 120, headers: dict | None = None) -> dict:
    """Stream url -> dest with Range resume and atomic rename. Returns manifest info."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        log.info("exists, skipping: %s", dest.name)
        return {"url": url, "bytes": dest.stat().st_size, "skipped": True}
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            have = part.stat().st_size if part.exists() else 0
            headers = dict(headers or UA)
            if have:
                headers["Range"] = f"bytes={have}-"
            with requests.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True) as r:
                if have and r.status_code == 200:
                    have = 0  # server ignored Range; restart
                    part.unlink(missing_ok=True)
                elif have and r.status_code != 206:
                    r.raise_for_status()
                r.raise_for_status()
                mode = "ab" if have else "wb"
                total = r.headers.get("Content-Length")
                log.info("GET %s (%s bytes%s)", url, total or "?", ", resuming" if have else "")
                with open(part, mode) as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            f.write(chunk)
            if part.stat().st_size == 0:
                raise IOError(f"empty response for {url} (status {r.status_code})")
            digest = sha256(part)
            if expected_sha256 and digest != expected_sha256:
                part.unlink()
                raise IOError(f"checksum mismatch for {dest.name}")
            os.replace(part, dest)
            log.info("done: %s (%d bytes)", dest.name, dest.stat().st_size)
            return {"url": url, "bytes": dest.stat().st_size, "sha256": digest}
        except Exception as e:  # noqa
            log.warning("attempt %d failed for %s: %s", attempt + 1, url, e)
            time.sleep(2 ** attempt)
    raise IOError(f"failed to download {url}")

def list_links(url: str, pattern: str) -> list[str]:
    """Return hrefs on an HTML index page matching a regex."""
    import re
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return sorted(set(re.findall(r'href="([^"]*' + pattern + r')"', r.text)) |
                  set(m for m in re.findall(r'href="([^"]+)"', r.text) if re.search(pattern, m)))
