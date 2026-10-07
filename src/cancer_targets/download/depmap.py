"""DepMap release discovery: figshare API -> portal files API -> manual instructions."""
import io, logging, re
import requests, pandas as pd
from .fetch import UA, PLAIN_UA, download
from .manifest import record

log = logging.getLogger("ct.depmap")
FIGSHARE = "https://api.figshare.com/v2"

_AUTHOR_CACHE: list[dict] | None = None

def _figshare_search(title: str) -> list[dict]:
    """Search DepMap's figshare account (author 'Broad DepMap'); fall back to title search."""
    global _AUTHOR_CACHE
    if _AUTHOR_CACHE is None:
        r = requests.post(f"{FIGSHARE}/articles/search", headers=UA, timeout=60,
                          json={"search_for": ':author: "Broad DepMap"', "page_size": 100,
                                "order": "published_date", "order_direction": "desc"})
        r.raise_for_status()
        _AUTHOR_CACHE = r.json()
    hits = [a for a in _AUTHOR_CACHE if title.lower() == a["title"].lower()]
    if hits:
        return hits
    r = requests.post(f"{FIGSHARE}/articles/search", json={"search_for": f':title: "{title}"', "page_size": 10},
                      headers=UA, timeout=60)
    r.raise_for_status()
    return [a for a in r.json() if title.lower() in a["title"].lower()]

def find_figshare_release(cfg: dict) -> tuple[str, list[dict]] | None:
    for q in cfg["quarters"]:
        for pat in cfg["release_title_patterns"]:
            title = pat.format(q=q)
            try:
                arts = _figshare_search(title)
            except Exception as e:
                log.warning("figshare search failed for %s: %s", title, e)
                continue
            if arts:
                art = sorted(arts, key=lambda a: a["published_date"])[-1]
                files = requests.get(f"{FIGSHARE}/articles/{art['id']}/files?page_size=1000", headers=UA, timeout=60).json()
                log.info("figshare release: %s (article %s, %d files)", art["title"], art["id"], len(files))
                return art["title"], files
    return None

def portal_file_table(cfg: dict) -> pd.DataFrame | None:
    try:
        r = requests.get(cfg["portal_files_api"], headers=UA, timeout=120)
        r.raise_for_status()
        if "text/html" in r.headers.get("Content-Type", "") or r.text.lstrip().startswith("<"):
            log.warning("portal API returned HTML (bot check)")
            return None
        return pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        log.warning("portal API failed: %s", e)
        return None

MANUAL = """
DepMap automated download failed (portal bot check / figshare discovery).
Please download these files manually from https://depmap.org/portal/data_page/?tab=allData
(choose the latest 'DepMap Public' release) and place them in {dest}:
{files}
Then re-run: ct download --source depmap
"""

def download_depmap(cfg: dict, dest) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    wanted = [f for f in cfg["files"] if not (dest / f["name"]).exists()]
    if not wanted:
        log.info("all DepMap files present")
        return
    fs = find_figshare_release(cfg)
    if fs:
        title, files = fs
        for w in wanted:
            rx = re.compile(w["regex"])
            hits = [f for f in files if rx.match(f["name"])]
            if not hits:
                log.warning("no figshare file matches %s", w["name"]); continue
            f = hits[0]
            info = download(f["download_url"], dest / w["name"], headers=PLAIN_UA)
            record("depmap", w["name"], release=title, figshare_md5=f.get("computed_md5"), **info)
        wanted = [f for f in cfg["files"] if not (dest / f["name"]).exists()]
    if wanted:
        tab = portal_file_table(cfg)
        if tab is not None:
            rel_col = next((c for c in tab.columns if "release" in c.lower()), None)
            name_col = next((c for c in tab.columns if c.lower() in ("filename", "file_name", "name")), None)
            url_col = next((c for c in tab.columns if "url" in c.lower()), None)
            if rel_col and name_col and url_col:
                pub = tab[tab[rel_col].astype(str).str.contains("Public", na=False)]
                latest = sorted(pub[rel_col].unique())[-1]
                sub = pub[pub[rel_col] == latest]
                for w in wanted:
                    hits = sub[sub[name_col].astype(str).str.match(w["regex"])]
                    if len(hits):
                        info = download(hits.iloc[0][url_col], dest / w["name"])
                        record("depmap", w["name"], release=latest, **info)
        wanted = [f for f in cfg["files"] if not (dest / f["name"]).exists()]
    if wanted:
        msg = MANUAL.format(dest=dest, files="\n".join("  - " + f["name"] for f in wanted))
        log.error(msg)
        raise SystemExit(msg)
