import os, re, requests, pytz, json
from datetime import datetime

# ==================== 泛用参数配置 ====================
# 这里只有权重 w，不再有硬编码的补偿值 offset
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
            is_static_nav = False # 核心标志位：判断 nav 是静态净值还是动态收盘价

            # --- 1. 获取净值基准 (逻辑自洽方案) ---
            # 优先尝试从天天基金获取 T-1 静态净值
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            if "jsonpgz" in nav_res.text:
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                is_static_nav = True # 拿到了 T-1 净值，需要叠加海外涨幅
            else:
                # 备用：从腾讯获取昨收价 (对于场内LOF，昨收价通常已含部分美股波动)
                prefix = "sh" if code.startswith(('5', '6')) else "sz"
                p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
                nav = float(p_res.text.split('~')[4]) # 昨收价
                is_static_nav = False # 拿的是昨收价，海外波动计算需谨慎对齐

            # --- 2. 获取场内现价 ---
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(price_res.text.split('~')[3])

            # --- 3. 泛用算法模型 ---
            asset_change = get_market_data(info['ticker'])
            
            # 影子净值计算逻辑优化：
            # 如果 nav 是静态的(T-1)，我们需要叠加完整的 asset_change。
            # 如果 nav 是动态昨收价(T)，asset_change 只应计算美股相对于昨收的额外增量(这里简化为 0 或微调)。
            if is_static_nav:
                # 标准公式
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
            else:
                # 备用公式：既然 nav 已经是包含美股收盘波动的“昨收价”了，
                # 我们只需要考虑 T 日当天的实时动态修正。
                est_nav = nav * (1 + (fx_change * 0.95))

            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} (Static:{is_static_nav}) -> P2:{p2:.2%}")
        except Exception as e:
            print(f"ERROR: {code} | {e}")

    # --- 4. 固化渲染 ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha (自动对齐版)</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
