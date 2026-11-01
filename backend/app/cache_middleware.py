"""In-process response cache for GET requests.

Supabase's free-tier pooler is slow (see query_engine.py notes), so repeat
reads are cached in memory for CACHE_TTL seconds. Any non-GET request
(a write) clears the whole cache rather than tracking per-key invalidation —
simplest way to guarantee no stale reads after a calculation/edit.
"""
from __future__ import annotations

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

CACHE_TTL = 4 * 3600  # 4 hours
_cache: dict[str, tuple[float, bytes, int, str | None]] = {}


class CacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != "GET":
            _cache.clear()
            return await call_next(request)

        key = str(request.url)
        now = time.time()
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            _, body, status_code, media_type = hit
            return Response(content=body, status_code=status_code, media_type=media_type,
                             headers={"Cache-Control": f"public, max-age={CACHE_TTL}", "X-Cache": "HIT"})

        response = await call_next(request)
        if response.status_code != 200:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        _cache[key] = (now, body, response.status_code, response.media_type)
        return Response(content=body, status_code=response.status_code, media_type=response.media_type,
                         headers={"Cache-Control": f"public, max-age={CACHE_TTL}", "X-Cache": "MISS"})
