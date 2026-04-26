# Документация по развёртыванию и внесению изменений в проект TalkPro

**Версия:** 1.0  
**Дата:** май 2026  
**Автор:** Умагалова Мариян (fullstack разработчик, DevOps)

## 1. Структура проекта на сервере
/opt/talkpro/talkpro_backend/
├── docker-compose.yml
├── .env
├── Dockerfile.ai
├── frontend-backend/
│ ├── backend/
│ └── frontend/
└── talkpro-ai-services/


## 2. Требования к серверу

- **ОС:** Ubuntu 22.04 / 24.04
- **Docker** 20.10+ и **Docker Compose** 2.x
- **Порты:** 80 (фронтенд), 3001 (Node.js), 8000 (Python)

## 3. Переменные окружения (файл `.env`)

Перед запуском необходимо создать файл `.env` в корне проекта со следующими переменными:

```ini
GIGACHAT_API_KEY=your_gigachat_key_here
SUPERJOB_SECRET_KEY=your_superjob_key_here
YANDEX_CALENDAR_EMAIL=your_email@example.com
YANDEX_CALENDAR_APP_PASSWORD=your_app_password_here
USE_REAL_YANDEX_CALENDAR=false

## 4. Первоначальное развертывание

ssh root@130.49.151.46
apt update && apt install -y docker.io docker-compose
cd /opt/talkpro/talkpro_backend
docker-compose up -d --build

## 5. Внесение изменений 

- Скопировать новые файлы на сервер (через scp, rsync или nano).
- Подключиться по SSH:

ssh root@130.49.151.46

- Перейти в папку проекта:

cd /opt/talkpro/talkpro_backend

- Пересобрать нужные контейнеры:

Только фронтенд:
docker-compose up -d --build frontend
Только бэкенд (Node.js):
docker-compose up -d --build app-backend
Только AI‑сервис:
docker-compose up -d --build ai-service
Все сразу:
docker-compose up -d --build

- Проверить логи:

docker-compose logs --tail=50

## 6. Мониторинг и диагностика:

Статус контейнеров: docker-compose ps
Логи определённого сервиса: docker-compose logs <service>
(где <service> = frontend | app-backend | ai-service)
Живой поток логов: docker-compose logs -f
Перезапуск контейнера без сборки: docker-compose restart <service>

## 7. Возможные проблемы и решения

| Проблема | Возможная причина | Решение |
|----------|------------------|---------|
| Ошибка 500 при анализе резюме | Неверный GIGACHAT_API_KEY | Проверить `.env`, перезапустить `ai-service` |
| Контакты SuperJob не приходят | Тестовый тариф только для города «Совхоз имени Ленина» | Использовать `town=Совхоз имени Ленина` (ID=2660) или купить тариф |
| Фронтенд не обновляется | Кэш браузера | Очистить кэш (Ctrl+Shift+R) или открыть в инкогнито |
| Docker не может скачать образ | Проблемы с доступом к Docker Hub | Настроить зеркало в `/etc/docker/daemon.json`: `{"registry-mirrors": ["https://mirror.timeweb.com"]}` |

## 8. Дополнительные рекомендации

- Все важные данные (db.json, загруженные файлы) монтируются через volumes, поэтому они сохраняются при пересборке.
- Перед обновлением production-сервера рекомендуется протестировать изменения на локальном стенде.


