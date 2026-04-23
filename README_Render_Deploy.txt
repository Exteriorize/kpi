# Деплой KPI Dashboard на Render

## Что выбрать в Render
Нужен тип сервиса: **Web Service**.

Render требует, чтобы приложение слушало HTTP-порт, а команды сборки и запуска задаются в настройках сервиса.
Для Streamlit обычно используется запуск через:
`streamlit run app_kpi_history.py --server.port $PORT --server.address 0.0.0.0`

## Вариант 1 — через render.yaml
1. Загрузи все файлы проекта в GitHub-репозиторий
2. Убедись, что в корне лежит файл `render.yaml`
3. В Render нажми **New +**
4. Выбери **Blueprint**
5. Подключи GitHub-репозиторий
6. Render сам подхватит настройки из `render.yaml`

## Вариант 2 — вручную в Render
Если не хочешь через Blueprint, создай **Web Service** и укажи:

### Build Command
`pip install -r requirements_kpi_dashboard_v2.txt`

### Start Command
`streamlit run app_kpi_history.py --server.port $PORT --server.address 0.0.0.0`

## Какие файлы должны быть в репозитории
- `app_kpi_history.py`
- `requirements_kpi_dashboard_v2.txt`
- `render.yaml`

## Важно про данные
Сейчас приложение хранит историю в локальном файле `kpi_dashboard.db`.
На Render файловая система не подходит для надежного долгого хранения после новых деплоев или перезапуска контейнера.
Поэтому для теста это нормально, но для постоянной работы лучше потом перенести историю в:
- Render Disk
- PostgreSQL
- Supabase
- SQLite на persistent disk

## Если хочешь просто протестировать
Можно задеплоить в текущем виде и каждый день загружать файл.
Но для стабильной боевой версии лучше сделать persistent storage.

## Локальная проверка
Перед загрузкой в Render можно проверить так:
`streamlit run app_kpi_history.py --server.port 8501 --server.address 0.0.0.0`
