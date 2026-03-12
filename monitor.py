import os, re, requests, pytz, json
from datetime import datetime

# 保持你原来的配置区不变
FUND_CONFIG = {
    # ... (此处省略你的配置，保持完全一致)
}

CN_TZ = pytz.timezone('Asia/Shanghai')

# 添加 headers，这是 Actions 跑通此接口的关键
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10) # 加上 Header
        meta = res.json()['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # 使用你原来的逻辑，增加 header 伪装
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            # 严格按照你原来的解析方式
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
            
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(price_res.text.split('~')[3])

            # ... (后续计算逻辑保持不变)
            us_change = 0.0
            if isinstance(info['ticker'], dict):
                for tk, weight in info['ticker'].items():
                    us_change += get_market_data(tk) * weight
            else:
                us_change = get_market_data(info['ticker'])

            p1 = (mp - nav) / nav
            est_nav = nav * (1 + (us_change + fx_change) * info['w'])
            p2 = (mp - est_nav) / est_nav
            
            results.append({"code": code, "name": info['name'], "p1": p1, "p2": p2, "color": "plus" if p2 > 0 else "minus"})
        except Exception as e:
            print(f"Error for {code}: {e}")
            continue

    # ... (后续渲染逻辑保持不变)
