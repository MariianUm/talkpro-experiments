import asyncio
import time
import random
from typing import Dict, Any, List
from datetime import datetime
from .yandex_calendar_real import YandexCalendarRealClient
from .mock_client import MockYandexCalendarClient  # добавлен импорт

class YandexCalendarQueueClient:
    def __init__(self, base_client=None, use_real=False, email=None, app_password=None,
                 max_retries: int = 3, retry_delay: int = 2):
        """
        Инициализация клиента с очередью.
        :param base_client: клиент для реальных вызовов (если use_real=False)
        :param use_real: если True, создаёт реальный клиент по email и app_password
        :param email: Яндекс.почта (для реального клиента)
        :param app_password: пароль приложения (для реального клиента)
        :param max_retries: макс. количество повторных попыток
        :param retry_delay: базовая задержка для exponential backoff
        """
        if use_real:
            if not email or not app_password:
                raise ValueError("Для реального API нужны email и пароль приложения")
            self.base_client = YandexCalendarRealClient(email, app_password)
        else:
            self.base_client = base_client or MockYandexCalendarClient()

        self.queue: List[Dict] = []
        self.processing = False
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Метрики для гипотезы
        self.metrics = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "retried": 0,
            "response_times": [],
            "queue_wait_times": []
        }

    async def create_interview_event(self, **kwargs) -> Dict[str, Any]:
        """
        Основной метод - создает событие через очередь.
        Это метод, который будет вызываться из API.
        """
        # Добавляем в очередь и ждем результат
        queue_info = await self.add_to_queue(kwargs)

        # Ждем обработки (polling)
        result = await self._wait_for_processing(queue_info["queue_id"])
        return result

    async def add_to_queue(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Добавление задачи в очередь"""
        queue_id = f"queue_{int(time.time())}_{len(self.queue)}"

        task = {
            "id": queue_id,
            "data": event_data,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "attempts": 0,
            "queue_start_time": time.time()
        }

        self.queue.append(task)

        # Запускаем обработчик если не запущен
        if not self.processing:
            asyncio.create_task(self._process_queue())

        return {
            "queue_id": queue_id,
            "status": "queued",
            "queue_position": len(self.queue),
            "estimated_wait": f"{(len(self.queue) - 1) * 2} секунд"
        }

    async def _process_queue(self):
        """Обработчик очереди"""
        self.processing = True
        while self.queue:
            # Ищем первую задачу со статусом "pending"
            task = None
            for t in self.queue:
                if t["status"] == "pending":
                    task = t
                    break
            if not task:
                # Нет задач для обработки – подождём и проверим снова
                await asyncio.sleep(0.1)
                continue

            try:
                # Обновляем статус
                task["status"] = "processing"
                task["started_at"] = datetime.now().isoformat()
                task["attempts"] += 1

                # Замер времени ожидания в очереди
                queue_wait = time.time() - task["queue_start_time"]
                self.metrics["queue_wait_times"].append(queue_wait)

                # Пробуем выполнить с повторными попытками
                result = await self._execute_with_retry(task["data"])

                # Успех
                task["status"] = "completed"
                task["completed_at"] = datetime.now().isoformat()
                task["result"] = result

                print(f"Задача {task['id']} выполнена (очередь: {queue_wait:.1f}с)")

            except Exception as e:
                # Ошибка
                task["error"] = str(e)

                if task["attempts"] < self.max_retries:
                    # Повторная попытка – сбрасываем статус обратно в pending
                    task["status"] = "pending"
                    print(f"Задача {task['id']} будет повторена (попытка {task['attempts']})")
                else:
                    # Превышено количество попыток
                    task["status"] = "failed"
                    task["failed_at"] = datetime.now().isoformat()
                    print(f"Задача {task['id']} провалена после {self.max_retries} попыток")

            # Небольшая пауза перед следующей итерацией
            await asyncio.sleep(0.1)

        self.processing = False

    async def _execute_with_retry(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение с повторными попытками и exponential backoff"""
        start_time = time.time()

        for attempt in range(self.max_retries):
            try:
                self.metrics["total_requests"] += 1

                result = await self.base_client.create_interview_event(**event_data)

                # Успех
                response_time = time.time() - start_time
                self.metrics["response_times"].append(response_time)
                self.metrics["successful"] += 1

                return result

            except Exception as e:
                if attempt < self.max_retries - 1:
                    # Exponential backoff с jitter
                    delay = self.retry_delay * (2 ** attempt)
                    jitter = random.uniform(0, 0.5)
                    self.metrics["retried"] += 1

                    print(f"Ошибка при выполнении (попытка {attempt+1}/{self.max_retries}): {str(e)}")

                    await asyncio.sleep(delay + jitter)
                else:
                    self.metrics["failed"] += 1
                    print(f"Задача провалена после {self.max_retries} попыток. Последняя ошибка: {str(e)}")
                    raise

    async def _wait_for_processing(self, queue_id: str, timeout: int = 30) -> Dict[str, Any]:
        """Ожидание обработки задачи. Возвращает результат задачи."""
        start = time.time()
        while time.time() - start < timeout:
            # Ищем задачу с заданным id
            task = None
            for t in self.queue:
                if t["id"] == queue_id:
                    task = t
                    break
            if task:
                if task["status"] == "completed":
                    # Удаляем задачу из очереди, чтобы не накапливались
                    self.queue.remove(task)
                    return task["result"]
                elif task["status"] == "failed":
                    self.queue.remove(task)
                    raise Exception(f"Задача не выполнена: {task.get('error', 'Unknown error')}")
                # Иначе всё ещё pending или processing – ждём дальше
            await asyncio.sleep(0.1)
        raise Exception(f"Таймаут ожидания задачи {queue_id}")

    def get_queue_status(self) -> Dict[str, Any]:
        """Статус очереди"""
        return {
            "processing": self.processing,
            "queue_length": len(self.queue),
            "pending": len([t for t in self.queue if t["status"] == "pending"]),
            "tasks": [
                {
                    "id": t["id"][:10],
                    "status": t["status"],
                    "attempts": t["attempts"],
                    "created_at": t["created_at"][11:19]
                }
                for t in self.queue[:5]
            ]
        }

    def get_metrics(self) -> Dict[str, Any]:
        """Метрики для проверки гипотезы"""
        total = self.metrics["total_requests"]
        successful = self.metrics["successful"]

        metrics = {
            "total_requests": total,
            "successful": successful,
            "failed": self.metrics["failed"],
            "retried": self.metrics["retried"],
            "queue_size": len(self.queue)
        }

        # Процент успешных
        if total > 0:
            metrics["success_rate"] = round((successful / total) * 100, 2)
        else:
            metrics["success_rate"] = 0

        # Время ответа
        if self.metrics["response_times"]:
            times = self.metrics["response_times"]
            metrics["avg_response_time"] = round(sum(times) / len(times), 3)
            metrics["p95_response_time"] = round(sorted(times)[int(len(times) * 0.95)], 3) if len(times) >= 20 else metrics["avg_response_time"]

        return metrics

    def get_stats(self):
        """Статистика клиента"""
        base_stats = self.base_client.get_stats()
        base_stats["with_queue"] = True
        return base_stats