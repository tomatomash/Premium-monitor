import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化参数区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        return (res.json()['chart']['result'][0]['meta']['regularMarketPrice'] / 
                res.json()['chart']['result'][0]['meta']['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    results = []
    
    for code, info in FUND_CONFIG.items():
        try:
            asset_change = get_market_data(info['ticker'])
            # 轨道 A：深市 (使用天天基金)
            if not code.startswith('5'):
                r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', r.text).group(1))['dwjz'])
                mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5).text.split('~')[3])
            # 轨道 B：沪市 (使用强制容错 API)
            else:
                em_url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f2,f31"
                data = requests.get(em_url, headers=HEADERS, timeout=5).json().get('data', {})
                # 使用 .get(key, default) 彻底规避 KeyError
                mp = float(data.get('f2', 0)) / 1000
                nav = float(data.get('f31', 1.0))
                if mp == 0 or nav == 0: # 如果依然抓不到，尝试备用接口
                    nav = 1.0
                    mp = float(requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5).text.split('~')[3])

            p1 = (mp - nav) / nav
            p2 = (mp - (nav * (1 + asset_change * info['w']))) / (nav * (1 + asset_change * info['w']))
            results.append({"name": info["name"], "code": code, "p1": p1, "p2": p2})
        except Exception as e:
            print(f"ERROR: {code} 轨道故障: {e}")

    # 渲染
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {"plus" if i["p2"]>0.02 else "minus"}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}</style></head><body>{rows}</body></html>'
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
