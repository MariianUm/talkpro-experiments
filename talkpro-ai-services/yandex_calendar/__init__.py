import asyncio
import time
import random
from typing import Dict, Any

_singleton_client = None

class YandexCalendarQueueClient:
    """
    ПРОСТАЯ РАБОЧАЯ РЕАЛИЗАЦИЯ с очередью в памяти
    """
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.events_created = 0
        self.processing_tasks = 0
        self.metrics = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "retried": 0,
            "response_times": []
        }
        
        print(f"Яндекс.Календарь: Клиент инициализирован (max_retries={max_retries})")
    
    async def create_interview_event(self, **kwargs) -> Dict[str, Any]:
        task_id = f"task_{int(time.time())}_{random.randint(100, 999)}"
        start_time = time.time()
        
        print(f"🎯 Начало обработки задачи {task_id}")
        self.processing_tasks += 1
        
        try:
            queue_delay = random.uniform(0.05, 0.2)
            await asyncio.sleep(queue_delay)
            
            result = await self._execute_with_retry(kwargs)
            total_time = time.time() - start_time
            
            result["queue_info"] = {
                "task_id": task_id,
                "queue_time": round(queue_delay, 3),
                "total_time": round(total_time, 3),
                "processing_tasks": self.processing_tasks
            }
            
            return result
            
        finally:
            self.processing_tasks -= 1
    
    async def _execute_with_retry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        execution_start = time.time()
        
        for attempt in range(self.max_retries):
            try:
                network_delay = random.uniform(0.3, 1.2)
                await asyncio.sleep(network_delay)
                
                error_chance = 0.2 / (attempt + 1)
                if random.random() < error_chance:
                    raise Exception(f"Мок: Ошибка API 429 (попытка {attempt + 1})")
                
                # Успех
                self.events_created += 1
                
                # Метрики
                execution_time = time.time() - execution_start
                self.metrics["response_times"].append(execution_time)
                self.metrics["success"] += 1
                self.metrics["total"] += 1
                
                return {
                    "status": "created",
                    "event_id": f"yandex_{self.events_created}",
                    "execution_time": round(execution_time, 3),
                    "attempts": attempt + 1,
                    "network_delay": round(network_delay, 3),
                    "data": {
                        "candidate": data.get("candidate_email", ""),
                        "interviewer": data.get("interviewer_email", ""),
                        "time": data.get("start_time", "")
                    }
                }
                
            except Exception as e:
                self.metrics["total"] += 1
                
                if attempt < self.max_retries - 1:
                    delay = 0.8 * (2 ** attempt)
                    self.metrics["retried"] += 1
                    await asyncio.sleep(delay + random.uniform(0, 0.3))
                else:
                    self.metrics["failed"] += 1
                    raise Exception(f"Не удалось после {self.max_retries} попыток: {str(e)}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        return {
            "processing_tasks": self.processing_tasks,
            "implementation": "lightweight_queue",
            "max_retries": self.max_retries,
            "metrics_snapshot": {
                "total_requests": self.metrics["total"],
                "events_created": self.events_created
            }
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        times = self.metrics["response_times"]
        
        result = {
            "total_requests": self.metrics["total"],
            "successful": self.metrics["success"],
            "failed": self.metrics["failed"],
            "retried": self.metrics["retried"],
            "success_rate": round((self.metrics["success"] / self.metrics["total"]) * 100, 2) if self.metrics["total"] > 0 else 0,
            "events_created": self.events_created,
            "active_tasks": self.processing_tasks
        }
        
        if times:
            result["avg_response_time"] = round(sum(times) / len(times), 3)
            result["min_response_time"] = round(min(times), 3)
            result["max_response_time"] = round(max(times), 3)
            
            # P95
            if len(times) >= 5:
                sorted_times = sorted(times)
                p95_index = int(len(sorted_times) * 0.95)
                result["p95_response_time"] = round(sorted_times[p95_index], 3)
            else:
                result["p95_response_time"] = result["avg_response_time"]
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Общая статистика"""
        return {
            "client_type": "yandex_queue_mock_simple",
            "with_queue": True,
            "max_retries": self.max_retries,
            **self.get_metrics()
        }

def get_yandex_calendar_client(use_queue: bool = True):
    """
    Возвращает один и тот же экземпляр клиента (синглтон)
    """
    global _singleton_client
    
    if _singleton_client is None:
        _singleton_client = YandexCalendarQueueClient(max_retries=3)
        print("Яндекс.Календарь: Создан новый клиент (синглтон)")
    else:
        print("Яндекс.Календарь: Используется существующий клиент")
    
    return _singleton_client