# -*- coding: utf-8 -*-
"""Claude（Anthropic Messages API）呼叫，bot 內所有 AI 文字生成都走這裡。

金鑰：環境變數 ANTHROPIC_API_KEY → 全域設定 lccnet_config.get_anthropic_api_key()
      → 都沒有就停用 AI（generate() 丟 AIUnavailable，呼叫端回覆友善訊息）。
模型：環境變數 ANTHROPIC_MODEL（選用覆寫）→ lccnet_config.get_anthropic_model()。
全域設定讀取結果快取 10 分鐘，避免每次生成都開 DB 連線。
"""
import logging
import os
import time

logger = logging.getLogger(__name__)

DISABLED_MESSAGE = "⚠️ AI 功能目前未啟用（未設定 Claude 金鑰），請聯絡管理者。"
_CACHE_TTL = 600
_cache = {"at": 0.0, "key": None, "model": None}


class AIUnavailable(RuntimeError):
    pass


def _read_global():
    try:
        import lccnet_config
    except Exception as e:  # psycopg2 未安裝等
        logger.warning("無法載入 lccnet_config：%s", e)
        return None, None
    try:
        conn = lccnet_config.connect()
        try:
            return (lccnet_config.get_anthropic_api_key(conn=conn),
                    lccnet_config.get_anthropic_model(conn=conn))
        finally:
            conn.close()
    except Exception as e:
        logger.warning("讀取全域設定 lccnet_config 失敗：%s", e)
        return None, lccnet_config.DEFAULT_ANTHROPIC_MODEL


def _settings():
    """回傳 (api_key, model)；api_key 為 None 表示 AI 停用。"""
    env_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
    env_model = os.getenv("ANTHROPIC_MODEL", "").strip() or None
    if env_key and env_model:
        return env_key, env_model
    if time.time() - _cache["at"] > _CACHE_TTL:
        _cache["key"], _cache["model"] = _read_global()
        _cache["at"] = time.time()
    return env_key or _cache["key"], env_model or _cache["model"]


def get_model():
    return _settings()[1] or "（未取得）"


def is_enabled():
    key, model = _settings()
    return bool(key and model)


def generate(prompt, timeout=60, max_tokens=4096):
    """送單一 user prompt，回傳純文字。AI 停用時丟 AIUnavailable。"""
    key, model = _settings()
    if not (key and model):
        raise AIUnavailable(DISABLED_MESSAGE)
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=timeout)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
