import os
import requests
from datetime import datetime
import pytz
import time

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
}

WEBHOOK_URL = os.getenv('FEISHU_URL')

def get_price_data(ticker):
    """尝试从雅虎财经获取数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    for _ in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                result = response.json()['chart']['result'][0]['meta']
                current = result.get('regularMarketPrice')
                previous = result.get('previousClose')
                if current and previous:
                    return (current / previous) - 1
            time.sleep(2)
        except:
            pass
    return None

def generate_html(data_list, update_time):
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alpha 溢价看板</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; background: #f0f2f5; display: flex; justify-content: center; padding: 20px; }}
            .card {{ background: white; padding: 24px; border-radius: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.05); width: 100%; max-width: 400px; }}
            h2 {{ color: #1a1a1a; display: flex; align-items: center; gap: 8px; margin-top: 0; }}
            .time {{ font-size: 13px; color: #8c8c8c; margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 12px; }}
            .item {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #f5f5f5; }}
            .plus {{ color: #cf1322; font-weight: bold; }}
            .minus {{ color: #389e0d; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>📈 Alpha 实时监控</h2>
            <div class="time">最后更新: {update_time}</div>
            {data_list if data_list else '<div>正在等待数据抓取...</div>'}
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now_str = datetime.now(sh_tz).strftime('%H:%M:%S')
    
    feishu_report = [f"通知：Alpha 溢价监控 ({now_str})", "---"]
    html_items = []
    
    for code, (ticker, name) in FUND_CONFIG.items():
        change = get_price_data(ticker)
        if change is not None:
            sign = "+" if change >= 0 else ""
            color = "plus" if change >= 0 else "minus"
            text = f"{sign}{change:.2%}"
            feishu_report.append(f"• {name} ({code}): {text}")
            html_items.append(f'<div class="item"><span>{name}</span><span class="{color}">{text}</span></div>')
        else:
            feishu_report.append(f"• {name} ({code}): 获取失败")

    # 修复后的飞书请求代码
    if WEBHOOK_URL:
        payload = {
            "msg_type": "text",
            "content": {"text": "\n".join(feishu_report)}
        }
        requests.post(WEBHOOK_URL, json=payload)
    
    generate_html("".join(html_items), now_str)

if __name__ == "__main__":
    run_task()
