import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from superjob_client import SuperJobClient

env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

async def main():
    SECRET_KEY = os.getenv("SUPERJOB_SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SUPERJOB_SECRET_KEY не найден в .env. Создайте файл .env и добавьте туда ключ.")
    
    client = SuperJobClient(SECRET_KEY)
    
    resumes = await client.search_resumes(
        keyword="Python разработчик",
        town="Москва",
        count=5,
        experience=3,
        payment_from=150000
    )
    
    print(f"Найдено резюме: {len(resumes)}")
    for i, res in enumerate(resumes, 1):
        print(f"\n--- Резюме {i} ---")
        print(f"Должность: {res.get('profession')}")
        print(f"Зарплата: {res.get('payment_from')}-{res.get('payment_to')} {res.get('currency')}")
        print(f"Опыт: {res.get('experience', {}).get('title')}")
        print(f"Город: {res.get('town', {}).get('title')}")
        print(f"Ссылка: {res.get('link')}")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())