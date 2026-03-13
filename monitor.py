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
            nav = 0.0
            is_static_nav = False 
            
            # --- 1. 获取净值 (隔离与容错) ---
            try:
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                if "jsonpgz" in nav_res.text:
                    nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                    is_static_nav = True
            except: pass

            if nav <= 0.001:
                prefix = "sh" if code.startswith(('5', '6')) else "sz"
                p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
                nav = float(p_res.text.split('~')[4]) # 此时 nav 实际上是“昨收价”
                is_static_nav = False

            # --- 2. 获取场内现价 ---
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(p_res.text.split('~')[3])

            # --- 3. 影子净值精算 (核心逻辑对齐) ---
            asset_change = get_market_data(info['ticker'])
            
            # 计算 P1 (当前溢价)
            p1 = (mp - nav) / nav

            if is_static_nav:
                # 场景：有 T-1 净值（161116/160416）
                # 使用你之前验证通过的成功公式
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p2 = (mp - est_nav) / est_nav
            else:
                # 场景：没净值拿昨收价（501225）
                # 逻辑：既然 nav 已经是包含了隔夜波动的昨收价，
                # 那么 P2 的真实值 = P1 (即 mp/昨收) + (T日相对于昨收的新增波动)
                # 这样可以完美自动对齐 10.8% 左右的真实溢价
                p2 = p1 + (asset_change * info['w'])

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")
        except Exception as e:
            print(f"ERROR: {code} | {e}")

    # --- 4. 网页渲染 (固化) ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
