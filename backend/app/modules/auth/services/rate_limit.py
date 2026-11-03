# backend/app/modules/auth/services/rate_limit.py

"""Ограничение попыток по IP в памяти одного процесса."""

from asyncio import Lock
from collections import defaultdict, deque
from datetime import datetime, timedelta

_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_lock = Lock()

async def check_ip_rate_limit(ip: str, limit: int, window_minutes: int) -> bool:
	"""Вернуть True, если запрос нужно отклонить из-за превышения лимита."""
	now = datetime.utcnow()
	window_start = now - timedelta(minutes=window_minutes)

	async with _lock:
		bucket = _attempts[ip]
		while bucket and bucket[0] < window_start:
			bucket.popleft()

		if len(bucket) >= limit:
			return True

		bucket.append(now)
		return False
