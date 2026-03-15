import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any
import uuid

class MockYandexCalendarClient:
    """Мок-клиент, имитирующий Яндекс.Календарь API"""
    
    def __init__(self, fail_rate: float = 0.1, latency: tuple = (0.5, 2.0)):
        self.events_created = 0
        self.fail_rate = fail_rate
        self.latency = latency
        self.events_db = {}
    
    async def create_interview_event(
        self,
        candidate_email: str,
        interviewer_email: str,
        start_time: str,
        duration_minutes: int = 60,
        title: str = "Собеседование",
        description: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """
        Имитация создания события в Яндекс.Календаре
        """
        # Измеряем время выполнения
        start_time_ms = time.time()
        
        # Имитация сетевой задержки
        delay = random.uniform(*self.latency)
        await asyncio.sleep(delay)
        
        # Имитация случайных ошибок API (для тестирования гипотезы)
        if random.random() < self.fail_rate:
            raise Exception(
                f"Мок: Яндекс.Календарь временно недоступен "
                f"(ошибка 429: Rate Limit Exceeded, задержка: {delay:.2f}с)"
            )
        
        # Парсим время
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            start_dt = datetime.now() + timedelta(days=1)
        
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        
        # Создаем уникальный ID события
        self.events_created += 1
        event_id = f"yandex_mock_{self.events_created:06d}"
        
        # Формируем ответ как у реального API
        event_data = {
            "id": event_id,
            "summary": title,
            "description": description or f"Собеседование с кандидатом {candidate_email}",
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Europe/Moscow"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Europe/Moscow"
            },
            "location": location,
            "attendees": [
                {"email": candidate_email, "displayName": "Кандидат", "responseStatus": "needsAction"},
                {"email": interviewer_email, "displayName": "Интервьюер", "responseStatus": "accepted"}
            ],
            "conferenceData": {
                "entryPoints": [
                    {
                        "entryPointType": "video",
                        "uri": f"https://teams.yandex.ru/join/{event_id[:8]}",
                        "label": "Яндекс.Телемост"
                    }
                ]
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},
                    {"method": "email", "minutes": 1440}
                ]
            },
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "status": "confirmed"
        }
        
        # Сохраняем для возможного получения позже
        self.events_db[event_id] = event_data
        
        response_time = time.time() - start_time_ms
        
        return {
            "status": "created",
            "event_id": event_id,
            "event": event_data,
            "links": {
                "html": f"https://calendar.yandex.ru/event/{event_id}",
                "teams": f"https://teams.yandex.ru/join/{event_id[:8]}"
            },
            "metadata": {
                "response_time": round(response_time, 3),
                "client_type": "yandex_mock",
                "events_created": self.events_created,
                "latency_simulated": round(delay, 3)
            }
        }
    
    async def get_event(self, event_id: str) -> Dict[str, Any]:
        """Получить событие (мок)"""
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if event_id in self.events_db:
            return self.events_db[event_id]
        raise Exception(f"Событие {event_id} не найдено")
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика мок-клиента"""
        return {
            "client_type": "yandex_mock",
            "events_created": self.events_created,
            "events_in_db": len(self.events_db),
            "fail_rate": self.fail_rate,
            "latency_range": self.latency,
            "api_available": False,
            "note": "Реальное API недоступно, используется мок-имитация"
        }