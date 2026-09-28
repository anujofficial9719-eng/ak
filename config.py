import os

PORT = int(os.getenv("PORT", "8000"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "25"))
# Optional cookie string, e.g. ndus=...;csrfToken=...
TERABOX_COOKIE = os.getenv("TERABOX_COOKIE", "").strip()
# Optional fallback gateway. Leave empty for direct TeraBox resolution.
TERABOX_PROXY_URL = os.getenv("TERABOX_PROXY_URL", "").strip()
