import logging
import time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import config
from terabox_resolver import is_terabox_link, resolve_terabox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("terabox_api")

app = FastAPI(
    title="Ak TeraBox Resolver API",
    description="Standalone TeraBox share-link resolver API.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)

_hits = defaultdict(deque)

def _rate_limit(ip: str):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(429, "Rate limit exceeded, try again later.")
    q.append(now)

@app.middleware("http")
async def limiter(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    try:
        _rate_limit(ip)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"status": False, "error": e.detail})
    return await call_next(request)

@app.get("/", include_in_schema=False)
def root():
    return {
        "status": True,
        "creator": "Ak",
        "message": "TeraBox Resolver API is online",
        "version": "1.0.0",
        "endpoints": {
            "resolve": "/api/terabox?url=<TERABOX_SHARE_URL>",
            "legacy": "/api?url=<TERABOX_SHARE_URL>",
            "health": "/health",
            "docs": "/docs",
        },
    }

@app.get("/health")
def health():
    return {"status": True, "service": "terabox-api", "provider": "TeraBox"}

async def _resolve(url: str):
    if not is_terabox_link(url):
        return JSONResponse(status_code=400, content={
            "status": False,
            "error": "Only TeraBox share links are supported here."
        })
    try:
        data = await run_in_threadpool(resolve_terabox, url)
        if isinstance(data, dict) and data.get("error"):
            return JSONResponse(status_code=502, content={"status": False, **data})
        return {"status": True, "creator": "Ak", "data": data}
    except Exception as e:
        logger.exception("TeraBox resolve failed")
        return JSONResponse(status_code=502, content={"status": False, "error": str(e)})

@app.get("/api/terabox")
async def terabox(url: str = Query(..., description="TeraBox share URL")):
    return await _resolve(url)

@app.get("/api")
async def legacy(url: str = Query(..., description="TeraBox share URL")):
    return await _resolve(url)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=False)
