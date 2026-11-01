# -*- coding: utf-8 -*-
"""全域學管（lccnet）設定的唯一權威來源。

2026-08-26 起，所有需要登入學管系統／呼叫學管 API 的專案，帳號、密碼、
待辦 API Token 與連結位置一律讀這裡，不再各自維護 user.md。
維護入口是 CAAC 名單分派系統主控台的「設定 → 全域設定」分頁。

設計決定（2026-08-26 與使用者確認）
------------------------------------
* **獨立資料庫**：`lccnet_config`，掛在既有的 `lcc-kpi-sys:asia-east1:lcc-kpi-pg`
  執行個體下（KPI／履歷／採購／職福／CAAC 都已經共用這台）。不寄生在任何一個
  系統的專屬 DB 裡，語意乾淨，且 CAAC 停用也不影響其他系統。
* **不加密**：既然要開放給 6+ 個系統讀，Fernet 金鑰就得跟著散布到每個系統的
  部署環境，同步成本高、實質安全效益低（金鑰散得跟密碼一樣廣）。改為明文存放，
  防線是「DB 帳號權限 ＋ Cloud SQL 網路隔離」——比照 user.md 本來就是明文的做法。
  唯讀權限透過 `lccnet_config_reader` 角色授予，各系統只能 SELECT，
  只有 CAAC 主控台的 `caac_app` 能寫。
* **user.md 降級為開發參考**：`D:\\AI-SYS\\user.md` 不再是執行時的來源，
  只留給新程式開發時本機試接用。詳見各專案規格書。

用法
----
    import lccnet_config
    acc, pwd = lccnet_config.get_credentials()
    token = lccnet_config.get_todo_token()

沒有現成連線時本模組會自己開一條短連線（讀完即關），因為呼叫端多半是
排程腳本而不是長駐服務。連線參數走環境變數，見 `_conn_kwargs()`。
"""
import os

import psycopg2

CONNECTION_NAME = "lcc-kpi-sys:asia-east1:lcc-kpi-pg"
DB_NAME = "lccnet_config"

# settings 表的 key 常數——各系統一律用這些常數，不要各自寫字串字面值。
KEY_ACCOUNT = "lcc_account"
KEY_PASSWORD = "lcc_password"
KEY_TODO_TOKEN = "lcc_todo_token"
KEY_BASE_URL = "lcc_base_url"
KEY_TODO_API_URL = "lcc_todo_api_url"

# 2026-09-02 新增：跨系統排程失敗的 Telegram 通知（比照 CAAC 自己的
# telegram_notify.py 機制，但存放位置刻意分開，見下方兩個 getter 的說明）。
KEY_TELEGRAM_BOT_TOKEN = "telegram_bot_token"
KEY_TELEGRAM_CHAT_ID = "telegram_admin_chat_id"

# 2026-09-19 新增：總公司排程伺服器（VM，與公司 Windows 主機同網段）。
# 各系統排程「主跑」主機的連線資料，部署／遠端維護時讀這裡，不要寫死在程式或 .bat。
KEY_SCHED_HOST = "sched_server_host"
KEY_SCHED_USER = "sched_server_user"
KEY_SCHED_PASSWORD = "sched_server_password"

# 2026-09-26 新增：聯成電腦 email 系統（OpenWebMail）網址，帳密同學管。
# 各系統登入信箱取信（CAAC 驗證碼、週會報告盤查…）一律經 lccnet_mail.py。
KEY_WEBMAIL_URL = "lcc_webmail_url"

# 2026-10-23 新增：系統通知寄件 Gmail（hq.lccnet.com.tw@gmail.com）與應用程式密碼，跨系統共用。
# 原本各系統放在 Zeabur 環境變數 EMAIL_SENDER/EMAIL_PASSWORD，10/14 Zeabur 外洩後改集中存這裡，
# 由 CAAC 主控台「全域設定 → 📧 系統寄信 Gmail」維護；各系統讀這組、環境變數只在全域 DB 連不上時備援。
KEY_SMTP_SENDER = "smtp_gmail_sender"
KEY_SMTP_APP_PASSWORD = "smtp_gmail_app_password"
# 寄件組別：不同系統用不同 Gmail 寄信。組別代碼接在 key 後面（"" 為預設組，"hr" → smtp_gmail_sender_hr）。
SMTP_PROFILES = [
    ("", "系統通知（hq，KPI 等）", "hq.lccnet.com.tw@gmail.com"),
    ("hr", "人才招募（hr，履歷系統）", "hr.lccnet.com.tw@gmail.com"),
]

# 2026-09-27 新增：Jev（OpenRouter Decisions API）共用金鑰。各系統 jev_client 讀取順序：
# 環境變數 OPENROUTER_API_KEY（系統專用）→ 這把共用金鑰 → 都沒有就停用 Jev。
# 明文存放（同學管密碼）；OpenRouter 端務必設每月額度上限。規劃見 D:/AI-SYS/tools/jev/。
KEY_OPENROUTER_SHARED_KEY = "openrouter_shared_key"

# 2026-09-27 新增：Anthropic（Claude）API 金鑰，跨系統共用。來源是 KPI 系統「AI 撰寫
# 主管審查回覆」用的那把；KPI 自 2026-09-27（V2.16）起改讀這把＋下方預設模型，
# Zeabur 的 ANTHROPIC_API_KEY 環境變數只在全域 DB 連不上時備援。其他系統建議同樣
# 以這把為主、自己的環境變數 ANTHROPIC_API_KEY 為備援 → 都沒有就停用 AI 功能。
KEY_ANTHROPIC_API_KEY = "anthropic_api_key"
# 用共用金鑰的系統預設呼叫哪個 Claude 模型（主控台下拉選單可改；各系統可用自己的設定覆蓋）。
KEY_ANTHROPIC_MODEL = "anthropic_default_model"
ANTHROPIC_MODELS = [
    ("claude-sonnet-5-5", "Claude Sonnet 5.5（預設：速度與品質平衡）"),
    ("claude-sonnet-5", "Claude Sonnet 5（前一版）"),
    ("claude-opus-5-5", "Claude Opus 5.5（品質較高、較貴）"),
    ("claude-opus-5", "Claude Opus 5"),
    ("claude-fable-5-1", "Claude Fable 5.1（最強、最貴）"),
    ("claude-haiku-4-5", "Claude Haiku 4.5（最快、最便宜）"),
]
# ⚠️ Sonnet 5.5 不接受 thinking {"type": "disabled"}（400），要關閉思考改傳 {"type": "between_tools"}
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"

# 2026-10-01 新增：排程衛兵（Sentinel，⑮ 排程維運 sentinel/sentinel.py）設定，
# 維護入口 CAAC 主控台「設定 → 🛡️ 排程衛兵」。值一律存字串，未設定時用 SENTINEL_DEFAULTS。
KEY_SENTINEL_ENABLED = "sentinel_enabled"
KEY_SENTINEL_PRIMARY_HOST = "sentinel_primary_host"
KEY_SENTINEL_WINDOW_START = "sentinel_window_start"
KEY_SENTINEL_WINDOW_END = "sentinel_window_end"
KEY_SENTINEL_INTERVAL_MIN = "sentinel_interval_min"
KEY_SENTINEL_KEYWORDS = "sentinel_keywords"
KEY_SENTINEL_EXCLUDE_KEYWORDS = "sentinel_exclude_keywords"
KEY_SENTINEL_MAX_FIX_ATTEMPTS = "sentinel_max_fix_attempts"
KEY_SENTINEL_AUTOFIX_ENABLED = "sentinel_autofix_enabled"
# LINE Messaging API（LINE Notify 已於 2025-03-31 停止服務）。空值時衛兵改發 Telegram。
KEY_LINE_CHANNEL_TOKEN = "line_channel_access_token"
KEY_LINE_ADMIN_USER_ID = "line_admin_user_id"
SENTINEL_HOSTS = ["windows", "vm"]
SENTINEL_DEFAULTS = {
    KEY_SENTINEL_ENABLED: "true",
    KEY_SENTINEL_PRIMARY_HOST: "windows",
    KEY_SENTINEL_WINDOW_START: "08:00",
    KEY_SENTINEL_WINDOW_END: "22:00",
    KEY_SENTINEL_INTERVAL_MIN: "30",
    KEY_SENTINEL_KEYWORDS: "\n".join(["【排程】", "排程未回報", "排程失敗", "停擺",
                                      "異常", "備援", "已過期", "Zeabur"]),
    KEY_SENTINEL_EXCLUDE_KEYWORDS: "\n".join(["排程已恢復", "已恢復", "簽到退", "切換完成", "Zeabur 完成"]),
    KEY_SENTINEL_MAX_FIX_ATTEMPTS: "2",
    KEY_SENTINEL_AUTOFIX_ENABLED: "true",
}

DEFAULT_BASE_URL = "https://student.lccnet.com.tw"
DEFAULT_WEBMAIL_URL = "http://mail.lccnet.com.tw"


def _conn_kwargs():
    """連線參數。本機走 cloud-sql-proxy 的 TCP，雲端走 unix socket。

    帳密與主機一律純讀 os.environ，比照 db.py 的慣例（機密不進設定檔）。
    優先吃 LCCNET_CONFIG_PG_* ，讓呼叫端能用獨立的唯讀帳號連這個共用 DB，
    不必跟自己系統的主 DB 帳號綁在一起；沒設就退回該系統既有的 PG_* 設定。
    """
    def pick(name, default=None):
        return (os.environ.get("LCCNET_CONFIG_PG_" + name)
                or os.environ.get("PG_" + name) or default)

    user = pick("USER", "caac_app")
    password = pick("PASSWORD", "")
    host = pick("HOST")
    port = int(pick("PORT", "5432"))
    conn_name = (os.environ.get("LCCNET_CONFIG_PG_CONNECTION_NAME")
                 or os.environ.get("PG_CONNECTION_NAME") or CONNECTION_NAME)
    if host:
        return dict(host=host, port=port, dbname=DB_NAME, user=user,
                    password=password, connect_timeout=20)
    return dict(host="/cloudsql/%s" % conn_name, dbname=DB_NAME,
                user=user, password=password)


def connect():
    conn = psycopg2.connect(**_conn_kwargs())
    conn.autocommit = True
    return conn


def get(key, default=None, conn=None):
    """讀一個設定值。conn 省略時自己開一條短連線。"""
    own = conn is None
    c = connect() if own else conn
    try:
        with c.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
            r = cur.fetchone()
        return r[0] if r and r[0] else default
    finally:
        if own:
            c.close()


def set(key, value, by="console", conn=None):
    """寫一個設定值。只有 CAAC 主控台（caac_app）有權限，其他系統會被 DB 擋下。"""
    own = conn is None
    c = connect() if own else conn
    try:
        with c.cursor() as cur:
            cur.execute("""INSERT INTO settings (key, value, updated_by, updated_at)
                           VALUES (%s, %s, %s, now())
                           ON CONFLICT (key) DO UPDATE
                           SET value=EXCLUDED.value, updated_by=EXCLUDED.updated_by,
                               updated_at=now()""", (key, str(value), by))
    finally:
        if own:
            c.close()


def is_set(key, conn=None):
    """是否已設定。空字串當成沒設定——清除是寫入空字串，沒有刪除介面。"""
    return bool(get(key, conn=conn))


def get_credentials(conn=None):
    """回傳 (帳號, 密碼)。兩者缺一就丟 RuntimeError，不回半套讓呼叫端拿去登入失敗。"""
    acc = get(KEY_ACCOUNT, conn=conn)
    pwd = get(KEY_PASSWORD, conn=conn)
    if not acc or not pwd:
        raise RuntimeError(
            "全域設定尚未填入學管帳號／密碼。請到 CAAC 名單分派系統主控台的"
            "「設定 → 全域設定」分頁填寫。")
    return acc, pwd


def get_todo_token(conn=None):
    return get(KEY_TODO_TOKEN, conn=conn)


def get_base_url(conn=None):
    return get(KEY_BASE_URL, DEFAULT_BASE_URL, conn=conn)


def get_webmail_url(conn=None):
    """聯成電腦 email 系統網址，登入帳密＝學管帳密。用法見 lccnet_mail.py。"""
    return get(KEY_WEBMAIL_URL, DEFAULT_WEBMAIL_URL, conn=conn)


def smtp_keys(profile=""):
    """寄件組別對應的 (寄件信箱 key, 應用程式密碼 key)。"""
    sfx = "_" + profile if profile else ""
    return KEY_SMTP_SENDER + sfx, KEY_SMTP_APP_PASSWORD + sfx


def get_smtp(conn=None, profile=""):
    """系統寄信 Gmail：回傳 (寄件信箱, 應用程式密碼)，未設定的欄位為 None。
    profile 見 SMTP_PROFILES（"" 預設組 hq、"hr" 履歷系統）。"""
    ks, kp = smtp_keys(profile)
    return get(ks, conn=conn), get(kp, conn=conn)


def get_todo_api_url(conn=None):
    return get(KEY_TODO_API_URL, conn=conn)


def get_telegram_bot_token(conn=None):
    """跨系統排程失敗通知用的 Bot Token。

    ⚠️ 這**不是** CAAC 自己 `telegram_notify.py` 讀的那個——CAAC 的管理員
    警示（主機停擺／備援接手等）token 存在 CAAC 自己的 DB（Fernet 加密）。
    這裡是給其他系統（每日業績系統等）用的，明文存放在這個共用表——
    跟學管密碼一樣，防線是 DB 帳號權限，不是加密（見本檔開頭的設計決定）。
    可以填同一個 Bot 的 token，也可以另開一個，兩邊互不影響。
    維護入口同樣是 CAAC 主控台「設定 → 全域設定」，但是另一個獨立欄位。
    """
    return get(KEY_TELEGRAM_BOT_TOKEN, conn=conn)


def get_telegram_chat_id(conn=None):
    return get(KEY_TELEGRAM_CHAT_ID, conn=conn)


def get_openrouter_shared_key(conn=None):
    """Jev 共用金鑰；沒設回 None（呼叫端就停用 Jev）。"""
    return (get(KEY_OPENROUTER_SHARED_KEY, "", conn=conn) or "").strip() or None


def get_anthropic_api_key(conn=None):
    """Anthropic（Claude）共用金鑰；沒設回 None（呼叫端就停用 AI 功能）。"""
    return (get(KEY_ANTHROPIC_API_KEY, "", conn=conn) or "").strip() or None


def get_anthropic_model(conn=None):
    """共用金鑰的預設 Claude 模型 ID；沒設回 DEFAULT_ANTHROPIC_MODEL（claude-sonnet-5-5）。"""
    return (get(KEY_ANTHROPIC_MODEL, "", conn=conn) or "").strip() or DEFAULT_ANTHROPIC_MODEL


def get_sentinel_settings(conn=None):
    """排程衛兵全部設定 {key: 字串}，未設定的 key 補 SENTINEL_DEFAULTS。"""
    own = conn is None
    c = connect() if own else conn
    try:
        with c.cursor() as cur:
            cur.execute("SELECT key, value FROM settings WHERE key = ANY(%s)",
                        (list(SENTINEL_DEFAULTS) + [KEY_LINE_CHANNEL_TOKEN, KEY_LINE_ADMIN_USER_ID],))
            got = {k: v for k, v in cur.fetchall() if v}
    finally:
        if own:
            c.close()
    out = dict(SENTINEL_DEFAULTS)
    out.update(got)
    return out


def get_sched_server(conn=None):
    """總公司排程伺服器 (host, user, password)；未設定的欄位為 None。

    明文存放，防線同學管密碼（DB 權限＋網路隔離）。維護入口：CAAC 主控台「設定 → 全域設定」。
    """
    return (get(KEY_SCHED_HOST, conn=conn), get(KEY_SCHED_USER, conn=conn),
            get(KEY_SCHED_PASSWORD, conn=conn))
