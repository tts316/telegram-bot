import requests
import os

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

def get_tsm_adr():

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": "TSM",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    try:

        r = requests.get(url, params=params, timeout=10, verify=False)

        data = r.json()

        price = data["Global Quote"]["05. price"]
        change = data["Global Quote"]["09. change"]
        percent = data["Global Quote"]["10. change percent"]

        return f"""
TSM ADR
價格：{price} USD
漲跌：{change} ({percent})
"""

    except Exception as e:
        return f"TSM ADR資料取得失敗：{e}"
