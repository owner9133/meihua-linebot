"""
梅花易數占卜 LINE Bot
適用於 line-bot-sdk==1.20.0
環境變數配置，適合部署到 Render
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

# Google Gemini API
import google.generativeai as genai

# ==================== 設定區 ====================
# 從環境變數讀取金鑰（需在 Render 設定環境變數）
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# ==================== 初始化 ====================
app = Flask(__name__)

# LINE Bot API 初始化
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Gemini API 初始化
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-2.0-flash')

# ==================== 梅花易數核心資料 ====================

# 先天八卦數
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

# 六十四卦對應表
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

# ==================== 梅花易數起卦函數 ====================

def num_to_gua(num):
    """將數字轉換為八卦"""
    remainder = num % 8
    return 8 if remainder == 0 else remainder

def num_to_yao(num):
    """將數字轉換為動爻"""
    remainder = num % 6
    return 6 if remainder == 0 else remainder

def get_bian_gua(gua_num, yao_position):
    """根據動爻位置計算變卦"""
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
    """數字起卦法"""
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

def qigua_by_time():
    """時間起卦法"""
    now = datetime.now()
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
    """隨機起卦法"""
    num1 = random.randint(1, 999)
    num2 = random.randint(1, 999)
    result = qigua_by_number(num1, num2)
    result['random_nums'] = (num1, num2)
    return result

def format_gua_result(gua_data):
    """格式化卦象結果"""
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

# ==================== AI 解卦 ====================

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

def get_ai_interpretation(ben_gua, bian_gua, yao, user_question):
    """使用 AI 解讀卦象"""
    prompt = f"""{MEIHUA_SYSTEM_PROMPT}

使用者的問題：{user_question}

占卜結果：
- 本卦：{ben_gua}
- 變卦：{bian_gua}
- 動爻：第{yao}爻

請根據以上卦象，為使用者的問題提供詳細的解讀和建議。
"""
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if attempt < 2:
                time.sleep((attempt + 1) * 10)
            else:
                return "⚠️ AI 解讀服務暫時繁忙，請稍後再試。"
    
    return "⚠️ 無法取得 AI 解讀，請稍後再試。"

# ==================== LINE Bot 路由 ====================

@app.route("/")
def home():
    return "🔮 梅花易數占卜 LINE Bot 正在運行中"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        print(f"收到訊息: {event.message.text}")
        user_message = event.message.text.strip()
        
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
            reply = process_divination("請為我解讀當下的運勢", 'time')
        
        elif user_message in ['隨機占卜', '隨機起卦']:
            reply = process_divination("請為我解讀整體運勢", 'random')
        
        else:
            # 如果是問句，當作占卜問題
            if any(kw in user_message for kw in ['？', '?', '嗎', '呢', '如何', '怎麼', '會不會', '能不能', '可以', '應該']):
                reply = process_divination(user_message, 'random')
            else:
                reply = "🔮 梅花易數占卜機器人\n\n" + get_help_message()
        
        print(f"準備回覆: {reply[:50]}...")
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
        
        print("訊息已送出")
        
    except Exception as e:
        print(f"❌ 錯誤發生: {e}")
        import traceback
        traceback.print_exc()

def process_divination(question, method='random'):
    """處理占卜請求"""
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
    """處理數字占卜"""
    parts = message.replace('數字占卜', '').strip().split()
    
    if len(parts) < 2:
        return "⚠️ 數字占卜格式：\n數字占卜 [數字1] [數字2]\n\n例如：數字占卜 168 888"
    
    try:
        num1 = int(parts[0])
        num2 = int(parts[1])
        question = ' '.join(parts[2:]) if len(parts) > 2 else "請解讀此卦象"
        
        gua_data = qigua_by_number(num1, num2)
        method_info = f"🔢 您的數字：{num1}, {num2}"
        
        gua_result, ben_gua, bian_gua, yao = format_gua_result(gua_data)
        ai_interpretation = get_ai_interpretation(ben_gua, bian_gua, yao, question)
        
        return f"📝 您的問題：{question}\n{method_info}\n{gua_result}\n🌟【易學大師解讀】\n{ai_interpretation}"
        
    except ValueError:
        return "⚠️ 請輸入有效的數字。\n\n格式：數字占卜 [數字1] [數字2]"

def get_help_message():
    """取得使用說明"""
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

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print("=" * 50)
    print("🔮 梅花易數占卜 LINE Bot 啟動中...")
    print(f"Port: {port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)
