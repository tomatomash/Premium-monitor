import os, re, requests, json
from datetime import datetime

# 基础配置
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
}
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        d = res.json()['chart']['result'][0]['meta']
        return (d['regularMarketPrice'] / d['previousClose']) - 1
    except: return 0.0

def run():
    results = []
    
    # --- 1. 处理深市 (封箱逻辑) ---
    for code in ["161116", "160416"]:
        try:
            info = FUND_CONFIG[code]
            r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', r.text).group(1))['dwjz'])
            mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5).text.split('~')[3])
            
            asset = get_market_data(info['ticker'])
            est = nav * (1 + asset * info['w'])
            results.append({"name": info["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
        except Exception as e:
            print(f"深市故障: {e}")

    # --- 2. 独立处理沪市 (完全隔离，互不影响) ---
    try:
        code = "501225"
        info = FUND_CONFIG[code]
        # 使用腾讯基金详细页接口，此接口无需复杂授权
        r = requests.get(f"https://proxy.finance.qq.com/fundapi/v1/fund/nav?code={code}", headers=HEADERS, timeout=5)
        data = r.json()['data']['nav']
        nav = float(data['nav'])
        mp = float(requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5).text.split('~')[3])
        
        asset = get_market_data(info['ticker'])
        est = nav * (1 + asset * info['w'])
        results.append({"name": info["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
    except Exception as e:
        print(f"沪市故障: {e}")

    # 渲染
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {"plus" if i["p2"]>0.02 else "minus"}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    with open("index.html", "w", encoding="utf-8") as f: 
        f.write(f'<!DOCTYPE html><html><body><div style="font-family:sans-serif;">{rows}</div></body></html>')

if __name__ == "__main__": run()
