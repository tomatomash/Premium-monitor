import os, re, requests, pytz, json
from datetime import datetime

# ==================== 配置区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": {"GC=F": 0.5, "GDX": 0.5}, "w": 0.95},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.95},
    "162411": {"name": "华宝油气", "ticker": "XOP", "w": 0.95},
    # ... (其余配置保持不变)
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        meta = res.json()['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(price_res.text.split('~')[3])

            us_change = 0.0
            if isinstance(info['ticker'], dict):
                for tk, weight in info['ticker'].items():
                    us_change += get_market_data(tk) * weight
            else:
                us_change = get_market_data(info['ticker'])

            p1 = (mp - nav) / nav
            est_nav = nav * (1 + (us_change + fx_change) * info['w'])
            p2 = (mp - est_nav) / est_nav
            
            # 这里打印数据，方便你在 Actions 日志中核对
            print(f"DEBUG: {info['name']} | P1: {p1:.2%} | P2: {p2:.2%}")
            
            results.append({"code": code, "name": info['name'], "p1": p1, "p2": p2, "color": "plus" if p2 > 0 else "minus"})
        except Exception as e:
            print(f"Skipping {code}: {e}")
            continue

    results.sort(key=lambda x: x['p2'], reverse=True)
    # ... (后续渲染逻辑，保持你原来代码中完全一致即可)
