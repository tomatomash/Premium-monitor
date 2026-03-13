import os, re, requests, json
from datetime import datetime

# 基础配置
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        d = res.json()['chart']['result'][0]['meta']
        return (d['regularMarketPrice'] / d['previousClose']) - 1
    except: return 0.0

def run():
    results = []
    
    # --- 1. 处理深市 (稳如泰山) ---
    for code in ["161116", "160416"]:
        try:
            info = FUND_CONFIG[code]
            r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', r.text).group(1))['dwjz'])
            mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5).text.split('~')[3])
            asset = get_market_data(info['ticker'])
            est = nav * (1 + asset * info['w'])
            results.append({"name": info["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
        except Exception as e: print(f"深市{code}故障: {e}")

    # --- 2. 处理沪市 (正则网页提取法，绕过 API 风控) ---
    try:
        code = "501225"
        info = FUND_CONFIG[code]
        # 直接抓取新浪基金页面的原始 HTML
        url = f"https://finance.sina.com.cn/fund/quotes/{code}/nav.shtml"
        r = requests.get(url, headers=HEADERS, timeout=8)
        # 利用正则从 HTML 文本中直接提取最新单位净值，避开 API 格式检查
        nav_match = re.search(r'单位净值.*?(\d+\.\d+)', r.text)
        nav = float(nav_match.group(1)) if nav_match else 1.0
        
        mp = float(requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5).text.split('~')[3])
        asset = get_market_data(info['ticker'])
        est = nav * (1 + asset * info['w'])
        results.append({"name": info["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
    except Exception as e: print(f"沪市501225故障: {e}")

    # 渲染部分...
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {"plus" if i["p2"]>0.02 else "minus"}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    with open("index.html", "w", encoding="utf-8") as f: f.write(f'<!DOCTYPE html><html><body><div style="font-family:sans-serif;">{rows}</div></body></html>')

if __name__ == "__main__": run()
