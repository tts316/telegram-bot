import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
CWA_API_KEY = os.getenv("CWA_API_KEY", "").strip()
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "").strip()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()

WEATHER_LOCATION = os.getenv("WEATHER_LOCATION", "臺北市").strip()

REPORT_MAX_ITEMS = int(os.getenv("REPORT_MAX_ITEMS", "2"))
REPORT_MAX_CHARS = int(os.getenv("REPORT_MAX_CHARS", "3500"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
