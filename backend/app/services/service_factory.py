"""Service factory — creates AnalyticsService instances."""
from functools import lru_cache
from app.services.analytics_service import AnalyticsService

# One shared instance per process — DuckDB is in-memory and thread-safe for reads
@lru_cache(maxsize=1)
def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()

def get_service() -> AnalyticsService:
    """Cached service for READ-ONLY endpoints — no view refresh."""
    return get_analytics_service()

def get_fresh_service() -> AnalyticsService:
    """Service with throttled view refresh — call after data WRITES (Analyze/Ingest).
    Throttle is 30 s so concurrent requests don't each re-scan parquet files.
    """
    svc = get_analytics_service()
    svc.engine.refresh()   # throttled internally — cheap if called within 30 s
    return svc

def invalidate_service_cache() -> AnalyticsService:
    """Force-refresh immediately — call right after warehouse ingest."""
    svc = get_analytics_service()
    svc.engine.refresh(force=True)
    return svc
