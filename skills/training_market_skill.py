from config import TRAINING_NEWS_KEYWORDS, SOCIAL_KEYWORDS
from skills.news_fetcher import fetch_news_bundle
from skills.social_fetcher import fetch_social_bundle
from skills.openai_summarizer import summarize_market_intel


def get_training_market_report() -> str:
    news_items = fetch_news_bundle(TRAINING_NEWS_KEYWORDS, per_keyword=3)
    social_items = fetch_social_bundle(SOCIAL_KEYWORDS, per_keyword=2)
    return summarize_market_intel(news_items, social_items)
