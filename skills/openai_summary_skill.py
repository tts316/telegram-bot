from openai import OpenAI
from skills.config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def summarize_text(title: str, content: str, topic: str = "新聞") -> str:
    fallback = f"{title}\n摘要：{(content or '')[:120]}..."

    if not client:
        return fallback

    try:
        prompt = f"""
你是台灣繁體中文商業情報助理。
請將以下{topic}整理成 2~3 句重點摘要，使用繁體中文，語氣專業清楚，不要過度誇飾。

標題：{title}

內容：
{content}
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是專業的繁體中文摘要助理。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return fallback
