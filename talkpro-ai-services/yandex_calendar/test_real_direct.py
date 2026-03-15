import asyncio
from yandex_calendar_real import YandexCalendarRealClient

async def test_direct():
    EMAIL = "umagalova.msh@phystech.edu"
    APP_PASSWORD = "jiwlcfypagqgpplr"

    client = YandexCalendarRealClient(EMAIL, APP_PASSWORD)

    event_data = {
        "candidate_email": "test@example.com",
        "interviewer_email": "hr@company.ru",
        "start_time": "2026-02-22T15:00:00+03:00",
        "duration_minutes": 60,
        "title": "Прямой тест",
        "description": "Тестируем напрямую",
        "location": "Онлайн"
    }

    try:
        result = await client.create_interview_event(**event_data)
        print("Успех!")
        print(result)
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_direct())