import os
import requests
from datetime import datetime
import pytz
import time

# ==================== 监控配置中心 ====================
# base_nav 为官方最新公布的单位净值，需根据公告定期更新以保持计算精准
# 数据参考日期：2026-03-09 前后
FUND_CONFIG = {
    "162411": {"name": "华宝油气", "ticker": "XOP",  "base_nav": 0.5420},
    "160216": {"name": "原油LOF", "ticker": "USO",  "base_nav": 0.8950},
    "160416": {"name": "南方原油", "ticker": "USO",  "base_nav": 1.1230},
    "159509": {"name": "纳指科技", "ticker": "IXN",  "base_nav": 1.4520},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "base_nav": 2.1464},
    "161128": {"name": "标普科技", "ticker": "XLK",  "base_nav": 1.2340},
    "161129": {"name": "生物科技", "ticker": "XBI",  "base_nav": 1.1560},
    "164906": {"name": "中概互联", "ticker": "KWEB", "base_nav": 0.9850},
    "161125": {"name": "标普500",  "ticker": "IVV",  "base_nav": 2.2190},
    "513500": {"name": "标普500ETF", "ticker": "IVV", "base_nav": 2.2190},
    "161127": {"name": "纳指100",  "ticker": "QQQ",  "base_nav": 1.8540},
    "513100": {"name": "纳指ETF",  "ticker": "QQQ",  "base_nav": 1.8540},
    "000004": {"name": "备用标的04", "ticker": "AAPL", "base_nav": 1.0000}, # 示例占位
    "000010": {"name": "预留10",   "ticker": "TSLA", "base_nav": 1.0000}, # 示例占位
}

WEBHOOK_URL = os.getenv('FEISHU_URL')

def get_us_change(ticker):
    """获取美股标的实时涨跌幅"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            m = res.json()['chart']['result'][0]['meta']
            return (m.get('regularMarketPrice') / m.get('previousClose')) - 1
    except:
        return 0.0
    return 0.0

def get_cn_price(code):
    """获取 A 股二级市场实时价格"""
    prefix = "sh" if code.startswith(('5', '6')) else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        res = requests.get(url, timeout=5)
        return float(res.text.split('~')[3])
    except:
        return None

def generate_html(items_html, update_time):
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alpha 专业套利监控</title>
        <style>
            body {{ font-family: sans-serif; background: #f4f7f9; padding: 15px; margin: 0; }}
            .container {{ max-width: 480px; margin: auto; background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; }}
            .header {{ background: #1890ff; color: white; padding: 15px; text-align: center; }}
            .time {{ font-size: 12px; opacity: 0.8; margin-top: 5px; }}
            .row {{ display: flex; justify-content: space-between; padding: 12px 15px; border-bottom: 1px solid #eee; align-items: center; }}
            .name-box {{ display: flex; flex-direction: column; }}
            .name {{ font-weight: bold; color: #333; }}
            .code {{ font-size: 11px; color: #999; }}
            .premium {{ font-family: monospace; font-weight: bold; font-size: 16px; }}
            .plus {{ color: #f5222d; }}
            .minus {{ color: #52c41a; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>🚀 Alpha 实时溢价监控</div>
                <div class="time">更新时间: {update_time}</div>
            </div>
            {items_html}
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now_str = datetime.now(tz).strftime('%H:%M:%S')
    
    feishu_lines = [f"【专业监控】实时溢价预警 ({now_str})", "---"]
    html_rows = []

    for code, info in FUND_CONFIG.items():
        cn_price = get_cn_price(code)
        us_change = get_us_change(info['ticker'])
        
        if cn_price:
            # 口径 2：实时估值溢价 = (A股价格 / (昨日净值 * (1 + 美股涨跌))) - 1
            est_nav = info['base_nav'] * (1 + us_change)
            premium = (cn_price / est_nav) - 1
            
            color_class = "plus" if premium > 0 else "minus"
            sign = "+" if premium > 0 else ""
            p_text = f"{sign}{premium:.2%}"
            
            feishu_lines.append(f"• {info['name']}({code}): {p_text}")
            html_rows.append(f'''
                <div class="row">
                    <div class="name-box">
                        <span class="name">{info['name']}</span>
                        <span class="code">代码: {code}</span>
                    </div>
                    <div class="premium {color_class}">{p_text}</div>
                </div>
            ''')

    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={{"msg_type": "text", "content": {{"text": "\\n".join(feishu_lines)}}}})
    
    generate_html("".join(html_rows), now_str)

if __name__ == "__main__":
    run_task()
# 修复后的飞书推送逻辑
    if WEBHOOK_URL:
        payload = {
            "msg_type": "text",
            "content": {
                "text": "\n".join(feishu_lines)
            }
        }
        try:
            requests.post(WEBHOOK_URL, json=payload, timeout=10)
        except Exception as e:
            print(f"推送失败: {e}")
