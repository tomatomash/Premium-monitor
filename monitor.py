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
            # 轨道 A：深市 (16/15等) - 物理封箱，绝对不动
            # ---------------------------------------------------------
            if not code.startswith('5'):
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                p_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p1, p2 = (mp - nav) / nav, (mp - est_nav) / est_nav

            # ---------------------------------------------------------
            # 轨道 B：沪市 (5开头) - 双重专业源并发抓取
            # ---------------------------------------------------------
            else:
                nav = 0.0
                # --- 源 1: 腾讯基金净值专用接口 (专治沪市延迟) ---
                try:
                    t_url = f"https://proxy.finance.qq.com/fundapi/v1/fund/nav?code={code}"
                    t_res = requests.get(t_url, headers=HEADERS, timeout=5).json()
                    nav = float(t_res['data']['nav']['nav']) # 提取官方净值
                except: pass

                # --- 源 2: 东方财富数据中心 (备份) ---
                if nav <= 0.01:
                    try:
                        em_url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f31"
                        em_data = requests.get(em_url, headers=HEADERS, timeout=5).json().get('data')
                        if em_data and em_data.get('f31') != "-":
                            nav = float(em_data['f31'])
                    except: pass
                
                # --- 现价抓取 (通用) ---
                p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])

                # --- 运算公式 (与深市完全对齐) ---
                asset_change = get_market_data(info['ticker'])
                # 如果所有源都拿不到 T-1 净值，nav 默认为 1.0 以防止崩溃，但这种情况极少
                if nav <= 0.01: nav = 1.0 
                
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p1, p2 = (mp - nav) / nav, (mp - est_nav) / est_nav

            results.append({"code": code, "name": info['name'], "p1": p1, "p2": p2, "color": "plus" if p2 > 0.02 else "minus"})
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")

        except Exception as e:
            print(f"ERROR: {code} 轨道故障: {e}")

    # --- 渲染逻辑固化 ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
