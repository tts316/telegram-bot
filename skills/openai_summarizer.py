from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL


def summarize_market_intel(news_items: list[dict], social_items: list[dict]) -> str:
    if not OPENAI_API_KEY:
        return _fallback_summary(news_items, social_items)

    client = OpenAI(api_key=OPENAI_API_KEY)

    news_text = "\n".join(
        [
            f"[新聞{i+1}] 標題：{item.get('title','')} | 關鍵字：{item.get('keyword','')} | 發布：{item.get('published','')} | 連結：{item.get('link','')}"
            for i, item in enumerate(news_items[:15])
        ]
    )

    social_text = "\n".join(
        [
            f"[社群{i+1}] 標題：{item.get('title','')} | 關鍵字：{item.get('keyword','')} | 發布：{item.get('published','')} | 連結：{item.get('link','')}"
            for i, item in enumerate(social_items[:15])
        ]
    )

    prompt = f"""
你是台灣教育培訓與補教市場情報分析助理。
請用繁體中文，整理下面資料成 Telegram 可直接閱讀的簡報格式。

需求：
1. 標題：台灣補教 / 培訓市場情報
2. 分成三段：
   - 市場新聞重點
   - 社群熱點（Dcard / Threads）
   - 商業觀察與建議
3. 每段請精簡、清楚、商務口吻
4. 不要虛構不存在的事實
5. 若資料不足，要明確寫「目前可見資訊有限」
6. 總長控制在 400~700 字內

以下是新聞資料：
{news_text}

以下是社群資料：
{social_text}
"""

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    return response.output_text.strip()


def summarize_ai_news(news_items: list[dict]) -> str:
    if not OPENAI_API_KEY:
        return _fallback_ai_news(news_items)

    client = OpenAI(api_key=OPENAI_API_KEY)

    news_text = "\n".join(
        [
            f"[新聞{i+1}] 標題：{item.get('title','')} | 關鍵字：{item.get('keyword','')} | 發布：{item.get('published','')} | 連結：{item.get('link','')}"
            for i, item in enumerate(news_items[:12])
        ]
    )

    prompt = f"""
你是科技與 AI 新聞助理。
請用繁體中文整理以下資料，輸出成 Telegram 可直接閱讀格式。

格式：
2. AI新聞、科技新聞、股市新聞重點
- AI新聞：
- 科技新聞：
- 股市 / 產業觀察：

限制：
1. 不虛構
2. 300~500字
3. 若資料不足請明說

資料如下：
{news_text}
"""

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    return response.output_text.strip()


def _fallback_summary(news_items: list[dict], social_items: list[dict]) -> str:
    lines = ["5. 台灣補教 / 培訓市場情報"]

    if news_items:
        lines.append("- 市場新聞重點：")
        for item in news_items[:3]:
            lines.append(f"  • {item.get('title', '')}")
    else:
        lines.append("- 市場新聞重點：目前可見資訊有限。")

    if social_items:
        lines.append("- 社群熱點：")
        for item in social_items[:3]:
            lines.append(f"  • {item.get('title', '')}")
    else:
        lines.append("- 社群熱點：目前可見資訊有限。")

    lines.append("- 商業觀察：補教、職能培訓、AI應用課程仍具討論熱度，可持續追蹤需求轉向與課程包裝。")
    return "\n".join(lines)


def _fallback_ai_news(news_items: list[dict]) -> str:
    lines = ["2. AI新聞、科技新聞、股市新聞重點"]
    if not news_items:
        lines.append("- 目前可見資訊有限。")
        return "\n".join(lines)

    for item in news_items[:5]:
        lines.append(f"- {item.get('title', '')}")
    return "\n".join(lines)
