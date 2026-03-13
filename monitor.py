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
        # --- 每个标的完全隔离，报错互不干扰 ---
        try:
            nav = 0.0
            is_static_nav = False 
            
            # 1. 尝试获取天天基金 T-1 静态净值
            try:
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                if nav_res.status_code == 200 and "jsonpgz" in nav_res.text:
                    match = re.search(r'jsonpgz\((.*?)\);', nav_res.text)
                    if match:
                        nav = float(json.loads(match.group(1))['dwjz'])
                        is_static_nav = True
            except: pass # 失败了就交给下面的备用方案

            # 2. 如果没拿到静态净值，强制使用腾讯接口昨收价
            if nav <= 0.001:
                prefix = "sh" if code.startswith(('5', '6')) else "sz"
                p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
                nav = float(p_res.text.split('~')[4])
                is_static_nav = False

            # 3. 获取场内现价
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(p_res.text.split('~')[3])

            # 4. 影子净值精算 (核心逻辑)
            asset_change = get_market_data(info['ticker'])
            
            if is_static_nav:
                # 基准是 T-1 净值，叠加完整海外变动
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
            else:
                # 基准是已包含昨晚变动的“昨收价”，P2 需通过 P1 叠加当日资产实时增量来还原影子溢价
                # 这种算法能自动对齐 10.8% 这种跳空缺口
                est_nav = nav * (1 + (fx_change * 0.95))
                # 针对影子净值缺失的补偿公式
                p2_boost = asset_change * info['w']
                p1 = (mp - nav) / nav
                p2 = p1 + p2_boost
                results.append({"name": info['name'], "code": code, "p1": p1, "p2": p2, "color": "plus" if p2 > 0.02 else "minus"})
                print(f"CHECK: {code} {info['name']} (Shadow) -> P2:{p2:.2%}")
                continue # 501225 走这个特殊分支

            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav
            results.append({"name": info['name'], "code": code, "p1": p1, "p2": p2, "color": "plus" if p2 > 0.02 else "minus"})
            print(f"CHECK: {code} {info['name']} (Static) -> P2:{p2:.2%}")

        except Exception as e:
            print(f"SKIP: {code} 发生错误: {e}")
            continue

    # --- 5. 渲染 HTML ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha (最终固化版)</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
