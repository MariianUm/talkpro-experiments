import asyncio
import aiohttp
import time
from caldav import DAVClient
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

YANDEX_EMAIL = os.getenv("YANDEX_CALENDAR_EMAIL")
YANDEX_PASSWORD = os.getenv("YANDEX_CALENDAR_APP_PASSWORD")

REQUESTS = 5
REPEAT = 1

async def create_event_sync(email, password, start_time, summary):
    """Синхронный вызов (блокирующий) через caldav"""
    try:
        client = DAVClient(
            url="https://caldav.yandex.ru",
            username=email,
            password=password
        )
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return False
        cal = calendars[0]
        event = cal.save_event(f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TalkPro//Test//RU
BEGIN:VEVENT
SUMMARY:{summary}
DTSTART:{start_time}
DTEND:{(datetime.fromisoformat(start_time) + timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')}
END:VEVENT
END:VCALENDAR""")
        return event is not None
    except:
        return False

async def create_event_async_with_retry(email, password, start_time, summary):
    """Асинхронная имитация (с очередью и retry) - упрощённо, без очереди"""
    for attempt in range(3):
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, create_event_sync, email, password, start_time, summary)
            if result:
                return True
        except:
            pass
        await asyncio.sleep(2 ** attempt)
    return False

async def main():
    print("Проверка работы с Яндекс.Календарём")
    if not YANDEX_EMAIL or not YANDEX_PASSWORD:
        print("Укажите YANDEX_CALENDAR_EMAIL и YANDEX_CALENDAR_APP_PASSWORD в .env")
        return

    # Синхронный подход
    print("Синхронные вызовы (без retry)")
    success_sync = 0
    for i in range(REQUESTS):
        start_time = (datetime.now() + timedelta(days=i+1)).strftime('%Y%m%dT%H%M%S')
        ok = await create_event_sync(YANDEX_EMAIL, YANDEX_PASSWORD, start_time, f"Синхронное событие {i}")
        if ok:
            success_sync += 1
        await asyncio.sleep(1)
    print(f"Успешность синхронного: {success_sync/REQUESTS*100:.1f}%")

    # Асинхронный с retry
    print("Асинхронный с retry")
    success_async = 0
    for i in range(REQUESTS):
        start_time = (datetime.now() + timedelta(days=i+2)).strftime('%Y%m%dT%H%M%S')
        ok = await create_event_async_with_retry(YANDEX_EMAIL, YANDEX_PASSWORD, start_time, f"Асинхронное событие {i}")
        if ok:
            success_async += 1
        await asyncio.sleep(0.5)
    print(f"Успешность асинхронного: {success_async/REQUESTS*100:.1f}% (цель ≥99.5%)")

if __name__ == "__main__":
    asyncio.run(main())