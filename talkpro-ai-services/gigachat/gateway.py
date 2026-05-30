import base64
import httpx
import uuid
import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, Optional, Tuple, Any

from .prompts import ANALYSIS_PROMPTS

logger = logging.getLogger(__name__)


class GigaChatGateway:

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://gigachat.devices.sberbank.ru/api/v1",
        model: str = "GigaChat",
        max_concurrent_api_calls: int = 10,
        batch_window: float = 0.05,
        max_batch_size: int = 50,
        cache_ttl: int = 3600,
        use_redis: bool = False,
        redis_url: str = "redis://localhost:6379",
    ):
        self.api_key = api_key

        if api_key == "test_key":
            self.client_id = "test"
            self.client_secret = "test"
        else:
            decoded = base64.b64decode(api_key).decode()
            self.client_id, self.client_secret = decoded.split(":", 1)

        self.base_url = base_url
        self.model = model
        self.max_concurrent_api_calls = max_concurrent_api_calls
        self.batch_window = batch_window
        self.max_batch_size = max_batch_size
        self.cache_ttl = cache_ttl

        self.client = httpx.AsyncClient(timeout=30.0, verify=False)
        self.access_token = None
        self.token_expires_at = 0

        self.use_redis = use_redis
        if use_redis:
            import aioredis
            self.redis = aioredis.from_url(redis_url)
            self._cache_get = self._redis_get
            self._cache_set = self._redis_set
        else:
            self.cache: Dict[str, Tuple[float, dict]] = {}
            self._cache_get = self._memory_get
            self._cache_set = self._memory_set

        self.batch_queue: asyncio.Queue = asyncio.Queue()
        self.batch_task: Optional[asyncio.Task] = None

        self.api_semaphore = asyncio.Semaphore(max_concurrent_api_calls)

        self.inflight: Dict[str, asyncio.Future] = {}

        self.lock = asyncio.Lock()

        self.stats = {
            "requests_total": 0,
            "success": 0,
            "errors": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "deduplicated_requests": 0,
            "queued_requests": 0,
            "api_calls": 0,
        }

        self._start_batch_processor()

    async def _get_access_token(self) -> str:
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_base64 = base64.b64encode(auth_str.encode()).decode()

        rquid = str(uuid.uuid4())
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": rquid,
            "Accept": "application/json",
        }
        data = {"scope": "GIGACHAT_API_PERS"}

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers=headers,
                data=data,
            )
            resp.raise_for_status()
            token_data = resp.json()
            self.access_token = token_data["access_token"]
            self.token_expires_at = token_data["expires_at"] / 1000
            return self.access_token

    def _start_batch_processor(self):
        async def processor():
            while True:
                await asyncio.sleep(self.batch_window)
                await self._flush_batch()

        self.batch_task = asyncio.create_task(processor())

    async def analyze(
        self,
        prompt_key: str,
        text: str,
        **kwargs
    ) -> Optional[dict]:
        self.stats["requests_total"] += 1

        prompt_template = ANALYSIS_PROMPTS.get(prompt_key)
        if not prompt_template:
            self.stats["errors"] += 1
            raise ValueError(f"Неизвестный ключ промпта: {prompt_key}")

        prompt = prompt_template.format(text=text, **kwargs)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        cached = await self._cache_get(prompt_hash)
        if cached is not None:
            self.stats["cache_hits"] += 1
            self.stats["success"] += 1
            return cached

        self.stats["cache_misses"] += 1

        async with self.lock:
            if prompt_hash in self.inflight:
                self.stats["deduplicated_requests"] += 1
                future = self.inflight[prompt_hash]
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self.inflight[prompt_hash] = future

                await self.batch_queue.put({
                    "prompt": prompt,
                    "prompt_hash": prompt_hash,
                    "future": future,
                })
                self.stats["queued_requests"] += 1

        try:
            result = await future
            self.stats["success"] += 1
            return result
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Ошибка при обработке запроса: {e}")
            return None

    async def _flush_batch(self):
        if self.batch_queue.empty():
            return

        requests = []

        while not self.batch_queue.empty() and len(requests) < self.max_batch_size:
            requests.append(await self.batch_queue.get())

        if not requests:
            return

        async def send_one(req):
            prompt = req["prompt"]
            prompt_hash = req["prompt_hash"]
            future = req["future"]

            try:
                cached = await self._cache_get(prompt_hash)
                if cached is not None:
                    if not future.done():
                        future.set_result(cached)
                    return

                async with self.api_semaphore:
                    self.stats["api_calls"] += 1
                    resp = await self._call_api(prompt)

                await self._cache_set(prompt_hash, resp)

                if not future.done():
                    future.set_result(resp)

            except Exception as e:
                if not future.done():
                    future.set_exception(e)

            finally:
                async with self.lock:
                    self.inflight.pop(prompt_hash, None)

        await asyncio.gather(*[send_one(req) for req in requests], return_exceptions=True)

    async def _call_api(self, prompt: str) -> dict:
        if self.api_key == "test_key":
            await asyncio.sleep(0.5)
            return {"choices": [{"message": {"content": "85"}}]}

        token = await self._get_access_token()
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
        )
        response.raise_for_status()
        return response.json()

    async def _memory_get(self, key: str) -> Optional[dict]:
        entry = self.cache.get(key)
        if entry and time.time() - entry[0] < self.cache_ttl:
            return entry[1]
        return None

    async def _memory_set(self, key: str, value: dict):
        self.cache[key] = (time.time(), value)

    async def _redis_get(self, key: str) -> Optional[dict]:
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def _redis_set(self, key: str, value: dict):
        await self.redis.setex(key, self.cache_ttl, json.dumps(value))

    async def close(self):
        if self.batch_task:
            self.batch_task.cancel()
            try:
                await self.batch_task
            except asyncio.CancelledError:
                pass

        await self.client.aclose()

        if self.use_redis:
            await self.redis.close()

    def get_stats(self) -> dict:
        return self.stats.copy()