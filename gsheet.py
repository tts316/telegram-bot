import os
import json
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_NAME = os.getenv("GSHEET_NAME", "tracking_data")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")


def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS_FILE,
        scope
    )

    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet


def ensure_header():
    sheet = get_sheet()
    values = sheet.get_all_values()

    expected_header = ["campaign_id", "click", "lead", "updated_at"]

    if not values:
        sheet.append_row(expected_header)
        return

    first_row = values[0]
    if first_row != expected_header:
        sheet.update("A1:D1", [expected_header])


# ===== 記錄 click / lead =====
def update_tracking(cid, action="click"):
    ensure_header()
    sheet = get_sheet()
    records = sheet.get_all_records()

    found = False

    for i, row in enumerate(records):
        if str(row.get("campaign_id", "")).strip() == str(cid).strip():
            found = True
            row_index = i + 2

            click = int(row.get("click", 0) or 0)
            lead = int(row.get("lead", 0) or 0)

            if action == "click":
                click += 1
            elif action == "lead":
                lead += 1

            sheet.update(
                f"B{row_index}:D{row_index}",
                [[click, lead, datetime.datetime.now().isoformat()]]
            )
            break

    if not found:
        click = 1 if action == "click" else 0
        lead = 1 if action == "lead" else 0

        sheet.append_row([
            cid,
            click,
            lead,
            datetime.datetime.now().isoformat()
        ])


# ===== 讀取全部 tracking =====
def get_tracking_data():
    ensure_header()
    sheet = get_sheet()
    records = sheet.get_all_records()

    data = {}
    for row in records:
        cid = str(row.get("campaign_id", "")).strip()
        if not cid:
            continue

        data[cid] = {
            "click": int(row.get("click", 0) or 0),
            "lead": int(row.get("lead", 0) or 0),
            "updated_at": row.get("updated_at", "")
        }

    return data
