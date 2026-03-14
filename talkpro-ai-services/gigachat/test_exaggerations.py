import asyncio
import os
import json
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь, чтобы импортировать gateway
sys.path.append(str(Path(__file__).parent))

from gateway import GigaChatGateway

async def test_exaggerations():
    # Загружаем ключ из .env (корень проекта)
    env_path = Path(__file__).parent.parent.parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
    print(f"PATH: {env_path}")
    print(f"KEY: {os.getenv('GIGACHAT_API_KEY')}")
    api_key = os.getenv("GIGACHAT_API_KEY")
    if not api_key or api_key == "test_key":
        print("Не задан реальный GIGACHAT_API_KEY в .env")
        return

    # Текст резюме с подозрительным местом (опыт 9 месяцев и руководство отделом)
    resume_text = """
    Кандидат: Иванов Иван Иванович
    Возраст: 22 года
    Образование: Московский государственный университет, бакалавр прикладной математики, 2025 год выпуска.

    Опыт работы:
    1. Компания "ТехноСофт", июнь 2024 – февраль 2025 (8 месяцев)
    Должность: Директор по развитию
    Обязанности:
    - Стратегическое планирование развития компании
    - Управление командой из 50 сотрудников
    - Проведение сделок M&A на сумму $10 млн
    - Разработка корпоративной стратегии до 2030 года

    2. Компания "Стартап.ру", январь 2024 – май 2024 (4 месяца)
    Должность: Стажёр-аналитик
    Обязанности:
    - Сбор и обработка данных
    - Подготовка отчётов
    - Помощь старшим коллегам

    Навыки:
    - Стратегический менеджмент (эксперт)
    - Управление персоналом
    - Проведение переговоров с топ-менеджментом
    - MS Office (базовый)
    """

    # Создаём шлюз
    gateway = GigaChatGateway(
        api_key=api_key,
        max_rps=1,
        batch_window=0.1,
        max_batch_size=5
    )

    print("Анализируем резюме...")
    result = await gateway.analyze(
        prompt_key="find_exaggerations",
        text=resume_text
    )

    if result is None:
        print("Не удалось получить ответ от GigaChat")
        await gateway.close()
        return

    # Печатаем сырой ответ
    print("\nСырой ответ от GigaChat:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Извлекаем содержимое
    try:
        content = result["choices"][0]["message"]["content"]
        print("\nСодержимое ответа:")
        print(content)

        # Ищем JSON-массив в ответе (между ```json и ```)
        json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Если нет маркеров кода, ищем первый [ и последний ]
            start = content.find('[')
            end = content.rfind(']') + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = "[]"
        
        if json_str and json_str != "[]":
            exaggerations = json.loads(json_str)
            print("\nНайденные преувеличения:")
            if exaggerations:
                for i, item in enumerate(exaggerations, 1):
                    print(f"{i}. Фрагмент: {item.get('fragment')}")
                    print(f"   Проблема: {item.get('issue')}")
                    print(f"   Уверенность: {item.get('confidence')}%")
            else:
                print("Преувеличений не обнаружено.")
        else:
            print("Преувеличений не обнаружено.")
    except Exception as e:
        print(f"Ошибка при разборе ответа: {e}")

    await gateway.close()

if __name__ == "__main__":
    asyncio.run(test_exaggerations())