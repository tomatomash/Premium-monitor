import os
import re
import random
import requests
from datetime import datetime
import pytz
import time
import pickle

# ==================== 【回滚校正版】严格对应官方名称 ====================
FUND_CONFIG = {
    "160416": {"name": "石油基金", "ticker": "CL=F"},
    "160216": {"name": "国泰原油LOF", "ticker": "CL=F"},
    "161129": {"name": "原油LOF", "ticker": "CL=F"},
    "501018": {"name": "南方原油LOF(C)", "ticker": "CL=F"},
    "160723": {"name": "嘉实原油LOF", "ticker": "CL=F"},
    "162719": {"name": "广发石油LOF", "ticker": "XOP"},
    "162411": {"name": "华宝油气LOF", "ticker": "XOP"},
    "161116": {"name": "易方达黄金主题", "ticker": "GC=F"},
    "160719": {"name": "嘉实黄金LOF", "ticker": "GC=F"},
    "161226": {"name": "国泰黄金LOF", "ticker": "GC=F"},
    "164701": {"name": "汇添富黄金LOF", "ticker": "GC=F"},
    "501225": {"name": "全球芯片LOF", "ticker": "SOXX"},
    "159509": {"name": "纳指科技ETF", "ticker": "NQ=F"},
    "161128": {"name": "标普科技LOF", "ticker": "XLK"},
    "162415": {"name": "生物科技LOF", "ticker": "XBI"},
    "164906": {"name": "中概互联LOF", "ticker": "KWEB"},
    "160644": {"name": "港美互联网LOF", "ticker": "KWEB"},
    "161125": {"name": "标普500LOF", "ticker": "ES=F"},
    "513500": {"name": "标普500ETF", "ticker": "ES=F"},
    "161127": {"name": "纳指100LOF", "ticker": "NQ=F"},
    "513100": {"name": "纳指ETF", "ticker": "NQ=F"},
}

CACHE_FILE = "fund_cache.pkl"
CACHE_DURATION_SECONDS = 2 * 3600
CN_TZ = pytz.timezone('Asia/Shanghai')
USER_AGENT_POOL = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"]

HTML_TPL = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Alpha 监控回滚版</title><style>body {{ font-family: sans-serif; background: #f0f2f5; padding: 15px; }}.container {{ max-width: 600px; margin: auto; background: white; border-radius: 12px; shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}.header {{ background: #1890ff; color: white; padding: 15px; text-align: center; }}.row {{ display: flex; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid #eee; }}.plus {{ color: #cf1322; }}.minus {{ color: #389e0d; }}.premium {{ font-weight: bold; }}</style><meta http-equiv="refresh" content="60"></head><body><div class="container"><div class="header">📊 Alpha 全自动监控<br><small>更新时间: {now_str}</small></div>{content_html}</div></body></html>"""

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as f:
                data = pickle.load(f)
                return data if isinstance(data, dict) else {}
    except: return {}
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, 'wb') as f: pickle.dump(data, f)
    except: pass

def safe_request(url):
    try: return requests.get(url, headers={'User-Agent': random.choice(USER_AGENT_POOL)}, timeout=10)
    except: return None

def get_latest_official_nav(fund_code):
    cache = load_cache()
    api_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    res = safe_request(api_url)
    if res and (match := re.search(r'jsonpgz\((.*?)\);', res.text)):
        try:
            import json
            nav = float(json.loads(match.group(1))['dwjz'])
            cache[fund_code] = {'nav': nav, 'ts': time.time()}
            save_cache(cache)
            return nav
        except: pass
    return cache.get(fund_code, {}).get('nav')

def get_cn_fund_market_price(code):
    prefix = "sh" if code.startswith(('5', '6')) else "sz"
    res = safe_request(f"http://qt.gtimg.cn/q={prefix}{code}")
    if res and '~' in res.text:
        try: return float(res.text.split('~')[3])
        except: pass
    return None

def get_us_ticker_change(ticker):
    res = safe_request(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d")
    if res:
        try:
            meta = res.json()['chart']['result'][0]['meta']
            return (meta.get('regularMarketPrice') / meta.get('previousClose')) - 1
        except: pass
    return 0.0

def run_monitor_task():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for code, info in FUND_CONFIG.items():
        mp = get_cn_fund_market_price(code)
        nav = get_latest_official_nav(code)
        if mp and nav:
            p1 = (mp - nav) / nav
            est_nav = nav * (1 + get_us_ticker_change(info['ticker']))
            p2 = (mp - est_nav) / est_nav
            c = "plus" if p2 > 0 else "minus"
            rows.append(f'<div class="row"><div><b>{info["name"]}</b><br><small>{code}</small></div><div class="premium {c}">{p1:.2%}~{p2:.2% }</div></div>')
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(HTML_TPL.format(now_str=now_str, content_html="".join(rows)))

if __name__ == "__main__": run_monitor_task()
