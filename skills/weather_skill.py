import requests
import os

CWA_API_KEY = os.getenv("CWA_API_KEY")

def get_weather_report():

    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"

    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "locationName": "臺北市"
    }

    try:

        r = requests.get(
            url,
            params=params,
            timeout=10,
            verify=False
        )

        data = r.json()

        loc = data["records"]["location"][0]
        weather = loc["weatherElement"][0]["time"][0]["parameter"]["parameterName"]
        rain = loc["weatherElement"][1]["time"][0]["parameter"]["parameterName"]

        minT = loc["weatherElement"][2]["time"][0]["parameter"]["parameterName"]
        maxT = loc["weatherElement"][4]["time"][0]["parameter"]["parameterName"]

        return f"""
1. 天氣回報
台北市天氣：{weather}
氣溫：約 {minT}~{maxT}°C
降雨機率：{rain}%
"""

    except Exception as e:
        return f"天氣資料取得失敗：{e}"
