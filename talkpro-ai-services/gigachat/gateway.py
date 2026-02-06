import ssl
import base64
import httpx
import uuid
import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from .prompts import ANALYSIS_PROMPTS

logger = logging.getLogger(__name__)

class GigaChatGateway:
    """AI Gateway с кэшированием, батчингом и контролем RPS."""
    
    def __init__(
        self,
        api_key: str,  # это base64 от client_id:client_secret
        base_url: str = "https://gigachat.devices.sberbank.ru/api/v1",
        model: str = "GigaChat",
        max_rps: int = 10,
        batch_window: float = 0.1,
        max_batch_size: int = 10,
        cache_ttl: int = 3600,
        use_redis: bool = False,
        redis_url: str = "redis://localhost:6379"
    ):
        # Декодируем ключ и разделяем на client_id и client_secret
        decoded = base64.b64decode(api_key).decode()
        self.client_id, self.client_secret = decoded.split(':', 1)

        self.api_key = api_key
        
        self.base_url = base_url
        self.model = model
        self.max_rps = max_rps
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
        self.rps_semaphore = asyncio.Semaphore(max_rps)
        
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "batched_requests": 0,
            "api_calls": 0,
            "errors": 0
        }
        
        self._start_batch_processor()
    
    async def _get_access_token(self) -> str:
        """Получает новый токен по Client ID и Client Secret"""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        # Формируем Basic Auth из пары client_id:client_secret
        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_base64 = base64.b64encode(auth_str.encode()).decode()
        
        rquid = str(uuid.uuid4())
        headers = {
            "Authorization": f"Basic {auth_base64}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": rquid,
            "Accept": "application/json"
        }
        data = {"scope": "GIGACHAT_API_PERS"}
        
        # Отладка
        print("\n=== ОТЛАДКА АВТОРИЗАЦИИ ===")
        print(f"URL: https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        print(f"Auth header (первые 50): {auth_base64[:50]}...")
        print(f"RqUID: {rquid}")
        print(f"Data: {data}")
        print("=============================\n")

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers=headers,
                data=data
            )
            print(f"Статус ответа: {resp.status_code}")
            print(f"Тело ответа: {resp.text}")
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
    
    async def _flush_batch(self):
        if self.batch_queue.empty():
            return
        
        requests = []
        while not self.batch_queue.empty() and len(requests) < self.max_batch_size:
            requests.append(await self.batch_queue.get())
        
        if not requests:
            return
        
        async def send_one(req):
            async with self.rps_semaphore:
                try:
                    resp = await self._call_api(req["prompt"])
                    req["future"].set_result(resp)
                except Exception as e:
                    req["future"].set_exception(e)
                finally:
                    self.stats["api_calls"] += 1
        
        await asyncio.gather(*[send_one(req) for req in requests])
        self.stats["batched_requests"] += len(requests)
    
    async def analyze(
        self,
        prompt_key: str,
        text: str,
        **kwargs
    ) -> Optional[dict]:
        prompt_template = ANALYSIS_PROMPTS.get(prompt_key)
        if not prompt_template:
            raise ValueError(f"Неизвестный ключ промпта: {prompt_key}")
        
        prompt = prompt_template.format(text=text, **kwargs)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        
        cached = await self._cache_get(prompt_hash)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        
        self.stats["cache_misses"] += 1
        
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        await self.batch_queue.put({
            "prompt": prompt,
            "future": future,
            "prompt_hash": prompt_hash
        })
        
        try:
            result = await future
            await self._cache_set(prompt_hash, result)
            return result
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Ошибка при обработке запроса: {e}")
            return None
    
    async def _call_api(self, prompt: str) -> dict:
        """Реальный вызов GigaChat API с использованием токена."""
        if self.api_key == "test_key":
            await asyncio.sleep(0.2)
            return {"choices": [{"message": {"content": "85"}}]}

        token = await self._get_access_token()
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7
            }
        )
        response.raise_for_status()
        return response.json()
    
    # Методы кэширования
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
        await self.client.aclose()
        if self.use_redis:
            await self.redis.close()
    
    def get_stats(self) -> dict:
        return self.stats.copy()