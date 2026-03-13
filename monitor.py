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
            # 轨道 A：深市 (16/15等) - 严格保持原始逻辑
            # ---------------------------------------------------------
            if not code.startswith('5'):
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                
                price_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                mp = float(price_res.text.split('~')[3])
                
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p1 = (mp - nav) / nav
                p2 = (mp - est_nav) / est_nav

            # ---------------------------------------------------------
            # 轨道 B：沪市 (5开头) - 启用东财专业 API (针对 501225 彻底解困)
            # ---------------------------------------------------------
            else:
                # 抓取东财沪深行情快照 (secid=1. 代表沪市)
                # 这个接口能返回真正的 f31:单位净值 和 f2:最新价
                url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f2,f31"
                em_res = requests.get(url, headers=HEADERS, timeout=5).json()['data']
                
                # 单位净值 (如果 f31 失效，则通过天天基金做二次兜底)
                nav = float(em_res['f31']) if em_res['f31'] != "-" else 0.0
                if nav <= 0:
                    try:
                        r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5)
                        nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', r.text).group(1))['dwjz'])
                    except: nav = 1.0 # 最后的保底
                
                mp = float(em_res['f2']) / 1000 if em_res['f2'] != "-" else 0.0
                if mp <= 0: # 备用现价来源
                    p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", timeout=5)
                    mp = float(p_res.text.split('~')[3])
                
                asset_change = get_market_data(info['ticker'])
                
                # 沪市逻辑完全镜像深市公式：实现真正的数据对齐
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p1 = (mp - nav) / nav
                p2 = (mp - est_nav) / est_nav

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")

        except Exception as e:
            print(f"ERROR: {code} 轨道故障: {e}")

    # --- 渲染逻辑固化 ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
