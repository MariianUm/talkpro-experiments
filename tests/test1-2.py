import asyncio
import random
import time
import statistics
import math
import hashlib
from dataclasses import dataclass
from typing import List, Optional


REQUESTS_TOTAL = 1000
UNIQUE_REQUESTS = 700
DUPLICATE_REQUESTS = REQUESTS_TOTAL - UNIQUE_REQUESTS

CONCURRENT_USERS = 50
REPEAT = 3

BATCH_WINDOW = 0.05
MAX_BATCH_SIZE = 50
MAX_CONCURRENT_API_CALLS = 25
TIMEOUT_SEC = 30.0

RANDOM_SEED = 42


def make_prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def generate_unique_prompts(n: int) -> List[str]:
    templates = [
        "Проанализируй резюме кандидата. Опыт: {exp} лет. Навыки: {skills}. Образование: {edu}. Проект: {project}.",
        "Оцени релевантность кандидата. Опыт: {exp} лет. Стек: {skills}. Достижение: {achievement}.",
        "Проверь резюме на преувеличения. Опыт: {exp} лет. Навыки: {skills}. Должность: {position}.",
        "Сделай AI-анализ резюме. Кандидат имеет {exp} лет опыта. Технологии: {skills}. Сертификат: {cert}.",
        "Оцени качество резюме для вакансии. Опыт: {exp} лет. Навыки: {skills}. Проекты: {project}.",
    ]

    skills_pool = [
        "Python", "Java", "C++", "SQL", "JavaScript", "React", "Docker",
        "Kubernetes", "Go", "Rust", "FastAPI", "Django", "PostgreSQL",
        "Redis", "Kafka", "Linux", "Git", "CI/CD", "Machine Learning"
    ]

    edu_pool = ["Бакалавр", "Магистр", "Высшее", "Курсы", "Среднее специальное"]

    projects_pool = [
        "CRM", "платежный шлюз", "чат-бот", "аналитическая платформа",
        "интернет-магазин", "HR-система", "сервис рекомендаций"
    ]

    achievements_pool = [
        "ускорил API на 30%", "внедрил CI/CD", "снизил нагрузку на БД",
        "автоматизировал тестирование", "разработал микросервис"
    ]

    positions_pool = [
        "Junior Developer", "Middle Developer", "Senior Developer",
        "Team Lead", "Backend Developer", "Data Engineer"
    ]

    cert_pool = ["AWS", "GCP", "Kubernetes", "Scrum", "PMP", "без сертификатов"]

    prompts = set()

    while len(prompts) < n:
        template = random.choice(templates)
        prompt = template.format(
            exp=random.randint(1, 20),
            skills=", ".join(random.sample(skills_pool, random.randint(3, 7))),
            edu=random.choice(edu_pool),
            project=random.choice(projects_pool),
            achievement=random.choice(achievements_pool),
            position=random.choice(positions_pool),
            cert=random.choice(cert_pool),
        )
        prompts.add(prompt)

    return list(prompts)


def build_test_tasks() -> List[str]:
    unique_prompts = generate_unique_prompts(UNIQUE_REQUESTS)
    duplicate_prompts = random.choices(unique_prompts, k=DUPLICATE_REQUESTS)

    all_prompts = unique_prompts + duplicate_prompts
    random.shuffle(all_prompts)

    assert len(all_prompts) == REQUESTS_TOTAL
    assert len(set(all_prompts)) == UNIQUE_REQUESTS

    print("Сформирован набор задач:")
    print(f"  Всего задач: {len(all_prompts)}")
    print(f"  Уникальных промптов: {len(set(all_prompts))}")
    print(f"  Дублирующих промптов: {len(all_prompts) - len(set(all_prompts))}")
    print(f"  Теоретический максимум экономии: {(DUPLICATE_REQUESTS / REQUESTS_TOTAL) * 100:.1f}%")

    return all_prompts


class MockGigaChatAPI:
    """
    Мок внешнего GigaChat API.

    capacity моделирует ограниченную пропускную способность внешнего API.
    Это нужно, чтобы проверить влияние gateway на P95 при пиковой нагрузке.
    """

    def __init__(
        self,
        min_delay: float = 0.5,
        max_delay: float = 2.0,
        error_rate: float = 0.001,
        capacity: int = 25,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.error_rate = error_rate
        self.semaphore = asyncio.Semaphore(capacity)
        self.api_calls = 0

    async def call(self, prompt: str) -> dict:
        self.api_calls += 1

        async with self.semaphore:
            await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

            if random.random() < self.error_rate:
                raise RuntimeError("Mock GigaChat error")

            return {"choices": [{"message": {"content": "OK"}}]}


class BaselineClient:
    def __init__(self, api: MockGigaChatAPI):
        self.api = api

    async def analyze(self, prompt: str) -> dict:
        return await self.api.call(prompt)


class GatewayClient:
    """
    Gateway для эксперимента:
    - cache-aside;
    - in-flight deduplication;
    - очередь с временным окном;
    - ограничение числа одновременных внешних API-вызовов.
    """

    def __init__(
        self,
        api: MockGigaChatAPI,
        batch_window: float = BATCH_WINDOW,
        max_batch_size: int = MAX_BATCH_SIZE,
        max_concurrent_api_calls: int = MAX_CONCURRENT_API_CALLS,
    ):
        self.api = api
        self.batch_window = batch_window
        self.max_batch_size = max_batch_size
        self.api_semaphore = asyncio.Semaphore(max_concurrent_api_calls)

        self.cache = {}
        self.inflight = {}
        self.queue = asyncio.Queue()
        self.lock = asyncio.Lock()

        self.cache_hits = 0
        self.cache_misses = 0
        self.deduplicated_requests = 0
        self.queued_requests = 0

        self.worker_task = asyncio.create_task(self._worker())

    async def analyze(self, prompt: str) -> dict:
        h = make_prompt_hash(prompt)

        if h in self.cache:
            self.cache_hits += 1
            return self.cache[h]

        self.cache_misses += 1

        async with self.lock:
            if h in self.inflight:
                self.deduplicated_requests += 1
                future = self.inflight[h]
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self.inflight[h] = future
                await self.queue.put((h, prompt, future))
                self.queued_requests += 1

        return await future

    async def _worker(self):
        while True:
            await asyncio.sleep(self.batch_window)
            await self._flush()

    async def _flush(self):
        items = []

        while not self.queue.empty() and len(items) < self.max_batch_size:
            items.append(await self.queue.get())

        if not items:
            return

        async def process_one(h, prompt, future):
            try:
                if h in self.cache:
                    if not future.done():
                        future.set_result(self.cache[h])
                    return

                async with self.api_semaphore:
                    result = await self.api.call(prompt)

                self.cache[h] = result

                if not future.done():
                    future.set_result(result)

            except Exception as e:
                if not future.done():
                    future.set_exception(e)

            finally:
                async with self.lock:
                    self.inflight.pop(h, None)

        await asyncio.gather(
            *[process_one(h, prompt, future) for h, prompt, future in items],
            return_exceptions=True
        )

    async def close(self):
        self.worker_task.cancel()
        try:
            await self.worker_task
        except asyncio.CancelledError:
            pass


@dataclass
class TestResult:
    total: int
    success: int
    errors: int
    timeouts: int
    latencies: List[float]
    api_calls: int
    cache_hits: int = 0
    cache_misses: int = 0
    deduplicated_requests: int = 0
    queued_requests: int = 0

    @property
    def success_rate(self) -> float:
        return self.success / self.total * 100 if self.total else 0.0

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        idx = math.ceil(0.95 * len(ordered)) - 1
        return ordered[idx]


async def run_load_test(client, prompts: List[str], api: MockGigaChatAPI) -> TestResult:
    results = {
        "total": 0,
        "success": 0,
        "errors": 0,
        "timeouts": 0,
        "latencies": [],
    }

    chunks = [
        prompts[i::CONCURRENT_USERS]
        for i in range(CONCURRENT_USERS)
    ]

    async def worker(worker_prompts: List[str]):
        for prompt in worker_prompts:
            started_at = time.perf_counter()
            results["total"] += 1

            try:
                response = await asyncio.wait_for(
                    client.analyze(prompt),
                    timeout=TIMEOUT_SEC
                )

                if not response or "choices" not in response:
                    results["errors"] += 1
                    continue

                latency = time.perf_counter() - started_at
                results["latencies"].append(latency)
                results["success"] += 1

            except asyncio.TimeoutError:
                results["timeouts"] += 1

            except Exception:
                results["errors"] += 1

    await asyncio.gather(*[worker(chunk) for chunk in chunks])

    return TestResult(
        total=results["total"],
        success=results["success"],
        errors=results["errors"],
        timeouts=results["timeouts"],
        latencies=results["latencies"],
        api_calls=api.api_calls,
        cache_hits=getattr(client, "cache_hits", 0),
        cache_misses=getattr(client, "cache_misses", 0),
        deduplicated_requests=getattr(client, "deduplicated_requests", 0),
        queued_requests=getattr(client, "queued_requests", 0),
    )


def pct_reduction(base: float, exp: float) -> float:
    if base == 0:
        return 0.0
    return (base - exp) / base * 100


async def run_once(run_number: int):
    print(f"\nПрогон {run_number}/{REPEAT}")

    prompts = build_test_tasks()

    baseline_api = MockGigaChatAPI()
    baseline_client = BaselineClient(baseline_api)

    print("Baseline...")
    baseline = await run_load_test(baseline_client, prompts, baseline_api)

    gateway_api = MockGigaChatAPI()
    gateway_client = GatewayClient(gateway_api)

    print("Gateway...")
    gateway = await run_load_test(gateway_client, prompts, gateway_api)
    await gateway_client.close()

    print(f"  Baseline: api_calls={baseline.api_calls}, avg={baseline.avg_latency:.3f}s, p95={baseline.p95_latency:.3f}s, success={baseline.success_rate:.2f}%")
    print(f"  Gateway:  api_calls={gateway.api_calls}, avg={gateway.avg_latency:.3f}s, p95={gateway.p95_latency:.3f}s, success={gateway.success_rate:.2f}%")
    print(f"  Gateway cache_hits={gateway.cache_hits}, deduplicated={gateway.deduplicated_requests}, queued={gateway.queued_requests}")

    return baseline, gateway


async def main():
    random.seed(RANDOM_SEED)

    baseline_results = []
    gateway_results = []

    for i in range(1, REPEAT + 1):
        baseline, gateway = await run_once(i)
        baseline_results.append(baseline)
        gateway_results.append(gateway)

    avg_baseline_api_calls = statistics.mean(r.api_calls for r in baseline_results)
    avg_gateway_api_calls = statistics.mean(r.api_calls for r in gateway_results)

    avg_baseline_p95 = statistics.mean(r.p95_latency for r in baseline_results)
    avg_gateway_p95 = statistics.mean(r.p95_latency for r in gateway_results)

    avg_baseline_latency = statistics.mean(r.avg_latency for r in baseline_results)
    avg_gateway_latency = statistics.mean(r.avg_latency for r in gateway_results)

    avg_baseline_success = statistics.mean(r.success_rate for r in baseline_results)
    avg_gateway_success = statistics.mean(r.success_rate for r in gateway_results)

    api_economy = pct_reduction(avg_baseline_api_calls, avg_gateway_api_calls)
    avg_latency_reduction = pct_reduction(avg_baseline_latency, avg_gateway_latency)
    p95_reduction = pct_reduction(avg_baseline_p95, avg_gateway_p95)

    print("ИТОГИ ЭКСПЕРИМЕНТА")

    print(f"Baseline API calls:       {avg_baseline_api_calls:.1f}")
    print(f"Gateway API calls:        {avg_gateway_api_calls:.1f}")
    print(f"Экономия API-вызовов:     {api_economy:.1f}%")
    print()
    print(f"Baseline avg latency:     {avg_baseline_latency:.3f}s")
    print(f"Gateway avg latency:      {avg_gateway_latency:.3f}s")
    print(f"Снижение avg latency:     {avg_latency_reduction:.1f}%")
    print()
    print(f"Baseline P95 latency:     {avg_baseline_p95:.3f}s")
    print(f"Gateway P95 latency:      {avg_gateway_p95:.3f}s")
    print(f"Изменение P95 latency:    {p95_reduction:.1f}%")
    print()
    print(f"Baseline success rate:    {avg_baseline_success:.2f}%")
    print(f"Gateway success rate:     {avg_gateway_success:.2f}%")

    print("\nЦелевые значения:")
    print("  Экономия API-вызовов: 25–30%")
    print("  Success rate: ≥99.5%")
    print("  P95: не хуже baseline или снижение при ограниченной пропускной способности API")


if __name__ == "__main__":
    asyncio.run(main())