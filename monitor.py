import os, re, requests, pytz, json
from datetime import datetime

# ==================== 泛用参数配置 ====================
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
            is_static_nav = False # 判断 nav 是静态 T-1 净值还是动态昨收价

            # --- 1. 获取净值基准 ---
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            if "jsonpgz" in nav_res.text:
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                is_static_nav = True # 拿到了 T-1 净值，需要叠加海外涨幅
            else:
                # 备用：从腾讯获取昨收价
                p_res = requests.get(f"http://qt.gtimg.cn/q={'sh' if code.startswith(('5', '6')) else 'sz'}{code}", headers=HEADERS, timeout=5)
                nav = float(p_res.text.split('~')[4]) 
                is_static_nav = False # 昨收价已含海外波动，算法需调整

            # --- 2. 获取场内现价 ---
            p_res = requests.get(f"http://qt.gtimg.cn/q={'sh' if code.startswith(('5', '6')) else 'sz'}{code}", headers=HEADERS, timeout=5)
            mp = float(p_res.text.split('~')[3])

            # --- 3. 影子净值精算逻辑 ---
            asset_change = get_market_data(info['ticker'])
            
            if is_static_nav:
                # 场景A：有 T-1 净值，计算：mp / (T-1净值 * T日资产波动 * T日汇率波动)
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
            else:
                # 场景B：没净值拿昨收价，由于昨收价已对齐美股收盘，只需计算“当日汇率”和“盘中额外溢价”
                # 此时 P2 应该更接近于 P1 的实时反馈
                est_nav = nav * (1 + (fx_change * 0.95))

            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav

            # --- 特殊修正：针对 501225 这种高度依赖影子净值的标的 ---
            # 如果是场景B且是501225，我们必须手动对齐它相对于 SOXX 的历史基准误差
            if not is_static_nav and code == "501225":
                 # 核心修正：501225 的场内价格通常比其账面昨收价高出约 10% 的预估净值差
                 p2 = p1 + (asset_change * info['w'])

            results.append({"code": code, "name": info['name'], "p1": p1, "p2": p2, "color": "plus" if p2 > 0.02 else "minus"})
            print(f"CHECK: {code} {info['name']} (Static:{is_static_nav}) -> P2:{p2:.2%}")
        except Exception as e:
            print(f"ERROR: {code} | {e}")

    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha (逻辑自适应版)</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
