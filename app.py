"""
梅花易數占卜 LINE Bot - 完整可部署版本
適用：line-bot-sdk==1.20.0
建議部署至 Render / Heroku / VPS
說明：
- 支援三種起卦方式：數字、時間、隨機
- 加強 Gemini (Google Generative AI) 呼叫重試與退化策略（若 API 不可用會使用本地簡易解卦模板回覆）
- 詳細日誌，環境變數檢查
- 小型 Procfile 範例：web: gunicorn meihua_linebot:app

"""

import os
import time
import random
import logging
from datetime import datetime
from flask import Flask, request, abort

# LINE Bot SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# Google Gemini API (注意：需安裝 google-generative-ai，並根據官方文件初始化)
import google.generativeai as genai

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== 設定區 ====================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 環境變數檢查（若缺少 LINE 關鍵憑證，啟動時就失敗）
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    logger.error('缺少 LINE Channel 金鑰，請在環境變數設定 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_CHANNEL_SECRET')
    raise RuntimeError('缺少 LINE Channel 金鑰')

# ==================== 初始化 ====================
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 嘗試初始化 Gemini，如果沒有設定 GEMINI_API_KEY，將啟用本地退化模式
USE_GEMINI = False
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # 舊版示例：model = genai.GenerativeModel('models/gemini-2.0-flash')
        # new usage uses genai.generate() or client patterns. 為了兼容，不直接呼叫 client 層。
        USE_GEMINI = True
        logger.info('已設定 GEMINI API Key，啟用線上 AI 解卦模式')
    except Exception as e:
        logger.warning(f'嘗試設定 Gemini 時發生錯誤，將退回本地模板：{e}')
        USE_GEMINI = False
else:
    logger.info('未設定 GEMINI_API_KEY，啟用本地退化解卦')

# ==================== 梅花易數核心資料 ====================
BAGUA_NUM = {
    1: {'name': '乾', 'symbol': '☰', 'nature': '天', 'attribute': '剛健', 'element': '金'},
    2: {'name': '兌', 'symbol': '☱', 'nature': '澤', 'attribute': '喜悅', 'element': '金'},
    3: {'name': '離', 'symbol': '☲', 'nature': '火', 'attribute': '光明', 'element': '火'},
    4: {'name': '震', 'symbol': '☳', 'nature': '雷', 'attribute': '震動', 'element': '木'},
    5: {'name': '巽', 'symbol': '☴', 'nature': '風', 'attribute': '順入', 'element': '木'},
    6: {'name': '坎', 'symbol': '☵', 'nature': '水', 'attribute': '陷險', 'element': '水'},
    7: {'name': '艮', 'symbol': '☶', 'nature': '山', 'attribute': '止靜', 'element': '土'},
    8: {'name': '坤', 'symbol': '☷', 'nature': '地', 'attribute': '順承', 'element': '土'},
}

HEXAGRAM_TABLE = {
    (1,1): '乾為天', (1,2): '天澤履', (1,3): '天火同人', (1,4): '天雷無妄',
    (1,5): '天風姤', (1,6): '天水訟', (1,7): '天山遯', (1,8): '天地否',
    (2,1): '澤天夬', (2,2): '兌為澤', (2,3): '澤火革', (2,4): '澤雷隨',
    (2,5): '澤風大過', (2,6): '澤水困', (2,7): '澤山咸', (2,8): '澤地萃',
    (3,1): '火天大有', (3,2): '火澤睽', (3,3): '離為火', (3,4): '火雷噬嗑',
    (3,5): '火風鼎', (3,6): '火水未濟', (3,7): '火山旅', (3,8): '火地晉',
    (4,1): '雷天大壯', (4,2): '雷澤歸妹', (4,3): '雷火豐', (4,4): '震為雷',
    (4,5): '雷風恆', (4,6): '雷水解', (4,7): '雷山小過', (4,8): '雷地豫',
    (5,1): '風天小畜', (5,2): '風澤中孚', (5,3): '風火家人', (5,4): '風雷益',
    (5,5): '巽為風', (5,6): '風水渙', (5,7): '風山漸', (5,8): '風地觀',
    (6,1): '水天需', (6,2): '水澤節', (6,3): '水火既濟', (6,4): '水雷屯',
    (6,5): '水風井', (6,6): '坎為水', (6,7): '水山蹇', (6,8): '水地比',
    (7,1): '山天大畜', (7,2): '山澤損', (7,3): '山火賁', (7,4): '山雷頤',
    (7,5): '山風蠱', (7,6): '山水蒙', (7,7): '艮為山', (7,8): '山地剝',
    (8,1): '地天泰', (8,2): '地澤臨', (8,3): '地火明夷', (8,4): '地雷復',
    (8,5): '地風升', (8,6): '地水師', (8,7): '地山謙', (8,8): '坤為地',
}

# ==================== 起卦與格式化函數 ====================

def num_to_gua(num):
    remainder = num % 8
    return 8 if remainder == 0 else remainder


def num_to_yao(num):
    remainder = num % 6
    return 6 if remainder == 0 else remainder


def get_bian_gua(gua_num, yao_position):
    gua_binary = {
        1: [1, 1, 1], 2: [0, 1, 1], 3: [1, 0, 1], 4: [0, 0, 1],
        5: [1, 1, 0], 6: [0, 1, 0], 7: [1, 0, 0], 8: [0, 0, 0],
    }
    binary_to_gua = {
        (1,1,1): 1, (0,1,1): 2, (1,0,1): 3, (0,0,1): 4,
        (1,1,0): 5, (0,1,0): 6, (1,0,0): 7, (0,0,0): 8,
    }
    binary = gua_binary[gua_num].copy()
    yao_index = (yao_position - 1) % 3
    binary[yao_index] = 1 - binary[yao_index]
    return binary_to_gua[tuple(binary)]


def qigua_by_number(num1, num2):
    upper_gua = num_to_gua(num1)
    lower_gua = num_to_gua(num2)
    yao = num_to_yao(num1 + num2)

    if yao <= 3:
        bian_lower = get_bian_gua(lower_gua, yao)
        bian_upper = upper_gua
    else:
        bian_upper = get_bian_gua(upper_gua, yao - 3)
        bian_lower = lower_gua

    return {
        'upper': upper_gua, 'lower': lower_gua, 'yao': yao,
        'bian_upper': bian_upper, 'bian_lower': bian_lower,
    }


def qigua_by_time(now=None):
    """時間起卦法，可傳入指定時間以便單元測試"""
    if now is None:
        now = datetime.now()

    # 傳統時辰每兩小時計為一格，這裡以 ((hour +1)//2) 取整
    hour_num = ((now.hour + 1) // 2) % 12
    if hour_num == 0:
        hour_num = 12

    upper_num = now.year + now.month + now.day
    lower_num = upper_num + hour_num

    upper_gua = num_to_gua(upper_num)
    lower_gua = num_to_gua(lower_num)
    yao = num_to_yao(lower_num)

    if yao <= 3:
        bian_lower = get_bian_gua(lower_gua, yao)
        bian_upper = upper_gua
    else:
        bian_upper = get_bian_gua(upper_gua, yao - 3)
        bian_lower = lower_gua

    return {
        'upper': upper_gua, 'lower': lower_gua, 'yao': yao,
        'bian_upper': bian_upper, 'bian_lower': bian_lower,
        'time_info': f"{now.year}年{now.month}月{now.day}日 {now.hour}時"
    }


def qigua_random():
    num1 = random.randint(1, 999)
    num2 = random.randint(1, 999)
    result = qigua_by_number(num1, num2)
    result['random_nums'] = (num1, num2)
    return result


def format_gua_result(gua_data):
    upper = BAGUA_NUM[gua_data['upper']]
    lower = BAGUA_NUM[gua_data['lower']]
    bian_upper = BAGUA_NUM[gua_data['bian_upper']]
    bian_lower = BAGUA_NUM[gua_data['bian_lower']]

    ben_gua = HEXAGRAM_TABLE.get((gua_data['upper'], gua_data['lower']), '未知卦')
    bian_gua = HEXAGRAM_TABLE.get((gua_data['bian_upper'], gua_data['bian_lower']), '未知卦')

    result = "\n━━━━━━━━━━━━━━━━\n"
    result += "🔮 【梅花易數占卜結果】\n"
    result += "━━━━━━━━━━━━━━━━\n\n"
    result += f"📌 本卦：{ben_gua}\n"
    result += f"   上卦：{upper['name']}卦 {upper['symbol']}（{upper['nature']}・{upper['attribute']}・{upper['element']}）\n"
    result += f"   下卦：{lower['name']}卦 {lower['symbol']}（{lower['nature']}・{lower['attribute']}・{lower['element']}）\n\n"
    result += f"📌 動爻：第 {gua_data['yao']} 爻\n\n"
    result += f"📌 變卦：{bian_gua}\n"
    result += f"   上卦：{bian_upper['name']}卦 {bian_upper['symbol']}\n"
    result += f"   下卦：{bian_lower['name']}卦 {bian_lower['symbol']}\n\n"
    result += "━━━━━━━━━━━━━━━━\n"

    return result, ben_gua, bian_gua, gua_data['yao']

# ==================== AI 解卦（含退化策略） ====================

MEIHUA_SYSTEM_PROMPT = """你是一位精通梅花易數的資深易學大師，擁有數十年的占卜經驗。

你的角色和風格：
- 說話溫和、睿智，帶有古典韻味但不失親切
- 解卦時條理分明，深入淺出
- 給予正面、建設性的指引，避免過度負面的預測

解卦時請依照以下結構回答：

1.【卦象總論】（2-3句話概括整體卦象的意涵）

2.【本卦解析】解釋本卦的核心意義

3.【動爻啟示】動爻位置代表的變化重點

4.【變卦展望】事態發展的最終走向

5.【具體建議】根據使用者的問題給出具體、實用的建議

6.【吉凶判斷】簡明扼要的吉凶評估

請用繁體中文回答，語氣溫暖親切但專業。回答約300-400字。
"""


def simple_local_interpretation(ben_gua, bian_gua, yao, user_question):
    """當 Gemini 無法使用時，給出一份簡潔且有建議性的本地模板回覆。"""
    text = (
        f"【（系統備援）易學初步解讀】\n\n"
        f"卦象總論：本卦「{ben_gua}」變為「{bian_gua}」，代表事物正處於變動與調整階段，宜以穩健為主。\n\n"
        f"本卦解析：{ben_gua} 多與人事、方向相關，需注意溝通與步驟的完整性。\n\n"
        f"動爻啟示：第 {yao} 爻顯示變化焦點在於細節處理與時機把握。\n\n"
        f"變卦展望：若能耐心修正，事態將逐步轉為穩定；若忽視細節，易遭小障礙影響。\n\n"
        f"具體建議：檢視優先順序、做好溝通、避免衝動決策。若與人相關事務，先詢問對方意見再行動。\n\n"
        f"吉凶判斷：屬中性偏吉，宜守不宜攻。\n"
    )
    return text


def get_ai_interpretation(ben_gua, bian_gua, yao, user_question):
    """使用 Gemini 進行解卦，若失敗則回退到 simple_local_interpretation。"""
    if not USE_GEMINI:
        return simple_local_interpretation(ben_gua, bian_gua, yao, user_question) + "\n\n⚠️ 提示：目前使用本地備援解讀，若需更深入解析請設定 GEMINI_API_KEY。"

    prompt = f"{MEIHUA_SYSTEM_PROMPT}\n\n使用者的問題：{user_question}\n\n占卜結果：\n- 本卦：{ben_gua}\n- 變卦：{bian_gua}\n- 動爻：第{yao}爻\n\n請根據以上卦象，為使用者的問題提供詳細的解讀和建議。"

    # 簡單的重試與指數退避
    max_attempts = 3
    backoff_seconds = 5
    for attempt in range(1, max_attempts + 1):
        try:
            # 這裡嘗試使用 genai.generate 的通用調用；視你安裝的 SDK 版本微調
            response = genai.generate(
                model="models/gemini-2.0",
                prompt=prompt,
                temperature=0.3,
                max_output_tokens=800,
            )
            # response 物件依 SDK 版本可能不同，嘗試取常見欄位
            text = None
            if hasattr(response, 'text'):
                text = response.text
            elif isinstance(response, dict):
                # 若回傳 dict，常見 key: 'candidates' 或 'content'
                if 'candidates' in response and len(response['candidates']) > 0:
                    text = response['candidates'][0].get('content', '')
                else:
                    text = response.get('content', '') or response.get('output', '')

            if not text:
                raise RuntimeError('無法解析 Gemini 回應內容')

            return text

        except Exception as e:
            logger.warning(f'第 {attempt} 次呼叫 Gemini 發生錯誤：{e}')
            if attempt < max_attempts:
                sleep_time = backoff_seconds * attempt
                logger.info(f'等待 {sleep_time}s 後重試...')
                time.sleep(sleep_time)
            else:
                logger.error('多次嘗試後 Gemini 仍不可用，使用本地備援解讀')
                return simple_local_interpretation(ben_gua, bian_gua, yao, user_question) + (
                    "\n\n⚠️ 提示：AI 解讀服務暫時繁忙或金鑰/配額問題，已使用本地備援回覆。請稍後檢查 GEMINI_API_KEY 或 API 配額。"
                )

# ==================== LINE Bot 路由與處理 ====================

@app.route('/')
def home():
    return '🔮 梅花易數占卜 LINE Bot 正常運行'


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error('Invalid signature')
        abort(400)
    except Exception as e:
        logger.exception(f'處理 webhook 時發生錯誤: {e}')
        abort(500)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_message = event.message.text.strip()
        logger.info(f"收到訊息: {user_message}")

        # 指令處理
        if user_message in ['使用說明', '說明', 'help', '?', '？']:
            reply = get_help_message()

        elif user_message in ['占卜', '起卦', '卜卦']:
            reply = "🔮 請告訴我您想占問的事情，例如：\n\n「占卜 我的工作運勢如何？」\n「占卜 這段感情會有結果嗎？」\n\n或輸入：\n「數字占卜 123 456」\n「時間占卜」"

        elif user_message.startswith('占卜 ') or user_message.startswith('占卜：'):
            question = user_message.replace('占卜 ', '').replace('占卜：', '').strip()
            reply = process_divination(question, 'random')

        elif user_message.startswith('數字占卜'):
            reply = process_number_divination(user_message)

        elif user_message in ['時間占卜', '時間起卦']:
            reply = process_divination('請為我解讀當下的運勢', 'time')

        elif user_message in ['隨機占卜', '隨機起卦']:
            reply = process_divination('請為我解讀整體運勢', 'random')

        else:
            if any(kw in user_message for kw in ['？', '?', '嗎', '呢', '如何', '怎麼', '會不會', '能不能', '可以', '應該']):
                reply = process_divination(user_message, 'random')
            else:
                reply = '🔮 梅花易數占卜機器人\n\n' + get_help_message()

        logger.info(f'準備回覆長度: {len(reply)}')

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
        logger.info('訊息已送出')

    except Exception as e:
        logger.exception(f'回覆使用者時發生錯誤: {e}')


# ==================== 處理占卜邏輯函數 ====================

def process_divination(question, method='random'):
    if method == 'time':
        gua_data = qigua_by_time()
        method_info = f"⏰ 起卦時間：{gua_data.get('time_info', '當前時間')}"
    else:
        gua_data = qigua_random()
        nums = gua_data.get('random_nums', (0, 0))
        method_info = f"🎲 隨機數字：{nums[0]}, {nums[1]}"

    gua_result, ben_gua, bian_gua, yao = format_gua_result(gua_data)
    ai_interpretation = get_ai_interpretation(ben_gua, bian_gua, yao, question)

    reply = f"📝 您的問題：{question}\n{method_info}\n{gua_result}\n🌟【易學大師解讀】\n{ai_interpretation}"
    return reply


def process_number_divination(message):
    parts = message.replace('數字占卜', '').strip().split()

    if len(parts) < 2:
        return "⚠️ 數字占卜格式：\n數字占卜 [數字1] [數字2]\n\n例如：數字占卜 168 888"

    try:
        num1 = int(parts[0])
        num2 = int(parts[1])
        question = ' '.join(parts[2:]) if len(parts) > 2 else '請解讀此卦象'

        gua_data = qigua_by_number(num1, num2)
        method_info = f"🔢 您的數字：{num1}, {num2}"

        gua_result, ben_gua, bian_gua, yao = format_gua_result(gua_data)
        ai_interpretation = get_ai_interpretation(ben_gua, bian_gua, yao, question)

        return f"📝 您的問題：{question}\n{method_info}\n{gua_result}\n🌟【易學大師解讀】\n{ai_interpretation}"

    except ValueError:
        return "⚠️ 請輸入有效的數字。\n\n格式：數字占卜 [數字1] [數字2]"


def get_help_message():
    return """📖 【梅花易數占卜使用說明】

🎯 快速占卜：
直接輸入問題即可，例如：
• 「我的工作運勢如何？」
• 「這段感情會有結果嗎？」

🔮 指定起卦方式：

1️⃣ 輸入「占卜 [問題]」
   例如：占卜 我該換工作嗎？

2️⃣ 輸入「數字占卜 [數字1] [數字2]」
   例如：數字占卜 168 888

3️⃣ 輸入「時間占卜」
   以當前時間起卦

━━━━━━━━━━━━━━━━
💡 小提示：心誠則靈
━━━━━━━━━━━━━━━━"""

# ==================== 主程式 ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info('=' * 50)
    logger.info('🔮 梅花易數占卜 LINE Bot 啟動中...')
    logger.info(f'Port: {port}')
    logger.info('=' * 50)
    # debug=False 為生產環境建議
    app.run(host='0.0.0.0', port=port, debug=False)
