# Wildberries → Google Sheets report

Python-скрипт, который читает список кабинетов и токенов из Google Sheet и выгружает продажи Wildberries в целевой Google Sheet (по листу на кабинет).

## Как это работает

- **SOURCE_SHEET_ID**: таблица-источник (в первой строке заголовки; далее строки вида `token, cabinet`)
- **TARGET_SHEET_ID**: таблица-приёмник (создаёт/обновляет листы по названию кабинета)
- **GOOGLE_CREDS_JSON** или **GOOGLE_CREDS_PATH**: доступ к Google Sheets через service account

## Быстрый старт (локально)

1) Установи зависимости:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

2) Создай `.env` по примеру:

- скопируй `.env.example` → `.env`
- заполни значения

3) Запусти:

```bash
python main.py
```

### Параметры запуска (CLI)

По умолчанию скрипт выгружает продажи за последние 14 дней. Можно изменить:

```bash
python main.py --days 7
```

## GitHub Actions

Workflow запускается по расписанию и вручную. Нужны Secrets:

- `SOURCE_SHEET_ID`
- `TARGET_SHEET_ID`
- `GOOGLE_CREDS_JSON` (полный JSON service account)

## Безопасность

- **Никогда не коммить**: `.env`, `creds/`, любые service account JSON, токены WB.
- Репозиторий уже настроен так, что `.env` и `creds/` игнорируются через `.gitignore`.

