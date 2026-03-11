import os
import requests
from datetime import datetime
import pytz

# ==================== 监控配置中心 ====================
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
    # --- 预留位：只要左边代码是 00000x，新逻辑会瞬间将其抹除 ---
    "000001": ["SPY",  "预留01"],
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
    
    # 【暴力修复】创建一个只包含真实代码的干净清单
    # 只要代码以 "00000" 开头，它甚至连进入循环的机会都没有
    clean_list = {k: v for k, v in FUND_CONFIG.items() if not k.startswith("00000")}
    
    for code, info in clean_list.items():
        ticker, name = info
        try:
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", 
                                 headers={'User-Agent': 'Mozilla/5.0'},
                                 timeout=10)
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
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
