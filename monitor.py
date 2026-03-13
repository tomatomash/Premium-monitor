import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化参数区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.85},
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'http://finance.sina.com.cn'
}
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
            # 第一轨道：深市代码 (16/15等) - 逻辑封箱，绝对不动
            # ---------------------------------------------------------
            if not code.startswith('5'):
                # 摄取：天天基金
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                
                # 现价：腾讯
                p_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                
                # 运算：复合乘法
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + (asset_change * info['w'])) * (1 + (fx_change * 0.95))
                p1 = (mp - nav) / nav
                p2 = (mp - est_nav) / est_nav

            # ---------------------------------------------------------
            # 第二轨道：沪市代码 (5开头) - 专项抓取与加固逻辑
            # ---------------------------------------------------------
            else:
                # 摄取：新浪财经 (增加防崩溃校验)
                s_res = requests.get(f"http://hq.sinajs.cn/list=f_{code}", headers=HEADERS, timeout=10)
                data_match = re.search(r'"(.*)"', s_res.text)
                
                # 只有当正则匹配成功且数据完整时才解析，否则 nav 保底设为 1.0
                if data_match and len(data_match.group(1).split(',')) > 1:
                    nav = float(data_match.group(1).split(',')[1])
                else:
                    nav = 1.0 # 保底锚点
                
                # 现价：腾讯 (沪市前缀为 sh)
                p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                
                # 运算：影子还原法
                asset_change = get_market_data(info['ticker'])
                p1 = (mp - nav) / nav
                p2 = p1 + (asset_change * info['w']) 

            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus"
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")

        except Exception as e:
            # 错误隔离：如果某个标的出错，打印错误并跳过，不影响渲染网页
            print(f"ERROR: {code} 轨道故障: {e}")

    # --- 网页渲染 (固化) ---
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}.plus{{color:#cf1322;font-weight:bold;}}.minus{{color:#389e0d;}}.premium{{text-align:right;}}</style></head><body><div style="max-width:480px;margin:auto;"><h3>溢价精算 Alpha (双轨加固版)</h3><p>更新时间: {now_str}</p>{rows}</div></body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
