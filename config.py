import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

BOT_TIMEZONE = ZoneInfo("Asia/Taipei")
DEFAULT_LOCATION = "台北市"

TRAINING_NEWS_KEYWORDS = [
    "台灣 補教 新聞",
    "台灣 教育培訓 新聞",
    "台灣 企業內訓 新聞",
    "台灣 AI 課程 新聞",
    "台灣 語言補習班 新聞",
]

SOCIAL_KEYWORDS = [
    "台灣 補教 site:dcard.tw",
    "台灣 培訓 site:dcard.tw",
    "補習班 site:dcard.tw",
    "AI 課程 site:dcard.tw",
    "台灣 補教 Threads",
    "台灣 培訓 Threads",
    "AI 課程 Threads",
]
