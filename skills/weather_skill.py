import requests
from skills.config import CWA_API_KEY, WEATHER_LOCATION


def get_weather_report(location_name: str = WEATHER_LOCATION) -> str:
    if not CWA_API_KEY:
        return (
            "1. 天氣回報\n"
            "未設定 CWA_API_KEY，無法取得中央氣象署資料。"
        )

    try:
        url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
        params = {
            "Authorization": CWA_API_KEY,
            "format": "JSON",
            "locationName": location_name,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        locations = data.get("records", {}).get("location", [])
        if not locations:
            return f"1. 天氣回報\n找不到 {location_name} 的資料。"

        loc = locations[0]
        elements = {e["elementName"]: e["time"] for e in loc.get("weatherElement", [])}

        wx = elements.get("Wx", [])
        pop = elements.get("PoP", [])
        min_t = elements.get("MinT", [])
        max_t = elements.get("MaxT", [])

        weather_text = wx[0]["parameter"]["parameterName"] if wx else "未知"
        pop_text = pop[0]["parameter"]["parameterName"] if pop else "未知"
        min_text = min_t[0]["parameter"]["parameterName"] if min_t else "未知"
        max_text = max_t[0]["parameter"]["parameterName"] if max_t else "未知"

        return (
            "1. 天氣回報\n"
            f"{location_name} 未來時段天氣：{weather_text}。\n"
            f"降雨機率：約 {pop_text}%。\n"
            f"溫度：約 {min_text}°C ~ {max_text}°C。"
        )
    except Exception as e:
        return f"1. 天氣回報\n取得資料失敗：{e}"
