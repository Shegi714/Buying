import os
import time
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import argparse

load_dotenv()

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def get_env(name: str, *, required: bool = False) -> str | None:
    value = os.environ.get(name)
    if required and (value is None or not value.strip()):
        raise ValueError(f"{name} is not set or empty.")
    return value


def load_google_creds_json() -> str:
    creds_json = get_env("GOOGLE_CREDS_JSON")
    if creds_json and creds_json.strip():
        return creds_json

    creds_path = get_env("GOOGLE_CREDS_PATH")
    if creds_path and creds_path.strip():
        try:
            with open(creds_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            raise ValueError(f"Failed to read GOOGLE_CREDS_PATH file: {e}") from e

    raise ValueError("Set GOOGLE_CREDS_JSON or GOOGLE_CREDS_PATH.")


def create_gspread_client() -> gspread.Client:
    creds_dict = json.loads(load_google_creds_json())
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    return gspread.authorize(creds)


def read_cabinets_and_tokens(client: gspread.Client, source_sheet_id: str) -> list[dict[str, str]]:
    source_sheet = client.open_by_key(source_sheet_id).sheet1
    rows = source_sheet.get_all_values()[1:]
    return [
        {"token": row[0], "cabinet": row[1]}
        for row in rows
        if len(row) >= 2 and row[0].strip() and row[1].strip()
    ]

# 🔧 Очистка barcode от апострофа и принудительная запись как числа при необходимости
def clean_barcode(value):
    if isinstance(value, str):
        if value.startswith("'"):
            value = value[1:]
        if value.isdigit():
            try:
                return int(value)  # сохранится как число, без апострофа
            except Exception:
                return value
    return value

# 📡 Функция выгрузки продаж за последние N дней
def fetch_sales(token, days=14):
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"
    headers = {
        "accept": "application/json",
        "Authorization": token,  # просто токен, без Bearer
        "User-Agent": "Mozilla/5.0"
    }

    # Если TZ не укажем, WB трактует как МСК (UTC+3) — это ок.
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    all_sales = []
    next_date_from = date_from
    page = 1

    while True:
        print(f"📡 [{page}] Запрос продаж с dateFrom={next_date_from} ...")
        params = {"dateFrom": next_date_from}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
        except Exception as e:
            print(f"❌ Ошибка сети: {e}")
            break

        if response.status_code == 401:
            print("❌ Неверный токен или нет доступа (401 Unauthorized).")
            break
        if response.status_code != 200:
            body = response.text[:500]
            print(f"⚠️ Ошибка {response.status_code}: {body}")
            break

        try:
            sales = response.json()
        except Exception as e:
            print(f"❌ Не удалось распарсить JSON: {e}; фрагмент: {response.text[:500]}")
            break

        if not isinstance(sales, list):
            print(f"⚠️ Ожидали массив, получили {type(sales)}; фрагмент: {str(sales)[:300]}")
            break

        if not sales:
            print("✅ Данные закончились, все продажи собраны.")
            break

        all_sales.extend(sales)
        print(f"📦 Получено записей: {len(sales)}, всего собрано: {len(all_sales)}")

        # Готовим dateFrom для следующего запроса
        try:
            next_date_from = sales[-1]["lastChangeDate"]
        except Exception:
            print("⚠️ В последней записи нет lastChangeDate — остановка пагинации.")
            break

        page += 1
        # Лимит 1 запрос/мин
        print("⏳ Пауза 60 секунд (лимит API)...")
        time.sleep(60)

    return all_sales

# 📊 Запись продаж в Google Sheets
def write_sales_to_sheet(sheet_obj, cabinet_name, sales):
    try:
        # Создаём лист, если его нет
        try:
            worksheet = sheet_obj.worksheet(cabinet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet_obj.add_worksheet(title=cabinet_name, rows="1000", cols="25")

        if not sales:
            # Не затираем старые данные пустым результатом: просто сообщим.
            print(f"⚠️ Данных для '{cabinet_name}' нет. Лист не изменён.")
            return

        # Заголовки в том порядке, как они пришли
        headers = list(sales[0].keys())

        # Формируем все строки в памяти
        rows = [headers]
        for sale in sales:
            row = []
            for h in headers:
                v = sale.get(h, "")
                if h == "barcode":
                    v = clean_barcode(v)
                row.append(v)
            rows.append(row)

        # Теперь, когда всё готово, очищаем и записываем
        worksheet.clear()
        worksheet.update(rows)
        print(f"✅ Сохранено {len(sales)} записей в лист '{cabinet_name}'")

    except Exception as e:
        print(f"🛑 Ошибка при записи в лист '{cabinet_name}': {e}")

# 🚀 Главная функция
def main():
    parser = argparse.ArgumentParser(description="Wildberries to Google Sheets report")
    parser.add_argument("--days", type=int, default=14, help="How many days back to fetch sales (default: 14)")
    args = parser.parse_args()

    source_sheet_id = get_env("SOURCE_SHEET_ID", required=True)
    target_sheet_id = get_env("TARGET_SHEET_ID", required=True)

    client = create_gspread_client()
    data = read_cabinets_and_tokens(client, source_sheet_id)
    if not data:
        print("⚠️ В таблице-источнике нет валидных строк (token + cabinet).")
        return

    target_sheet = client.open_by_key(target_sheet_id)
    for entry in data:
        cabinet = entry["cabinet"]
        token = entry["token"]
        print(f"\n🔄 Работаем с кабинетом: {cabinet}")

        sales = fetch_sales(token, days=args.days)
        write_sales_to_sheet(target_sheet, cabinet, sales)

if __name__ == "__main__":
    main()
