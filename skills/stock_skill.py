# skills/stock_skill.py

import requests
import os

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")


def get_stock_report():
    """
    台積電 + TSM ADR 股價回報
    """

    result = []

    # === 1️⃣ 台積電 (TWSE) ===
    try:
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_AVG"

        params = {
            "response": "json",
            "date": "20260301",
            "stockNo": "2330"
        }

        r = requests.get(url, params=params, timeout=10, verify=False)
        data = r.json()

        price = data["data"][-1][1]

        result.append(f"台積電現股：約 {price} 元")

    except Exception as e:
        result.append(f"台積電現股取得失敗：{e}")

    # === 2️⃣ TSM ADR ===
    try:
        url = "https://www.alphavantage.co/query"

        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": "TSM",
            "apikey": ALPHA_VANTAGE_API_KEY
        }

        r = requests.get(url, params=params, timeout=10, verify=False)
        data = r.json()

        price = data["Global Quote"]["05. price"]
        change = data["Global Quote"]["09. change"]
        percent = data["Global Quote"]["10. change percent"]

        result.append(f"TSM ADR：約 {price} USD（{change} / {percent}）")

    except Exception as e:
        result.append(f"TSM ADR取得失敗：{e}")

    return f"""
4. 台積電及 TSM ADR 股價
{chr(10).join(result)}
"""
