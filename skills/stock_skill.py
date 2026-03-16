import requests
from datetime import datetime
from skills.config import ALPHA_VANTAGE_API_KEY


def get_tsmc_tw_price() -> str:
    try:
        today = datetime.now().strftime("%Y%m01")
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_AVG"
        params = {
            "response": "json",
            "date": today,
            "stockNo": "2330",
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = data.get("data", [])

        if not rows:
            return "台積電現股：查無資料"

        last_row = rows[-1]
        price = last_row[1] if len(last_row) > 1 else "未知"
        return f"台積電現股最新可得均價：約新台幣 {price} 元"
    except Exception as e:
        return f"台積電現股資料取得失敗：{e}"


def get_tsm_adr_price() -> str:
    if not ALPHA_VANTAGE_API_KEY:
        return "TSM ADR：未設定 ALPHA_VANTAGE_API_KEY"

    try:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": "TSM",
            "apikey": ALPHA_VANTAGE_API_KEY,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        quote = data.get("Global Quote", {})
        price = quote.get("05. price")
        change = quote.get("09. change")
        change_percent = quote.get("10. change percent")

        if not price:
            return "TSM ADR：查無資料"

        return f"TSM ADR 最新報價：約 {price} 美元（漲跌 {change} / {change_percent}）"
    except Exception as e:
        return f"TSM ADR 資料取得失敗：{e}"


def get_stock_report() -> str:
    return (
        "4. 台積電及 TSM ADR 股價\n"
        f"- {get_tsmc_tw_price()}\n"
        f"- {get_tsm_adr_price()}"
    )
