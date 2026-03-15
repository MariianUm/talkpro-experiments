import asyncio
import time
import random
import statistics
import os
from dotenv import load_dotenv
from job_search.job_adapter import JobSearchAdapter

load_dotenv()
SUPERJOB_SECRET_KEY = os.getenv("SUPERJOB_SECRET_KEY")
if not SUPERJOB_SECRET_KEY:
    raise ValueError("SUPERJOB_SECRET_KEY not found")

keywords = [
    "Python разработчик",
    "Аналитик данных",
    "Frontend разработчик",
    "DevOps инженер",
    "Java разработчик",
    "Системный аналитик",
    "Менеджер проектов",
    "Data Scientist",
    "Разработчик C++",
    "Тестировщик QA",
]

towns = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург"]

queries = []
for i in range(50):
    kw = keywords[i % len(keywords)]
    town = towns[i % len(towns)]
    queries.append((kw, town))

async def run_test():
    adapter = JobSearchAdapter(superjob_secret_key=SUPERJOB_SECRET_KEY)
    results = []
    total_success = 0
    times = []

    print("="*60)
    print("ТЕСТИРОВАНИЕ ГИПОТЕЗЫ №3: 50 поисковых запросов")
    print("="*60)

    for idx, (keyword, town) in enumerate(queries, 1):
        start = time.time()
        try:
            candidates = await adapter.search_candidates(
                keyword=keyword,
                town=town,
                limit=3
            )
            elapsed = time.time() - start
            success = len(candidates) > 0
            if success:
                total_success += 1
            times.append(elapsed)
            print(f"{idx:2}. {keyword:20} в {town:15} -> {len(candidates):2} кандидатов, время {elapsed:.2f} сек")
        except Exception as e:
            elapsed = time.time() - start
            times.append(elapsed)
            print(f"{idx:2}. {keyword:20} в {town:15} -> ОШИБКА: {e}, время {elapsed:.2f} сек")

    await adapter.close()

    success_rate = (total_success / len(queries)) * 100
    avg_time = statistics.mean(times) if times else 0
    sorted_times = sorted(times)
    p95 = sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) >= 20 else 0

    print("\n" + "="*60)
    print("ИТОГИ:")
    print(f"Успешных запросов (найдено ≥1 кандидата): {total_success} / 50 ({success_rate:.1f}%)")
    print(f"Среднее время ответа: {avg_time:.2f} сек")
    print(f"P95 латентность: {p95:.2f} сек")
    print(f"Целевые показатели: успешность ≥99%, среднее ≤15 сек, P95 ≤25 сек")
    if success_rate >= 99 and avg_time <= 15 and p95 <= 25:
        print(" Все целевые показатели достигнуты")
    else:
        if success_rate < 99:
            print(f" Успешность ниже целевой ({success_rate:.1f}% < 99%)")
        if avg_time > 15:
            print(f" Среднее время выше целевого ({avg_time:.2f} > 15)")
        if p95 > 25:
            print(f" P95 выше целевого ({p95:.2f} > 25)")

if __name__ == "__main__":
    asyncio.run(run_test())