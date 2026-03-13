import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化配置 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99}, # 黄金仓位极高，调至0.99
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.90}, # 石油调低权重至0.90，符合她理财口径
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.92},
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    """锁定常规交易价格，剔除盘后噪音"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()['chart']['result'][0]['meta']
        # 强制使用 regularMarketPrice 对比 previousClose，这是专业平台对齐净值的做法
        return (data.get('regularMarketPrice', 0) / data.get('previousClose', 1)) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # --- 1. 获取净值 (带容错) ---
            nav = 0.0
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            nav_match = re.search(r'jsonpgz\((.*?)\);', nav_res.text)
            
            if nav_match:
                nav = float(json.loads(nav_match.group(1))['dwjz'])
            else:
                # 备用方案：如果天天基金接口失效，尝试从腾讯价格接口取“昨收价”作为净值
                prefix = "sh" if code.startswith(('5', '6')) else "sz"
                price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
                nav = float(price_res.text.split('~')[4]) # 第4个位置通常是昨收价

            # --- 2. 获取场内实时价格 ---
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            parts = price_res.text.split('~')
            mp = float(parts[3])

            # --- 3. 精算逻辑 (Est_NAV) ---
            asset_change = get_market_data(info['ticker'])
            # 算法优化：将汇率和资产变动解耦，更贴近场内净值折算逻辑
            est_nav = nav * (1 + (asset_change * info['w']) + (fx_change * info['w']))

            p1 = (mp - nav) / nav
            p2 = (mp - est_nav) / est_nav

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")
        except Exception as e:
            print(f"FAILED: {code} 报错: {e}")

    # --- 4. 固化页面发布渲染 ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价率精算监控</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
