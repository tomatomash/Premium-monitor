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
            # ---------------------------------------------------------
            # 轨道 A：深市 (16/15) - 绝对封箱，不动
            # ---------------------------------------------------------
            if not code.startswith('5'):
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                p_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p1, p2 = (mp - nav) / nav, (mp - est_nav) / est_nav
                results.append({"name": info['name'], "code": code, "p1": p1, "p2": p2, "tag": ""})

            # ---------------------------------------------------------
            # 轨道 B：沪市 (5开头) - 双源并列对比模式
            # ---------------------------------------------------------
            else:
                asset_change = get_market_data(info['ticker'])
                p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])

                # --- 源 1: 腾讯专业接口 ---
                try:
                    t_res = requests.get(f"https://proxy.finance.qq.com/fundapi/v1/fund/nav?code={code}", timeout=5).json()
                    nav_t = float(t_res['data']['nav']['nav'])
                    est_t = nav_t * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                    results.append({"name": info['name'], "code": f"{code}(腾讯)", "p1": (mp-nav_t)/nav_t, "p2": (mp-est_t)/est_t, "tag": "TX"})
                except: pass

                # --- 源 2: 东方财富接口 ---
                try:
                    em_url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f31"
                    em_res = requests.get(em_url, timeout=5).json().get('data')
                    if em_res and em_res.get('f31') != "-":
                        nav_em = float(em_res['f31'])
                        est_em = nav_em * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                        results.append({"name": info['name'], "code": f"{code}(东财)", "p1": (mp-nav_em)/nav_em, "p2": (mp-est_em)/est_em, "tag": "EM"})
                except: pass

        except Exception as e:
            print(f"ERROR: {code} 故障: {e}")

    # --- 网页渲染 (固化) ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {"plus" if i["p2"] > 0.02 else "minus"}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha (双源对比版)</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
