import os, re, requests, pytz, json
from datetime import datetime

# ==================== 精准校准区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.98},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.88}, # 进一步收缩权重以对齐 10.7% 口径
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.90},
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        d = res.json()['chart']['result'][0]['meta']
        # 严格对比收盘价
        return (d['regularMarketPrice'] / d['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # --- 1. 强力获取净值 (解决 501225 报错) ---
            nav = 0.0
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            
            # 只有当返回包含 jsonpgz 且不为空时才解析
            if "jsonpgz" in nav_res.text and len(nav_res.text) > 20:
                try:
                    nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                except: nav = 0.0
            
            # 如果 nav 还是 0 (比如 501225 报错时)，从腾讯财经获取昨收价
            if nav <= 0.01:
                p_url = f"http://qt.gtimg.cn/q={'sh' if code.startswith(('5', '6')) else 'sz'}{code}"
                p_res = requests.get(p_url, headers=HEADERS, timeout=5)
                nav = float(p_res.text.split('~')[4]) # 腾讯接口的第5位是“昨收价”

            # --- 2. 获取场内现价 ---
            p_url = f"http://qt.gtimg.cn/q={'sh' if code.startswith(('5', '6')) else 'sz'}{code}"
            p_res = requests.get(p_url, headers=HEADERS, timeout=5)
            mp = float(p_res.text.split('~')[3])

            # --- 3. 算法校准 ---
            asset_change = get_market_data(info['ticker'])
            
            # P1 静态: 直接对比
            p1 = (mp - nav) / nav
            
            # P2 动态: 采用折算系数
            # 算法优化：考虑到 QDII 基金的管理费和调仓损耗，资产涨幅需要乘以权重 w
            est_nav = nav * (1 + (asset_change * info['w']) + (fx_change * info['w']))
            p2 = (mp - est_nav) / est_nav

            results.append({"code": code, "name": info['name'], "p1": p1, "p2": p2, "color": "plus" if p2 > 0.02 else "minus"})
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")
        except Exception as e:
            print(f"FAILED: {code} | 原因: {e}")

    # --- 4. 网页渲染 (保持固化格式) ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;}}.plus{{color:red;}}.minus{{color:green;}}</style></head><body><div style="max-width:500px;margin:auto;"><h3>溢价精算版</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
