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
        d = res.json()['chart']['result'][0]['meta']
        return (d['regularMarketPrice'] / d['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            asset_change = get_market_data(info['ticker'])
            
            # --- 统一计算轨道 ---
            if not code.startswith('5'):
                # 深市：使用 fundgz 接口 (稳)
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5).text.split('~')[3])
            else:
                # 沪市：使用东财行情接口的最新价(f2)和昨收净值(f31)
                # 再次尝试，这次我们要提取真实的净值分母
                em_url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f2,f31"
                data = requests.get(em_url, headers=HEADERS, timeout=5).json()['data']
                mp = float(data['f2'])/1000
                nav = float(data['f31'])
                # 如果 nav 小于 0.1，说明数据异常，强制修正为 1.0 (避免溢价100%)
                if nav < 0.1: nav = 1.0 

            # 统一公式
            est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav
            
            results.append({"name": info["name"], "code": code, "p1": p1, "p2": p2})
        except Exception as e:
            print(f"ERROR: {code} 故障: {e}")

    # --- 渲染 ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {"plus" if i["p2"]>0.02 else "minus"}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算</h3>{rows}</div></body></html>'
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
