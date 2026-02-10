import ssl
import os
import base64
import uuid
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

class YandexCalendarRealClient:
    def __init__(self, email: str, app_password: str):
        self.email = email
        self.app_password = app_password
        self.base_url = f"https://caldav.yandex.ru/calendars/{email}"
        self.events_created = 0
        self._auth_header = self._make_auth_header()
        self.session: Optional[aiohttp.ClientSession] = None

    def _make_auth_header(self) -> str:
        """Формирует Basic Auth заголовок"""
        auth_str = f"{self.email}:{self.app_password}"
        auth_bytes = auth_str.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        return f"Basic {auth_b64}"

    def _generate_uid(self) -> str:
        """Генерирует уникальный идентификатор для события"""
        return f"talkpro-{uuid.uuid4()}@yandex.ru"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Создаёт или возвращает существующую сессию"""
        if self.session is None or self.session.closed:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(
                connector=connector,
                headers={
                    "Authorization": self._auth_header,
                    "User-Agent": "TalkPro/1.0"
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session

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
        start_ms = asyncio.get_event_loop().time()
        uid = self._generate_uid()

        # Парсим время
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            start_dt = datetime.now() + timedelta(days=1)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # Форматируем время для iCalendar (UTC)
        dt_format = "%Y%m%dT%H%M%SZ"
        start_utc = start_dt.astimezone(timezone.utc).strftime(dt_format)
        end_utc = end_dt.astimezone(timezone.utc).strftime(dt_format)

        # Собираем iCalendar данные
        ical_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TalkPro//Yandex Calendar Integration//RU
BEGIN:VEVENT
UID:{uid}
DTSTART:{start_utc}
DTEND:{end_utc}
SUMMARY:{title}
DESCRIPTION:{description or f"Собеседование с кандидатом {candidate_email}"}
LOCATION:{location}
ATTENDEE;CN=Candidate;ROLE=REQ-PARTICIPANT:mailto:{candidate_email}
ATTENDEE;CN=Interviewer;ROLE=REQ-PARTICIPANT:mailto:{interviewer_email}
END:VEVENT
END:VCALENDAR"""

        # URL для события
        event_url = f"{self.base_url}/events-default/{uid}.ics"

        session = await self._get_session()
        try:
            async with session.put(event_url, data=ical_data.encode('utf-8')) as resp:
                response_time = asyncio.get_event_loop().time() - start_ms

                if resp.status in (201, 204):
                    self.events_created += 1
                    event_id = uid.split('@')[0]
                    html_link = f"https://calendar.yandex.ru/event?uid={uid}"

                    return {
                        "status": "created",
                        "event_id": event_id,
                        "event": {
                            "id": event_id,
                            "summary": title,
                            "description": description,
                            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Moscow"},
                            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Moscow"},
                            "location": location,
                            "attendees": [
                                {"email": candidate_email, "displayName": "Кандидат", "responseStatus": "needsAction"},
                                {"email": interviewer_email, "displayName": "Интервьюер", "responseStatus": "accepted"}
                            ],
                            "status": "confirmed"
                        },
                        "links": {
                            "html": html_link,
                            "teams": ""  # Яндекс.Телемост не создаётся автоматически
                        },
                        "metadata": {
                            "response_time": round(response_time, 3),
                            "client_type": "yandex_real",
                            "events_created": self.events_created,
                            "api_response_status": resp.status
                        }
                    }
                else:
                    error_text = await resp.text()
                    raise Exception(f"Yandex Calendar API error {resp.status}: {error_text}")

        except aiohttp.ClientError as e:
            raise Exception(f"Network error during Yandex Calendar request: {str(e)}")

    async def get_event(self, event_id: str) -> Dict[str, Any]:
        """Заглушка"""
        raise NotImplementedError("Метод get_event для реального API пока не реализован")

    async def close(self):
        """Закрыть сессию"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def get_stats(self) -> Dict[str, Any]:
        """Статистика клиента"""
        return {
            "client_type": "yandex_real",
            "events_created": self.events_created,
            "authenticated": bool(self.email and self.app_password),
            "note": "Используется реальный CalDAV API Яндекса"
        }