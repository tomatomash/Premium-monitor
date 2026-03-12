import os, re, requests, pytz, json
from datetime import datetime

FUND_CONFIG = {
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.95},
    "161130": {"name": "纳指生物", "ticker": "IBB", "w": 0.95},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.90},
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
            us_change = get_market_data(info['ticker'])
            
            p1 = (mp - nav) / nav
            est_nav = nav * (1 + (us_change + fx_change) * info['w'])
            p2 = (mp - est_nav) / est_nav
            results.append({"name": info['name'], "code": code, "p1": p1, "p2": p2, "color": "plus" if p2 > 0 else "minus"})
        except: continue

    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><body><div class="header">更新时间: {now_str}</div>{rows}</body></html>'
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
