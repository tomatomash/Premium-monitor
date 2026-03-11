import os
import requests
from datetime import datetime
import pytz

# ==================== 监控池 ====================
FUND_CONFIG = {
    "162411": ["XOP",  "华宝油气"],
    "160216": ["USO",  "原油LOF"],
    "160416": ["XLE",  "南方原油"],
    "159509": ["NVDA", "纳指科技"],
    "501225": ["SOXX", "全球芯片"],
    "161128": ["XLK",  "标普科技"],
    "161129": ["XBI",  "生物科技"],
    "164906": ["KWEB", "中概互联"],
    "161125": ["IVV",  "标普500"],
    "513500": ["IVV",  "标普500ETF"],
    "161127": ["QQQ",  "纳指100"],
    "513100": ["QQQ",  "纳指ETF"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
# ===============================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    # 头部保留关键词“通知”
    report_lines = [
        f"通知：📊 **Alpha 溢价监控 ({now.strftime('%H:%M')})**",
        "---"
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name = info
        try:
            # 抓取海外实时波动
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", 
                                 headers={'User-Agent': 'Mozilla/5.0'},
                                 timeout=10)
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 使用列表点 (•) 保持整齐，一行一个标的
            report_lines.append(f"• {name} ({code}): **{ovs_change:+.2%}**")
            
        except:
            report_lines.append(f"• {name} ({code}): ❌ 获取失败")

    # 发送汇总列表
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={
            "msg_type": "text", 
            "content": {"text": "\n".join(report_lines)}
        })

if __name__ == "__main__":
    run_task()
