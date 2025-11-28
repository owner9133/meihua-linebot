import os
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



💡 小提示：心誠則靈



# ==================== 主程式 ====================


if __name__ == '__main__':
port = int(os.environ.get('PORT', 5000))
logger.info('=' * 50)
logger.info('🔮 梅花易數占卜 LINE Bot 啟動中...')
logger.info(f'Port: {port}')
logger.info('=' * 50)
# debug=False 為生產環境建議
app.run(host='0.0.0.0', port=port, debug=False)

