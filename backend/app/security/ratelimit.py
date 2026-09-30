from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from ..config import get_settings
from ..deps import current_user

_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(user=Depends(current_user)):
    """Sliding-window limiter per user (in-memory; use Redis if you scale to multiple workers)."""
    limit, window = get_settings().rate_limit_per_min, 60
    now = time.monotonic()
    q = _hits[user.id]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests. Please slow down.")
    q.append(now)


def reset_rate_limits() -> None:
    _hits.clear()
