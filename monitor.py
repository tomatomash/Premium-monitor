import os
import requests
from datetime import datetime
import pytz

# ==================== 监控配置中心 ====================
# 填写指南： "国内代码": ["海外行情代码", "简称"]
# 海外代码去 Yahoo Finance 搜索，例如 纳斯达克100 是 QQQ，英伟达是 NVDA
FUND_CONFIG = {
    "162411": ["XOP",  "华宝油气"],
    "160216": ["USO",  "原油LOF"],
    "159509": ["NVDA", "纳指科技"],
    "501225": ["SOXX", "全球芯片"],
    "161129": ["XBI",  "生物科技"],
    "164906": ["KWEB", "中概互联"],
    # --- 以下为预留占位符，直接修改引号内的内容即可启用 ---
    "000001": ["SPY",  "备用标的01"], # 格式：国内基金代码 | 海外对标代码 | 自定义名称
    "000002": ["DIA",  "备用标的02"], # 比如想看道指，把 000002 改成对应 LOF 代码
    "000003": ["AAPL", "备用标的03"], 
    "000004": ["TSLA", "备ย用标的04"],
    "000005": ["MSFT", "备用标的05"],
    "000006": ["GOOG", "备用标的06"],
    "000007": ["META", "备用标的07"],
    "000008": ["AMZN", "备用标的08"],
    "000009": ["TSM",  "备用标的09"],
    "000010": ["ASML", "备用标的10"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
# =====================================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    # 头部保留关键词“通知”
    report_lines = [
        f"通知：Alpha 溢价监控 ({now.strftime('%H:%M')})",
        "---"
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name = info
        # 跳过测试用的占位代码
        if code == "000000" or name.startswith("备用"): continue
        
        try:
            # 获取海外实时波动
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", 
                                 headers={'User-Agent': 'Mozilla/5.0'},
                                 timeout=10)
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 纯文本列表，去除所有星号标识
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
