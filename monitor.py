import os, re, random, requests, pickle, time, pytz
from datetime import datetime

# ==================== 【最终完美回滚版】仅修正名称与格式报错 ====================
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
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_latest_official_nav(fund_code):
    api_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    try:
        res = requests.get(api_url, timeout=10)
        match = re.search(r'jsonpgz\((.*?)\);', res.text)
        if match:
            import json
            return float(json.loads(match.group(1))['dwjz'])
    except: pass
    return None

def get_cn_price(code):
    prefix = "sh" if code.startswith(('5', '6')) else "sz"
    try:
        res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=10)
        return float(res.text.split('~')[3])
    except: return None

def get_us_change(ticker):
    try:
        res = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d", timeout=10)
        meta = res.json()['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for code, info in FUND_CONFIG.items():
        mp = get_cn_price(code)
        nav = get_latest_official_nav(code)
        if mp and nav:
            p1 = (mp - nav) / nav
            p2 = (mp - (nav * (1 + get_us_change(info['ticker'])))) / (nav * (1 + get_us_change(info['ticker'])))
            color = "plus" if p2 > 0 else "minus"
            rows.append(f'<div class="row"><div><b>{info["name"]}</b><br><small>{code}</small></div><div class="premium {color}">{p1:.2%} ~ {p2:.2%}</div></div>')
    
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>监控</title><style>body {{ font-family: sans-serif; background: #f0f2f5; padding: 15px; }}.container {{ max-width: 600px; margin: auto; background: white; border-radius: 12px; }}.header {{ background: #1890ff; color: white; padding: 15px; text-align: center; }}.row {{ display: flex; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid #eee; }}.plus {{ color: #cf1322; }}.minus {{ color: #389e0d; }}.premium {{ font-weight: bold; }}</style></head><body><div class="container"><div class="header">📊 Alpha 全自动监控<br><small>更新时间: {now_str}</small></div>{"".join(rows)}</div></body></html>"""
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
