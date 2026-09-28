# 🚀 Ak TeraBox Resolver API

Standalone FastAPI API for TeraBox share links, built in the same simple style as the Ak xHamster resolver project.

## Endpoints

- `GET /` — API information
- `GET /health` — health check
- `GET /api/terabox?url=<TERABOX_URL>` — resolve TeraBox share
- `GET /api?url=<TERABOX_URL>` — compatibility endpoint
- `GET /docs` — Swagger UI

## Example

```text
https://YOUR-RENDER-URL.onrender.com/api/terabox?url=https://1024terabox.com/s/XXXXXXXX
```

The response includes filename, size, extension, thumbnail, fs_id, metadata and a direct/download URL when TeraBox exposes one to the resolver.

## Supported share domains

`terabox.app`, `terabox.com`, `1024terabox.com`, `1024tera.com`, `terasharefile.com`, `terasharelink.com`, `terafileshare.com`, `teraboxshare.com`, `teraboxlink.com`, `nephobox.com` and related subdomains.

## Important

TeraBox links and tokens can expire or require verification. The API does not hard-code the session/token values from a captured HAR. For shares that require authentication/verification, set `TERABOX_COOKIE` or configure an authorized resolver fallback using `TERABOX_PROXY_URL`.

Do not expose private cookies publicly or commit them to GitHub.

## Render

Use Docker deployment or the Python service with:

```text
Build: pip install -r requirements.txt
Start: uvicorn app:app --host 0.0.0.0 --port $PORT
```

Python 3.11 is recommended.
