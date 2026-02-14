import asyncio
import logging
from typing import Dict, Any, List, Optional

from .superjob_client import SuperJobClient

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JobSearchAdapter:
    def __init__(self, superjob_secret_key: str):
        """
        :param superjob_secret_key: Секретный ключ для SuperJob API
        """
        self.sj_client = SuperJobClient(superjob_secret_key)
        self._search_cache = {}
        self._contacts_limit = 100
        self._contacts_used = 0

    async def search_candidates(
        self,
        keyword: str,
        town: str = "Москва",
        limit: int = 20,
        page: int = 0,
        min_salary: int | None = None,
        experience_years: int | None = None,
        include_contacts: bool = False
    ) -> Dict[str, Any]:
        cache_key = f"{keyword}_{town}_{limit}_{page}_{min_salary}_{experience_years}_{include_contacts}"
        if cache_key in self._search_cache:
            logger.info(f"Возвращаем кешированный результат для {keyword}")
            return self._search_cache[cache_key]

        exp_id = self._experience_to_id(experience_years) if experience_years else None
        response = await self.sj_client.search_resumes(
            keyword=keyword,
            town=town,
            count=limit,
            page=page,
            payment_from=min_salary,
            experience=exp_id
        )
        resumes = response.get("objects", [])
        more = response.get("more", False)

        normalized = [self._normalize_sj_resume(r) for r in resumes]
        if include_contacts:
            for idx, r in enumerate(resumes):
                if self._contacts_used < self._contacts_limit:
                    contacts = await self.sj_client.get_resume_contacts(r["id"])
                    if contacts:
                        normalized[idx]["contacts"] = contacts
                        self._contacts_used += 1

        result = {"candidates": normalized, "more": more}
        self._search_cache[cache_key] = result
        asyncio.create_task(self._invalidate_cache_after(cache_key, 300))
        return result

    def _normalize_sj_resume(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        profession = raw.get("profession", "")
        payment = raw.get("payment")
        payment_from = raw.get("payment_from") or payment
        payment_to = raw.get("payment_to") or payment
        currency = raw.get("currency", "rub")

        exp_obj = raw.get("experience", {})
        exp_title = exp_obj.get("title") if isinstance(exp_obj, dict) else None

        edu_obj = raw.get("education", {})
        edu_title = edu_obj.get("title") if isinstance(edu_obj, dict) else None

        town_obj = raw.get("town", {})
        town_title = town_obj.get("title") if isinstance(town_obj, dict) else None

        contacts = {}
        if raw.get("contact"):
            contacts["name"] = raw["contact"]
        if raw.get("phone"):
            contacts["phone"] = raw["phone"]
        if raw.get("email"):
            contacts["email"] = raw["email"]

        return {
            "platform": "superjob",
            "id": raw.get("id"),
            "title": profession,
            "salary_from": payment_from,
            "salary_to": payment_to,
            "currency": currency,
            "experience": exp_title,
            "education": edu_title,
            "age": raw.get("age"),
            "gender": raw.get("gender", {}).get("title") if raw.get("gender") else None,
            "city": town_title,
            "skills": None,
            "contacts": contacts,
            "url": raw.get("link"),
            "raw": raw
        }

    def _experience_to_id(self, years: int) -> Optional[int]:
        if years < 1:
            return 1
        elif years < 3:
            return 2
        elif years < 6:
            return 3
        else:
            return 4

    async def _invalidate_cache_after(self, key: str, seconds: int):
        await asyncio.sleep(seconds)
        if key in self._search_cache:
            del self._search_cache[key]
            logger.debug(f"Кеш {key} очищен")

    async def close(self):
        await self.sj_client.close()