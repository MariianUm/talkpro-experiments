import asyncio
import random
from typing import List, Dict, Any
import time

class JobSearchAdapter:
    """
    Минимальный адаптер для поиска кандидатов
    """
    
    def __init__(self):
        self.searches_performed = 0
        self.candidates_found = 0
    
    async def search_candidates(
        self, 
        skills: List[str], 
        min_experience: int = 0,
        location: str = "Москва",
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Поиск кандидатов (мок)
        """
        self.searches_performed += 1
        
        # Имитация поиска
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Генерируем тестовых кандидатов
        num_candidates = random.randint(3, 10)
        candidates = []
        
        for i in range(num_candidates):
            candidates.append({
                "id": f"candidate_{i+1}",
                "name": f"Кандидат {i+1}",
                "skills": skills if skills else ["Python", "Django"],
                "experience": min_experience + random.randint(0, 3),
                "location": location,
                "salary": random.randint(100000, 250000),
                "source": random.choice(["hh.ru", "superjob.ru"])
            })
        
        self.candidates_found += len(candidates)
        
        return {
            "search_id": f"search_{self.searches_performed}",
            "query": {
                "skills": skills,
                "min_experience": min_experience,
                "location": location,
                "limit": limit
            },
            "results": {
                "total_found": len(candidates),
                "returned": min(len(candidates), limit),
                "candidates": candidates[:limit],
                "search_time": random.uniform(0.5, 2.0)
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика поиска"""
        return {
            "searches_performed": self.searches_performed,
            "total_candidates_found": self.candidates_found,
            "adapter_type": "job_search_mock_simple"
        }


# Фабрика (синглтон)
_singleton_adapter = None

def get_job_search_adapter():
    """Возвращает адаптер для поиска"""
    global _singleton_adapter
    
    if _singleton_adapter is None:
        _singleton_adapter = JobSearchAdapter()
        print("JobSearch: Создан адаптер для поиска кандидатов")
    
    return _singleton_adapter