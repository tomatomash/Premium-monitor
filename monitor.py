import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化参数区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, # 再次下调权重以对齐 10% 口径
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.85}, # 权重校准
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        d = res.json()['chart']['result'][0]['meta']
        # 强制使用 regularMarketPrice (常规交易市价) 对齐
        return (d['regularMarketPrice'] / d['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # --- 1. 获取净值 (恢复最稳健的路径) ---
            nav = 0.0
            # 501225 这种容易报错的，我们优先或直接使用腾讯昨收价作为 NAV 估算
            if code == "501225":
                p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5)
                nav = float(p_res.text.split('~')[4]) # 昨收价
            else:
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                if "jsonpgz" in nav_res.text:
                    nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                else:
                    p_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                    nav = float(p_res.text.split('~')[4])

            # --- 2. 获取场内现价 ---
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(price_res.text.split('~')[3])

            # --- 3. 精算模型：复合折算 ---
            asset_change = get_market_data(info['ticker'])
            
            # 使用乘法折算模型，并引入 0.95 的汇率折算率
            # Est_NAV = nav * (1 + 资产变动*权重) * (1 + 汇率变动*0.95)
            est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
            
            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")
        except Exception as e:
            print(f"ERROR: {code} 环节故障: {e}")

    # --- 4. 网页渲染 (固化) ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
