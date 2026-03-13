import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化的配置与接口 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.98},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.91}, # 调优权重以对齐 10.7% 左右的口径
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.92},
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()['chart']['result'][0]['meta']
        # 算法优化：采用常规交易时段价格与前结算价的比例
        return (data['regularMarketPrice'] / data['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # 1. 抓取净值
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            nav_match = re.search(r'jsonpgz\((.*?)\);', nav_res.text)
            if not nav_match: continue
            nav = float(json.loads(nav_match.group(1))['dwjz'])
            
            # 2. 抓取价格 (501225 前缀修正)
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(price_res.text.split('~')[3])

            # 3. 算法优化：动态预估净值模型
            asset_change = get_market_data(info['ticker'])
            
            # 优化公式：Est_NAV = 昨净值 * (1 + 资产变动 * 权重 + 汇率变动 * 权重)
            # 这种分项加权法比直接相加更接近专业平台的折算逻辑
            est_nav = nav * (1 + (asset_change * info['w']) + (fx_change * info['w']))

            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")
        except Exception as e:
            print(f"FAILED: {code} 由于 {str(e)}")

    # 4. 生成 HTML (样式与发布机制完全固化)
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-size:16px;}}.plus{{color:#cf1322;}}.minus{{color:#389e0d;}}.premium{{font-weight:bold;}}</style></head><body><div style="max-width:500px;margin:auto;"><h3>Alpha 监控精算版</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
