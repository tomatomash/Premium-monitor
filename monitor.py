import os
import requests
from datetime import datetime
import pytz
import time

# ==================== 监控配置中心 ====================
# base_nav: 请根据最新官方公告手动更新。
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
}

def get_us_change(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        m = res.json()['chart']['result'][0]['meta']
        return (m.get('regularMarketPrice') / m.get('previousClose')) - 1
    except:
        return 0.0

def get_cn_price(code):
    prefix = "sh" if code.startswith(('5', '6')) else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        res = requests.get(url, timeout=5)
        parts = res.text.split('~')
        if len(parts) > 3:
            return float(parts[3])
    except:
        pass
    return None

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now_str = datetime.now(tz).strftime('%H:%M:%S')
    rows = []

    for code, info in FUND_CONFIG.items():
        cn_price = get_cn_price(code)
        us_change = get_us_change(info['ticker'])
        
        if cn_price:
            est_nav = info['base_nav'] * (1 + us_change)
            premium = (cn_price / est_nav) - 1
            color = "plus" if premium > 0 else "minus"
            sign = "+" if premium > 0 else ""
            p_text = f"{sign}{premium:.2%}"
            
            row_html = f'<div class="row"><div><div class="name">{info["name"]}</div><div class="code">代码: {code}</div></div><div class="premium {color}">{p_text}</div></div>'
            rows.append(row_html)

    content_html = "".join(rows) if rows else '<div style="padding:40px; text-align:center; color:#999;">等待数据更新...</div>'

    final_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha 实时套利监控</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }}
        .container {{ max-width: 500px; margin: auto; background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: #1890ff; color: white; padding: 20px; text-align: center; }}
        .row {{ display: flex; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid #f0f0f0; align-items: center; }}
        .name {{ font-weight: 500; font-size: 16px; color: #1f1f1f; }}
        .code {{ font-size: 12px; color: #8c8c8c; margin-top: 2px; }}
        .premium {{ font-family: monospace; font-weight: 700; font-size: 18px; }}
        .plus {{ color: #cf1322; }}
        .minus {{ color: #389e0d; }}
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div style="font-size: 20px;
