"""`ct download` implementation."""
import logging, re, shutil
from pathlib import Path
import yaml, requests
from ..paths import CONFIG, RAW
from .fetch import download, list_links, UA
from .manifest import record
from .depmap import download_depmap

log = logging.getLogger("ct.download")

def load_sources() -> dict:
    return yaml.safe_load((CONFIG / "sources.yaml").read_text())

def _simple(source: str, cfg: dict):
    dest = RAW / cfg["dir"]
    for f in cfg["files"]:
        url = f.get("url")
        if not url and f.get("scrape_regex"):
            page = requests.get(cfg["download_page"], headers=UA, timeout=60).text
            m = re.search(r'href="([^"]*' + f["scrape_regex"] + r')"', page) or re.search(r'(https?://[^"\s]*' + f["scrape_regex"] + ')', page)
            if not m:
                log.warning("could not resolve %s from %s", f["name"], cfg["download_page"]); continue
            url = m.group(1)
            if url.startswith("/"):
                url = "https://www.proteinatlas.org" + url
        try:
            info = download(url, dest / f["name"])
            record(source, f["name"], release=cfg.get("release"), **info)
        except Exception as e:
            if f.get("optional"):
                log.warning("optional file %s failed: %s", f["name"], e)
            else:
                raise

def _opentargets(cfg: dict):
    dest = RAW / cfg["dir"]
    for ds in cfg["datasets"]:
        url = f"{cfg['base']}/{ds}/"
        links = list_links(url, r"[^\"/]*\.parquet")
        if not links:
            raise IOError(f"no parquet parts found at {url}")
        d = dest / ds
        for l in links:
            name = l.split("/")[-1]
            info = download(l if l.startswith("http") else url + name, d / name)
        record("opentargets", ds, release="latest", n_parts=len(links), url=url)

def _surfaceome(cfg: dict, from_dir: Path | None):
    dest = RAW / cfg["dir"]; dest.mkdir(parents=True, exist_ok=True)
    src = from_dir or Path.home() / "Downloads"
    for name in cfg["local_files"]:
        s = src / name
        if s.exists() and not (dest / name).exists():
            shutil.copy2(s, dest / name)
            record("surfaceome", name, url=str(s), bytes=s.stat().st_size)
        elif not s.exists():
            log.warning("local surfaceome file missing: %s", s)

def run(sources: list[str] | None = None, from_dir: str | None = None):
    cfg = load_sources()
    for source, c in cfg.items():
        if sources and source not in sources:
            continue
        log.info("=== %s ===", source)
        if source == "depmap":
            if from_dir:
                d = RAW / c["dir"]; d.mkdir(parents=True, exist_ok=True)
                for f in c["files"]:
                    s = Path(from_dir) / f["name"]
                    if s.exists() and not (d / f["name"]).exists():
                        shutil.copy2(s, d / f["name"]); record("depmap", f["name"], url=str(s), bytes=s.stat().st_size)
            download_depmap(c, RAW / c["dir"])
        elif source == "opentargets":
            _opentargets(c)
        elif source == "uniprot":
            from .uniprot import download_uniprot
            download_uniprot(RAW / c["dir"] / c["files"][0]["name"])
        elif source == "surfaceome":
            _surfaceome(c, Path(from_dir) if from_dir else None)
        else:
            _simple(source, c)
