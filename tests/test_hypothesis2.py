import asyncio
import time
import random
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импортируем ваши классы
from yandex_calendar.queue_client import YandexCalendarQueueClient
from yandex_calendar.yandex_calendar_real import YandexCalendarRealClient

# ========== 1. Реальный тест (проверка учётных данных) ==========
async def test_real_calendar():
    print("\n" + "="*60)
    print("ТЕСТ 1: Реальный Яндекс.Календарь")
    print("="*60)
    
    email = os.getenv("YANDEX_CALENDAR_EMAIL")
    app_password = os.getenv("YANDEX_CALENDAR_APP_PASSWORD")
    if not email or not app_password:
        print(" Нет данных для Яндекс.Календаря в .env")
        return False

    print(f"Использую email: {email}")
    print("Проверяем учётные данные...")
    
    # Проверим, что клиент работает
    try:
        real_client = YandexCalendarRealClient(email, app_password)
        # Попробуем создать одно событие (не через очередь, а напрямую)
        start_time = (datetime.now() + timedelta(days=1)).isoformat()
        result = await real_client.create_interview_event(
            candidate_email="test@example.com",
            interviewer_email="hr@test.com",
            start_time=start_time,
            duration_minutes=30,
            title="Тест интеграции",
            description="Проверка",
            location="Онлайн"
        )
        print(f" Событие создано! ID: {result.get('event_id')}")
        await real_client.close()
        return True
    except Exception as e:
        print(f" Ошибка: {e}")
        print("Проверьте правильность email и пароля приложения в .env")
        return False

# ========== 2. Тест отказоустойчивости (с мок-клиентом) ==========
class FlakyMockClient:
    """Мок-клиент, который иногда ошибается (для теста retry)"""
    def __init__(self, fail_probability=0.1):
        self.fail_probability = fail_probability
        self.call_count = 0
        self.fail_count = 0
    
    async def create_interview_event(self, **kwargs):
        self.call_count += 1
        if random.random() < self.fail_probability:
            self.fail_count += 1
            raise Exception(" Имитация сбоя API (таймаут)")
        await asyncio.sleep(0.1)
        return {"event_id": f"mock_{self.call_count}", "status": "created"}
    
    def get_stats(self):
        return {"calls": self.call_count, "failures": self.fail_count}

async def test_fault_tolerance():
    print("\n" + "="*60)
    print("ТЕСТ 2: Отказоустойчивость (имитация 10% сбоев)")
    print("="*60)
    
    # Синхронный подход (без retry)
    print("\n--- Синхронный подход (без retry) ---")
    flaky = FlakyMockClient(fail_probability=0.1)
    sync_results = []
    for i in range(10):
        start = time.time()
        try:
            await flaky.create_interview_event()
            sync_results.append(True)
            print(f"  Запрос {i}:  успех за {time.time()-start:.2f}с")
        except Exception:
            sync_results.append(False)
            print(f"  Запрос {i}:  ошибка за {time.time()-start:.2f}с")
    sync_success = sum(sync_results)
    print(f"Итог: {sync_success}/10 успешно")
    
    # Асинхронный с очередью и retry
    print("\n--- Асинхронный подход (с очередью и retry) ---")
    flaky2 = FlakyMockClient(fail_probability=0.1)
    queue_client = YandexCalendarQueueClient(base_client=flaky2, max_retries=3, retry_delay=1)
    
    async_results = []
    for i in range(10):
        start = time.time()
        try:
            await queue_client.create_interview_event()
            async_results.append(True)
            print(f"  Запрос {i}:  успех за {time.time()-start:.2f}с")
        except Exception:
            async_results.append(False)
            print(f"  Запрос {i}:  ошибка за {time.time()-start:.2f}с")
    async_success = sum(async_results)
    
    print(f"Итог: {async_success}/10 успешно")
    print(f"Статистика мок-клиента: вызовов {flaky2.call_count}, ошибок {flaky2.fail_count}")
    print(f"Количество повторных попыток: {queue_client.metrics['retried']}")
    
    return sync_success, async_success

# ========== 3. Тест времени подтверждения ==========
async def test_ack_time():
    print("\n" + "="*60)
    print("ТЕСТ 3: Время подтверждения пользователю")
    print("="*60)
    
    # Используем мок-клиент без задержек, чтобы измерить только время помещения в очередь
    from yandex_calendar.mock_client import MockYandexCalendarClient
    mock_client = MockYandexCalendarClient()
    queue_client = YandexCalendarQueueClient(base_client=mock_client)
    
    times = []
    for i in range(10):
        start = time.time()
        # Передаём обязательные аргументы (заглушки)
        await queue_client.create_interview_event(
            candidate_email=f"test{i}@example.com",
            interviewer_email="hr@company.ru",
            start_time=(datetime.now() + timedelta(days=1)).isoformat(),
            duration_minutes=30,
            title="Тест"
        )
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"Запрос {i}: подтверждение получено за {elapsed:.4f} сек")
    
    avg_time = sum(times) / len(times)
    print(f"\n Среднее время подтверждения: {avg_time:.4f} сек (цель ≤2 сек)")
    return avg_time

# ========== 4. Запуск ==========
async def main():
    print(" НАЧАЛО ТЕСТИРОВАНИЯ ГИПОТЕЗЫ №2")
    
    # Сначала проверим, работают ли реальные учётные данные
    real_ok = await test_real_calendar()
    if not real_ok:
        print("\n Реальный тест пропущен из-за проблем с аутентификацией.")
        print("Проверьте .env и повторите попытку.")
        return
    
    # Тест отказоустойчивости
    sync_success, async_success = await test_fault_tolerance()
    
    # Тест времени подтверждения
    ack_time = await test_ack_time()
    
    # Вывод итогов
    print("\n" + "="*60)
    print("ИТОГОВЫЕ РЕЗУЛЬТАТЫ ПО ГИПОТЕЗЕ №2")
    print("="*60)
    print(f"Реальный API: успешность 100% (1/1)")
    print(f"Отказоустойчивость: асинхронный подход {async_success}/10 (цель ≥99.5% при 10% сбоях)")
    print(f"   Синхронный подход (без retry): {sync_success}/10")
    print(f"Время подтверждения: {ack_time:.4f} сек (цель ≤2 сек)")

if __name__ == "__main__":
    asyncio.run(main())