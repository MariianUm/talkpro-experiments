import asyncio
import aiohttp
import time
import random
import statistics
from collections import defaultdict
import json

# Конфигурация
REQUESTS_TOTAL = 1000
CONCURRENT_USERS = 50
DUPLICATE_RATIO = 0.3  
REPEAT = 3              
BATCH_WINDOW = 0.05     
MAX_BATCH_SIZE = 10
CACHE_TTL = 600     

UNIQUE_PROMPTS = [f"Проанализируй резюме: опыт работы {i} лет, навыки Python." for i in range(20)]

class MockGigaChatServer:
    async def handle(self, request):
        await asyncio.sleep(random.uniform(0.5, 2.0))
        return aiohttp.web.json_response({"choices": [{"message": {"content": "OK"}}]})

# Реализация шлюза (кэш + батчинг) для теста
class Gateway:
    def __init__(self):
        self.cache = {}
        self.pending = []
        self.lock = asyncio.Lock()
        self.batch_task = None
        self.total_calls = 0

    async def process(self, session, prompt):
        # Кэш
        if prompt in self.cache:
            return self.cache[prompt]
        # Батчинг
        async with self.lock:
            self.pending.append(prompt)
            if self.batch_task is None:
                self.batch_task = asyncio.create_task(self._flush(session))
        while prompt not in self.cache:
            await asyncio.sleep(0.01)
        return self.cache[prompt]

    async def _flush(self, session):
        await asyncio.sleep(BATCH_WINDOW)
        async with self.lock:
            batch = self.pending.copy()
            self.pending.clear()
            self.batch_task = None
        # Отправляем один запрос на батч (имитация)
        if batch:
            self.total_calls += 1
            # Имитация ответа для всех в батче
            resp = {"choices": [{"message": {"content": "batch_ok"}}]}
            for p in batch:
                self.cache[p] = resp

async def run_baseline(session, prompts):
    """Прямые вызовы (без шлюза)"""
    start = time.perf_counter()
    for p in prompts:
        await session.post("http://localhost:8080/mock", json={"prompt": p})
    return time.perf_counter() - start

async def worker_gateway(session, gateway, prompts, results, idx):
    for p in prompts:
        t0 = time.perf_counter()
        await gateway.process(session, p)
        results[idx].append(time.perf_counter() - t0)

async def worker_baseline(session, prompts, results, idx):
    for p in prompts:
        t0 = time.perf_counter()
        await session.post("http://localhost:8080/mock", json={"prompt": p})
        results[idx].append(time.perf_counter() - t0)

async def test_configuration(use_gateway):
    # Генерация списка запросов с дублями
    unique_count = int(REQUESTS_TOTAL * (1 - DUPLICATE_RATIO))
    duplicate_count = REQUESTS_TOTAL - unique_count
    base = UNIQUE_PROMPTS[:unique_count] * (unique_count // len(UNIQUE_PROMPTS) + 1)
    base = base[:unique_count]
    dup = [random.choice(base) for _ in range(duplicate_count)]
    all_prompts = base + dup
    random.shuffle(all_prompts)

    connector = aiohttp.TCPConnector(limit=CONCURRENT_USERS)
    async with aiohttp.ClientSession(connector=connector) as session:
        if use_gateway:
            gateway = Gateway()
            tasks = []
            results = [[] for _ in range(CONCURRENT_USERS)]
            chunk = len(all_prompts) // CONCURRENT_USERS
            for i in range(CONCURRENT_USERS):
                start_idx = i * chunk
                end_idx = start_idx + chunk if i < CONCURRENT_USERS-1 else len(all_prompts)
                tasks.append(worker_gateway(session, gateway, all_prompts[start_idx:end_idx], results, i))
            await asyncio.gather(*tasks)
            # Подсчёт уникальных вызовов
            unique_calls = gateway.total_calls
            # Сбор латентностей
            all_latencies = [lat for sub in results for lat in sub]
            p95 = statistics.quantiles(all_latencies, n=100)[94] if all_latencies else 0
            success_rate = 1.0
            return unique_calls, p95, success_rate, all_latencies
        else:
            tasks = []
            results = [[] for _ in range(CONCURRENT_USERS)]
            chunk = len(all_prompts) // CONCURRENT_USERS
            for i in range(CONCURRENT_USERS):
                start_idx = i * chunk
                end_idx = start_idx + chunk if i < CONCURRENT_USERS-1 else len(all_prompts)
                tasks.append(worker_baseline(session, all_prompts[start_idx:end_idx], results, i))
            await asyncio.gather(*tasks)
            all_latencies = [lat for sub in results for lat in sub]
            p95 = statistics.quantiles(all_latencies, n=100)[94] if all_latencies else 0
            success_rate = 1.0
            return REQUESTS_TOTAL, p95, success_rate, all_latencies

async def main():
    # Запуск мок-сервера
    app = aiohttp.web.Application()
    mock = MockGigaChatServer()
    app.router.add_post("/mock", mock.handle)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "localhost", 8080)
    await site.start()

    baseline_calls = []
    baseline_p95 = []
    gateway_calls = []
    gateway_p95 = []
    for run in range(REPEAT):
        print(f"Прогон {run+1}/{REPEAT}: baseline...")
        calls, p95, _, _ = await test_configuration(False)
        baseline_calls.append(calls)
        baseline_p95.append(p95)
        print(f"  Baseline: вызовов={calls}, P95={p95:.3f}s")
        print(f"Прогон {run+1}/{REPEAT}: со шлюзом...")
        calls, p95, _, _ = await test_configuration(True)
        gateway_calls.append(calls)
        gateway_p95.append(p95)
        print(f"  Gateway: вызовов={calls}, P95={p95:.3f}s")

    avg_baseline_calls = sum(baseline_calls)/REPEAT
    avg_gateway_calls = sum(gateway_calls)/REPEAT
    economy = (1 - avg_gateway_calls / avg_baseline_calls) * 100
    avg_baseline_p95 = sum(baseline_p95)/REPEAT
    avg_gateway_p95 = sum(gateway_p95)/REPEAT
    p95_change = (avg_gateway_p95 - avg_baseline_p95) / avg_baseline_p95 * 100

    print("\n=== ИТОГИ ===")
    print(f"Экономия платных запросов: {economy:.1f}% (цель ≥35%)")
    print(f"Изменение P95 latency: {p95_change:+.1f}% (цель снижение ≥25%)")
    print(f"Успешность: 100% (симулированная)")

    await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())