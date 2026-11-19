"""Safe URL retrieval utilities."""

from app.intelligence.url_scanning.safe_fetch import SafeURLFetcher, UnsafeURLError

__all__ = ["SafeURLFetcher", "UnsafeURLError"]
