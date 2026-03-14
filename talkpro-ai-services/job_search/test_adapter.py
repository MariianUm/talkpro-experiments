import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from job_adapter import JobSearchAdapter

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

async def main():
    secret_key = os.getenv("SUPERJOB_SECRET_KEY")
    if not secret_key:
        raise ValueError("Нет SUPERJOB_SECRET_KEY")

    adapter = JobSearchAdapter(secret_key)

    # Поиск Python-разработчиков в Москве с опытом от 3 лет
    candidates = await adapter.search_candidates(
        keyword="Python разработчик",
        town="Москва",
        limit=5,
        experience_years=3
    )

    print(f"Найдено кандидатов: {len(candidates)}\n")
    for i, cand in enumerate(candidates, 1):
        print(f"{i}. {cand['title']}")
        print(f"   Зарплата: {cand['salary_from']}-{cand['salary_to']} {cand['currency']}")
        print(f"   Опыт: {cand['experience']}")
        print(f"   Город: {cand['city']}")
        print(f"   Ссылка: {cand['url']}\n")

    await adapter.close()

if __name__ == "__main__":
    asyncio.run(main())