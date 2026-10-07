import logging
from pathlib import Path
from typing import Optional, List
import typer

app = typer.Typer(help="Cancer target discovery pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

@app.command()
def download(source: Optional[List[str]] = typer.Option(None, "--source", "-s", help="Only these sources"),
             from_dir: Optional[str] = typer.Option(None, "--from", help="Local dir with pre-downloaded files")):
    """Fetch all raw data sources into data/raw/."""
    from .download.run import run
    run(source or None, from_dir)

@app.command()
def build(step: Optional[List[str]] = typer.Option(None, "--step", help="Only run these build steps")):
    """Harmonize raw data into Parquet + DuckDB."""
    from .harmonize.run import run
    run(step or None)

@app.command()
def score():
    """Compute components, composite scores and ranks."""
    from .scoring.rank import run
    run()

@app.command()
def benchmark():
    """Check known targets rank highly in their contexts."""
    from .scoring.benchmark import run
    run()

@app.command()
def db():
    """(Re)create data/ct.duckdb views over data/processed/*.parquet. Run after extracting a data bundle."""
    from .harmonize.db import build_db
    build_db()

@app.command()
def bundle(out: str = "data/bundles", raw: bool = True):
    """Package data/processed (and optionally data/raw) into tarballs for sharing (e.g. via Dropbox)."""
    import datetime as dt, subprocess
    from .paths import DATA
    tag = dt.date.today().isoformat()
    outdir = Path(out); outdir.mkdir(parents=True, exist_ok=True)
    jobs = [("processed", ["processed"])] + ([("raw", ["raw"])] if raw else [])
    for name, dirs in jobs:
        target = outdir / f"cancer-targets-{name}-{tag}.tar"
        print(f"writing {target} ...")
        subprocess.run(["tar", "-cf", str(target), "-C", str(DATA)] + dirs, check=True)
        print(f"  {target.stat().st_size / 1e9:.2f} GB")
    print("Done. Recipients extract into data/ and run `ct db`.")

@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Run the API (serves web/dist if built). Use --host 0.0.0.0 to accept connections from other machines."""
    import uvicorn
    uvicorn.run("cancer_targets.api.main:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    app()
