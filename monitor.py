import os
import requests
from datetime import datetime
import pytz

# ==================== 监控配置中心 ====================
# 填写指南： 
# 1. 想增加监控：把下方 00000x 改成真实的国内基金代码，并填写对应的海外代码和简称。
# 2. 海外代码：去 Yahoo Finance 搜索，如 QQQ, NVDA, TSLA 等。
FUND_CONFIG = {
    "162411": ["XOP",  "华宝油气"],
    "160216": ["USO",  "原油LOF"],
    "159509": ["NVDA", "纳指科技"],
    "501225": ["SOXX", "全球芯片"],
    "161129": ["XBI",  "生物科技"],
    "164906": ["KWEB", "中概互联"],
    "161125": ["IVV",  "标普500"],
    "513500": ["IVV",  "标普500ETF"],
    "161127": ["QQQ",  "纳指100"],
    "513100": ["QQQ",  "纳指ETF"],
    # --- 预留占位符：只需把 00000x 改为真实代码即可启用 ---
    "000001": ["SPY",  "预留01"],
    "000002": ["DIA",  "预留02"],
    "000003": ["AAPL", "预留03"], 
    "000004": ["TSLA", "预留04"],
    "000005": ["MSFT", "预留05"],
    "000006": ["GOOG", "预留06"],
    "000007": ["META", "预留07"],
    "000008": ["AMZN", "预留08"],
    "000009": ["TSM",  "预留09"],
    "000010": ["ASML", "预留10"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
# =====================================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    report_lines = [
        f"通知：Alpha 溢价监控 ({now.strftime('%H:%M')})",
        "---"
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name = info
        
        # 逻辑修复：只有当代码不是 00000x 开头时才进行监控和显示
        if code.startswith("00000"):
            continue
            
        try:
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", 
                                 headers={'User-Agent': 'Mozilla/5.0'},
                                 timeout=10)
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 确认去除所有星号，保证纯净列表格式
            report_lines.append(f"• {name} ({code}): {ovs_change:+.2%}")
            
        except:
            report_lines.append(f"• {name} ({code}): 获取失败")

    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={
            "msg_type": "text", 
            "content": {"text": "\n".join(report_lines)}
        })

if __name__ == "__main__":
    run_task()
