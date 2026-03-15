import asyncio
import time
from queue_client import YandexCalendarQueueClient
from yandex_calendar_real import YandexCalendarRealClient

async def test_real_queue():
    
    EMAIL = "umagalova.msh@phystech.edu"
    APP_PASSWORD = "jiwlcfypagqgpplr" 

    real_client = YandexCalendarRealClient(EMAIL, APP_PASSWORD)

    # 2. Создаём очередь-клиент, передавая реальный клиент как base_client
    queue_client = YandexCalendarQueueClient(
        base_client=real_client,
        max_retries=3,
        retry_delay=2
    )

    # 3. Параметры события
    event_data = {
        "candidate_email": "candidate@example.com",
        "interviewer_email": "interviewer@company.ru",
        "start_time": "2026-02-20T15:00:00+03:00",
        "duration_minutes": 60,
        "title": "Тестовое собеседование (очередь)",
        "description": "Создано через очередь",
        "location": "Яндекс.Телемост"
    }

    print("Отправляем задачу в очередь...")
    start = time.time()

    # 4. Вызываем метод создания (он сам положит в очередь и дождётся выполнения)
    try:
        result = await queue_client.create_interview_event(**event_data)
        total_time = time.time() - start

        print("\nСобытие успешно создано!")
        print(f"   Event ID: {result['event_id']}")
        print(f"   Ссылка: {result['links']['html']}")
        print(f"   Общее время: {total_time:.2f} сек")
        print(f"   Время подтверждения (в очереди): {result['metadata']['response_time']} сек")

        # 5. Статистика очереди
        print("\nСтатистика очереди:")
        stats = queue_client.get_queue_status()
        print(f"   Очередь: {stats['queue_length']} задач")
        print(f"   Успешно: {queue_client.get_metrics()['successful']}")
        print(f"   Повторов: {queue_client.get_metrics()['retried']}")

    except Exception as e:
        print(f"Ошибка: {e}")

    finally:
        await real_client.close()

if __name__ == "__main__":
    asyncio.run(test_real_queue())


async def test_sync():
    real_client = YandexCalendarRealClient(EMAIL, APP_PASSWORD)
    start = time.time()
    try:
        result = await real_client.create_interview_event(**event_data)
        sync_time = time.time() - start
        print(f"Синхронное время: {sync_time:.2f} сек")
    finally:
        await real_client.close()