"""
梅花易數占卜 LINE Bot
適用於 line-bot-sdk==1.20.0
Google Gemini 正確版本
"""

import os
import time
import random
from datetime import datetime
from flask import Flask, request, abort

# LINE Bot SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# Google Gemini API（新版正確引用）
import google.generativeai as genai

# =========================
# Flask 初始化
# =========================
app = Flask(__name__)

# =========================
# LINE Bot 初始化
# =========================
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# =========================
# Gemini 初始化（正確用法）
# =========================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


# ============================================================
# 產生梅花易數卦象
# ============================================================
def generate_gua():
    """產生 6 爻（0=陰，1=陽）"""
    return [random.randint(0, 1) for _ in range(6)]


def gua_to_text(lines):
    """將卦象轉成文字符號"""
    symbols = {1: "⚊ 陽爻", 0: "⚋ 陰爻"}
    return "\n".join([f"{i+1}. {symbols[line]}" for i, line in enumerate(lines)])


# ============================================================
# Gemini 解讀卦象（含自動重試 + 本地備援）
# ============================================================
def interpret_gua_with_gemini(question, gua_text, max_retries=3):
    prompt = f"""
使用梅花易數的方式解讀卦象。

使用者問題：{question}

卦象如下：
{gua_text}

請提供：
1. 卦象主題與意義  
2. 目前狀態  
3. 可能的發展  
4. 建議  
"""

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[INFO] 呼叫 Gemini 第 {attempt} 次...")

            response = model.generate_content(prompt)

            if response and hasattr(response, "text"):
                return response.text

        except Exception as e:
            print(f"[WARNING] Gemini 第 {attempt} 次錯誤：{e}")
            time.sleep(attempt * 5)  # 指數退避 5s、10s、15s

    # ==================
    # 本地備援（保證不會炸）
    # ==================
    return f"""
Gemini 目前連線不穩，以下為本地備援解讀：

你的問題：{question}

卦象：
{gua_text}

解讀：
此卦象顯示事情正處於變動階段，需要耐心與觀察。
目前局勢尚未完全明朗，但只要保持穩定、避免衝動，
最終仍有向好方向發展的可能。

建議：
保持節制、順勢而為，不強求，可逐步觀察情況再做決定。
"""


# ============================================================
# LINE Webhook
# ============================================================
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")

    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


# ============================================================
# 文字訊息處理
# ============================================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    # 產生卦象
    gua = generate_gua()
    gua_text = gua_to_text(gua)

    # 使用 Gemini 解讀
    interpretation = interpret_gua_with_gemini(user_text, gua_text)

    reply_text = f"""
🔮 梅花易數占卜結果 🔮

你問的是：
「{user_text}」

卦象如下：
{gua_text}

—— 解讀 ——
{interpretation}
"""

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(reply_text)
    )


# ============================================================
# 啟動（Render 需要）
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
