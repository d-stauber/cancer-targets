"""UniProt paginated download (the stream endpoint times out for large field sets)."""
import gzip, logging, re, time
import requests
from .fetch import PLAIN_UA
from .manifest import record

log = logging.getLogger("ct.uniprot")
FIELDS = "accession,id,gene_primary,gene_names,protein_name,length,cc_subcellular_location,ft_topo_dom,ft_transmem,ft_signal,keyword,xref_ensembl,xref_hgnc,cc_function"
URL = "https://rest.uniprot.org/uniprotkb/search"

def download_uniprot(dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        log.info("exists: %s", dest.name); return
    params = {"query": "(organism_id:9606) AND (reviewed:true)", "format": "tsv", "fields": FIELDS, "size": 500}
    url, n, release = URL, 0, None
    with gzip.open(dest.with_suffix(".part"), "wt") as out:
        first = True
        while url:
            for attempt in range(6):
                try:
                    r = requests.get(url, params=params if first else None, headers=PLAIN_UA, timeout=(30, 300))
                    r.raise_for_status()
                    break
                except Exception as e:
                    log.warning("uniprot page failed (attempt %d): %s", attempt + 1, e)
                    time.sleep(3 * 2 ** attempt)
            else:
                raise IOError("uniprot download failed repeatedly")
            release = release or r.headers.get("X-UniProt-Release")
            lines = r.text.splitlines()
            if first:
                out.write(lines[0] + "\n")
            for l in lines[1:]:
                out.write(l + "\n"); n += 1
            m = re.search(r'<([^>]+)>; rel="next"', r.headers.get("Link", ""))
            url = m.group(1) if m else None
            first = False
            if n % 5000 == 0:
                log.info("uniprot: %d entries", n)
    dest.with_suffix(".part").rename(dest)
    record("uniprot", dest.name, release=release, url=URL, rows=n)
    log.info("uniprot done: %d entries (release %s)", n, release)
