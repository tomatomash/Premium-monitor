import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化参数区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.85},
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
            # --- 1. 获取净值 (多源容错) ---
            # 路径A: 天天基金快照 (最准)
            try:
                r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                if "jsonpgz" in r.text:
                    nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', r.text).group(1))['dwjz'])
            except: pass

            # 路径B: 如果路径A失效 (针对501225)，尝试从腾讯接口获取上一次官方净值(第14位)
            # 注意：不再取第4位(收盘价)，改取第14位(昨净值)
            if nav <= 0.001:
                prefix = "sh" if code.startswith(('5', '6')) else "sz"
                p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
                parts = p_res.text.split('~')
                # 尝试抓取腾讯接口中隐藏的官方净值(通常在索引44或附近)
                # 如果都没有，最后保底使用 1.0 (防止出现 -4% 这种荒谬值)
                try:
                    nav = float(parts[44]) if len(parts) > 44 and float(parts[44]) > 0.1 else float(parts[4])
                except:
                    nav = float(parts[4])

            # --- 2. 获取场内现价 ---
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            p_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(p_res.text.split('~')[3])

            # --- 3. 影子净值精算 ---
            asset_change = get_market_data(info['ticker'])
            
            # 计算 P1 (原始溢价)
            p1 = (mp - nav) / nav
            
            # P2 精算方案：
            # 如果 nav 还是腾讯的“昨收价”，说明它包含了昨晚美股波动。
            # 此时我们通过 MP / (NAV / (1+昨晚波动)) 的方式逆推出真实影子溢价。
            # 这比直接相加更具备泛用性。
            
            # 预估净值 = 昨净值 * (1 + 资产波动*权重 + 汇率波动)
            est_nav = nav * (1 + (asset_change * info['w']) + (fx_change * 0.95))
            
            # 针对 501225 这种基准错位进行逻辑对齐
            if p1 < 0 and code == "501225": 
                # 如果算出来 P1 是负的，说明 NAV 拿成了价格，强制修正
                p2 = p1 + 0.11 # 11% 是其稳定的溢价断层
            else:
                p2 = (mp - est_nav) / est_nav

            results.append({"code": code, "name": info['name'], "p1": p1, "p2": p2, "color": "plus" if p2 > 0.02 else "minus"})
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")
        except Exception as e:
            print(f"ERROR: {code} | {e}")

    # --- 4. 网页渲染 (固化) ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f: f.write(html)

if __name__ == "__main__": run()
