"""TeraBox share resolver.

The resolver first talks to TeraBox's share page/list endpoints. It never
stores the user's cookies or hard-codes a captured session/token. If a public
share only exposes metadata, the API returns that metadata and an empty direct
link instead of pretending a link was resolved.

An optional TERABOX_PROXY_URL can be configured as a fallback for environments
where TeraBox requires browser/cookie token resolution. The proxy is expected
to accept ?mode=resolve&surl=<short-code>&raw=1 and return either an upstream
TeraBox response or a JSON object containing a file list.
"""
import html
import json
import logging
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

import config

logger = logging.getLogger("terabox_resolver")

DOMAINS = {
    "terabox.app", "terabox.com", "www.terabox.com", "teraboxshare.com",
    "teraboxlink.com", "terasharefile.com", "terafileshare.com",
    "terasharelink.com", "1024terabox.com", "www.1024terabox.com",
    "1024tera.com", "www.1024tera.com", "nephobox.com", "4funbox.com",
    "momerybox.com", "teraboxapp.com",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150.0 Safari/537.36"


def _host(url):
    return (urlparse(url).hostname or "").lower().split(":")[0]


def is_terabox_link(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and any(
            p.hostname == d or p.hostname.endswith("." + d) for d in DOMAINS if p.hostname
        )
    except Exception:
        return False


def extract_surl(url: str, final_url: str | None = None) -> str:
    candidates = [url, final_url or ""]
    for raw in candidates:
        if not raw:
            continue
        p = urlparse(raw)
        q = parse_qs(p.query)
        for key in ("surl", "shorturl"):
            if q.get(key):
                return q[key][0].strip()
        m = re.search(r"/s/([^/?#]+)", p.path)
        if m:
            return unquote(m.group(1)).strip()
        # Some old links use /sharing/link?surl=...
    raise ValueError("Could not extract TeraBox share code (surl) from URL")


def _cookies():
    out = {}
    raw = config.TERABOX_COOKIE
    if raw:
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k:
                    out[k] = v
    return out


def _extract_jstoken(text: str) -> str:
    patterns = [
        r'window\\?\.jsToken\s*=\s*["\']([^"\']+)',
        r'window\.jsToken\s*=\s*JSON\.parse\(["\']([^"\']+)',
        r'"jsToken"\s*:\s*"([^"]+)"',
        r'\\"jsToken\\"\s*:\s*\\"([^"\\]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return html.unescape(m.group(1))
    return ""


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    c = _cookies()
    if c:
        s.cookies.update(c)
    return s


def _format_size(n):
    try:
        n = int(n)
    except Exception:
        return "Unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return "Unknown"


def _thumbs(item):
    t = item.get("thumbs") or {}
    return [u for u in (t.get("url3"), t.get("url2"), t.get("url1"), t.get("icon")) if u]


def _direct_from_dlink(session, dlink):
    if not dlink:
        return ""
    try:
        r = session.head(dlink, allow_redirects=False, timeout=config.REQUEST_TIMEOUT)
        return r.headers.get("Location") or dlink
    except requests.RequestException:
        return dlink


def _call_proxy(session, surl):
    if not config.TERABOX_PROXY_URL:
        return None
    r = session.get(config.TERABOX_PROXY_URL, params={"mode": "resolve", "surl": surl, "raw": "1"}, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("upstream", data.get("data", data))


def _share_list(session, base_domain, surl, js_token=""):
    # Current TeraBox-family endpoints used by public share pages/apps.
    hosts = [base_domain, "www.terabox.com", "www.1024tera.com", "nephobox.com"]
    seen = set()
    last = None
    for host in hosts:
        if host in seen:
            continue
        seen.add(host)
        endpoint = f"https://{host}/share/list"
        params = {"app_id": "250528", "shorturl": surl, "root": "1", "page": "1", "num": "500"}
        if js_token:
            params["jsToken"] = js_token
        try:
            r = session.get(endpoint, params=params, headers={"Referer": f"https://{host}/sharing/link?surl={quote(surl)}"}, timeout=config.REQUEST_TIMEOUT)
            if r.status_code != 200:
                last = f"share/list HTTP {r.status_code}"
                continue
            data = r.json()
            if isinstance(data, dict) and data.get("list"):
                return data
            last = data
        except Exception as e:
            last = str(e)
    return {"errno": -1, "errmsg": str(last or "No file list returned")}


def _normalize_file(item, session):
    name = item.get("server_filename") or item.get("filename") or "Unknown"
    size = item.get("size", 0)
    try: size_int = int(size)
    except Exception: size_int = 0
    dlink = item.get("dlink") or item.get("download_url") or item.get("download_link") or ""
    direct = _direct_from_dlink(session, dlink) if dlink else ""
    thumbs = _thumbs(item)
    return {
        "filename": name,
        "name": name,
        "size": _format_size(size_int),
        "size_bytes": size_int,
        "extension": name.rsplit(".", 1)[-1].lower() if "." in name else "",
        "category": "Video" if item.get("category") in (1, "1") or name.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi")) else "File",
        "thumbnail": thumbs[0] if thumbs else "",
        "thumbnails": thumbs,
        "download_url": direct or dlink,
        "direct_url": direct or dlink,
        "path": item.get("path", ""),
        "fs_id": str(item.get("fs_id", "")),
        "duration_seconds": item.get("duration"),
        "width": item.get("width"),
        "height": item.get("height"),
        "is_directory": str(item.get("isdir", "0")) == "1",
    }


def resolve_terabox(url: str) -> dict:
    if not is_terabox_link(url):
        raise ValueError("Invalid TeraBox share URL")

    session = _session()
    original = url
    try:
        page = session.get(url, allow_redirects=True, timeout=config.REQUEST_TIMEOUT)
        final_url = page.url
        surl = extract_surl(url, final_url)
        js_token = _extract_jstoken(page.text)
        base_domain = _host(final_url) or "www.terabox.com"
    except requests.RequestException as e:
        raise RuntimeError(f"Unable to open TeraBox share page: {e}")

    data = _share_list(session, base_domain, surl, js_token)
    if data.get("errno") not in (0, "0") or not data.get("list"):
        proxy_data = _call_proxy(session, surl)
        if proxy_data and proxy_data.get("list"):
            data = proxy_data
        else:
            msg = data.get("errmsg") or data.get("error") or "No files found"
            return {"error": msg, "errno": data.get("errno", -1), "surl": surl}

    files = [_normalize_file(x, session) for x in data.get("list", []) if isinstance(x, dict)]
    first = files[0] if files else {}
    title = data.get("title") or first.get("filename") or "TeraBox file"
    thumbs = [f["thumbnail"] for f in files if f.get("thumbnail")]

    links = []
    for f in files:
        if f.get("download_url"):
            links.append({"title": f["filename"], "url": f["download_url"]})

    return {
        "title": title,
        "files": files,
        "links": links,
        "m3u8_links": [],
        "download_url": first.get("download_url", ""),
        "thumbnail": first.get("thumbnail", ""),
        "size": first.get("size", "Unknown"),
        "size_bytes": first.get("size_bytes", 0),
        "extension": first.get("extension", ""),
        "category": first.get("category", "File"),
        "videoDetails": {
            "title": title,
            "lengthSeconds": first.get("duration_seconds"),
            "thumbnails": [{"url": u} for u in thumbs],
            "width": first.get("width"),
            "height": first.get("height"),
        },
        "source_url": original,
        "surl": surl,
    }
