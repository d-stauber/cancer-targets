from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from ..paths import WEB_DIST
from .routers import meta, genes, contexts, explorer, controls

app = FastAPI(title="Cancer Targets API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health():
    from .db import q, DB
    n = int(q("select count(*) as n from contexts").n[0])
    return {"status": "ok", "contexts": n, "db": str(DB)}
for r in (meta, genes, contexts, explorer, controls):
    app.include_router(r.router, prefix="/api")

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        root = WEB_DIST.resolve()
        f = (root / path).resolve()
        if f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache, must-revalidate"})
