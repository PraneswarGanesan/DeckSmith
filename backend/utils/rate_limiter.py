import time
from utils.config import settings

class RateLimiter:
    def __init__(self):
        self.limit = settings.UNSPLASH_RATE_LIMIT
        self.calls = []

    def allow(self):
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 60]

        if len(self.calls) < self.limit:
            self.calls.append(now)
            return True
        return False


rate_limiter = RateLimiter()