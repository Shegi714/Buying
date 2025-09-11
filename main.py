import os
import time
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime, timedelta

# 🧪 Глобальные переменные окружения (GitHub Secrets)
SOURCE_SHEET_ID = os.environ.get("SOURCE_SHEET_ID")
TARGET_SHEET_ID = os.environ.get("TARGET_SHEET_ID")

# ⚙️ Подключение к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_json = os.environ.get("GOOGLE_CREDS_JSON")
if not creds_json:
    raise ValueError("GOOGLE_CREDS_JSON not set or empty!")

creds_dict = json.loads(creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 📑 Чтение токенов и кабинетов
source_sheet = client.open_by_key(SOURCE_SHEET_ID).sheet1
rows = source_sheet.get_all_values()[1:]
data = [{"token": row[0], "cabinet": row[1]} for row in rows if len(row) >= 2 and row[0].strip()]

# 📡 Функция выгрузки продаж за последние N дней
def fetch_sales(token, days=14):
    url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"
    headers = {
        "accept": "application/json",
        "Authorization": token,  # ⚠️ просто токен, без Bearer
        "User-Agent": "Mozilla/5.0"
    }

    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    all_sales = []
    next_date_from = date_from

    while True:
        print(f"📡 Запрос продаж с {next_date_from} ...")
        params = {"dateFrom": next_date_from}
        response = requests.get(url, headers=headers, params=params, timeout=60)

        if response.status_code == 401:
            print("❌ Неверный токен или нет доступа (401 Unauthorized).")
            break
        if response.status_code != 200:
            print(f"⚠️ Ошибка {response.status_code}: {response.text}")
            break

        sales = response.json()
        if not sales:
            print("✅ Данные закончились, все продажи собраны.")
            break

        all_sales.extend(sales)
        print(f"📦 Получено продаж: {len(sales)}, всего собрано: {len(all_sales)}")

        # Готовим дату для следующего запроса
        next_date_from = sales[-1]["lastChangeDate"]

        # Лимит 1 запрос/мин
        print("⏳ Ждём 60 секунд...")
        time.sleep(60)

    return all_sales


# 📊 Запись продаж в Google Sheets
def write_sales_to_sheet(sheet_obj, cabinet_name, sales):
    try:
        # Создаём или очищаем лист
        try:
            worksheet = sheet_obj.worksheet(cabinet_name)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet_obj.add_worksheet(title=cabinet_name, rows="1000", cols="25")

        if not sales:
            worksheet.update([["Нет данных за выбранный период"]])
            print(f"⚠️ Данных для '{cabinet_name}' нет.")
            return

        # Заголовки в том порядке, как они пришли
        headers = list(sales[0].keys())
        rows = [headers]

        for sale in sales:
            row = [
                clean_barcode(sale.get(h, "")) if h == "barcode" else sale.get(h, "")
                for h in headers
            ]
            rows.append(row)

        worksheet.update(rows)
        print(f"✅ Сохранено {len(sales)} продаж в лист '{cabinet_name}'")

    except Exception as e:
        print(f"🛑 Ошибка при записи в лист '{cabinet_name}': {e}")


# 🚀 Главная функция
def main():
    target_sheet = client.open_by_key(TARGET_SHEET_ID)

    for entry in data:
        cabinet = entry["cabinet"]
        token = entry["token"]
        print(f"\n🔄 Работаем с кабинетом: {cabinet}")

        sales = fetch_sales(token, days=14)
        write_sales_to_sheet(target_sheet, cabinet, sales)


if __name__ == "__main__":
    main()
