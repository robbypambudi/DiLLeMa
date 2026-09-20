import asyncio
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor


class BudgetExceeded(Exception):
    pass


class CircuitOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failures: int, cooldown_ms: int):
        self.threshold = failures
        self.cooldown = cooldown_ms / 1000
        self.failures = 0
        self.open_until = 0.0

    def check(self):
        if time.monotonic() < self.open_until:
            raise CircuitOpen()

    def success(self):
        self.failures = 0
        self.open_until = 0

    def failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = time.monotonic() + self.cooldown


class BoundedWorker:
    """Cancellation stops waiting, not native inference; retain the permit."""

    def __init__(self, concurrency: int):
        self.slots = asyncio.Semaphore(concurrency)
        self.executor = ThreadPoolExecutor(
            max_workers=concurrency, thread_name_prefix="adaptive"
        )
        self.pending = set()

    async def run(self, fn, *args, **kwargs):
        await self.slots.acquire()
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(self.executor, lambda: fn(*args, **kwargs))
        except BaseException:
            self.slots.release()
            raise
        self.pending.add(future)

        def finished(done):
            self.pending.discard(done)
            self.slots.release()
            if not done.cancelled():
                done.exception()  # consume errors after the caller has cancelled

        future.add_done_callback(finished)
        return await asyncio.shield(future)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)


class TTLCache:
    def __init__(self, size: int, ttl: float):
        self.size, self.ttl = size, ttl
        self.values = OrderedDict()

    def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        expiry, value = item
        if expiry <= time.monotonic():
            self.values.pop(key, None)
            return None
        self.values.move_to_end(key)
        return value

    def put(self, key, value):
        if not self.size or not self.ttl:
            return
        self.values[key] = (time.monotonic() + self.ttl, value)
        self.values.move_to_end(key)
        while len(self.values) > self.size:
            self.values.popitem(last=False)
