# Restometra

Restometra — русскоязычная панель аналитики ресторанного обслуживания. Отчёты за период собираются из сохранённых дневных результатов. Демонстрационные события воспроизводятся на фиксированных датах.

## Локальный запуск

Понадобятся Python 3.12, Node.js 22.12+ и Docker Compose. Команды ниже рассчитаны на PowerShell и выполняются из корня репозитория.

```powershell
docker compose up -d --wait
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
Set-Location backend
..\.venv\Scripts\python.exe -m app.demo
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

В отдельном терминале, из корня репозитория, запустите фоновый процесс.

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.worker
```

В третьем терминале, из корня репозитория, запустите интерфейс.

```powershell
Set-Location frontend
npm ci
npm run dev
```

Панель доступна по адресу [127.0.0.1:5173](http://127.0.0.1:5173), документация REST API — по адресу [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). PostgreSQL 16 доступна на локальном порту 55432. При использовании своей БД укажите переменную окружения `DATABASE_URL` со схемой `postgresql+psycopg://` в каждом терминале backend.

В Linux и macOS используйте `python3.12 -m venv .venv` и `.venv/bin/python` или `../.venv/bin/python` вместо путей к интерпретатору Windows.

## Демоданные и обработка

- `python -m app.demo --end-date 2026-01-31` в каталоге `backend` создаёт воспроизводимую выборку с указанной конечной датой в чистой БД. Без флага используется позавчера по Красноярску. Повторный запуск использует уже загруженную выборку. Для другой исходной даты используйте чистую БД.
- При загрузке демонстрационной выборки обработчик по умолчанию сразу рассчитывает готовые даты. Флаг `--no-process` позволяет отложить расчёт до запуска фонового процесса.
- `python -m app.worker --once` однократно догоняет готовые даты. Команда `python -m app.worker --restaurant 1 --date 2026-01-09` явно пересчитывает заданную дату после наступления срока обработки.
- Кнопка на странице «Отчёт за день» ставит дату в очередь. Для выполнения очереди должен быть запущен фоновый процесс.

## Проверки

Создайте пустую тестовую базу в локальном контейнере один раз. Интеграционные тесты создают собственные временные схемы и применяют миграции внутри каждой.

```powershell
docker compose exec -T postgres psql -U restometra -d postgres -c 'CREATE DATABASE restometra_test'
$env:TEST_DATABASE_URL = 'postgresql+psycopg://restometra:restometra@127.0.0.1:55432/restometra_test'
Set-Location backend
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m pytest -q
```

В каталоге `frontend` выполните `npm ci`, `npm run lint`, `npm run typecheck`, `npm test` и `npm run build`. CI запускает проверки для PR и push в `develop` и `main`.

[Архитектура и правила операционного дня](docs/architecture.md)
