import os, re, requests, pytz, json
from datetime import datetime

# ==================== 配置区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": {"GC=F": 0.5, "GDX": 0.5}, "w": 0.95},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.95},
    "162411": {"name": "华宝油气", "ticker": "XOP", "w": 0.95},
    "160216": {"name": "国泰原油", "ticker": "CL=F", "w": 0.95},
    "161129": {"name": "原油LOF", "ticker": "CL=F", "w": 0.95},
    "501018": {"name": "南方原油", "ticker": "CL=F", "w": 0.95},
    "160723": {"name": "嘉实原油", "ticker": "CL=F", "w": 0.95},
    "162719": {"name": "广发石油", "ticker": "XOP", "w": 0.95},
    "159509": {"name": "纳指科技", "ticker": "NQ=F", "w": 0.98},
    "161128": {"name": "标普科技", "ticker": "XLK", "w": 0.95},
    "162415": {"name": "生物科技", "ticker": "XBI", "w": 0.95},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.90},
    "164906": {"name": "中概互联", "ticker": "KWEB", "w": 0.95},
    "160644": {"name": "港美互联", "ticker": "KWEB", "w": 0.95},
    "161125": {"name": "标普500", "ticker": "ES=F", "w": 0.95},
    "513500": {"name": "标普ETF", "ticker": "ES=F", "w": 0.95},
    "161127": {"name": "纳指100", "ticker": "NQ=F", "w": 0.95},
    "513100": {"name": "纳指ETF", "ticker": "NQ=F", "w": 0.95},
    "160719": {"name": "嘉实黄金", "ticker": "GC=F", "w": 0.95},
    "161226": {"name": "国泰黄金", "ticker": "GC=F", "w": 0.95},
    "164701": {"name": "添富黄金", "ticker": "GC=F", "w": 0.95},
}

CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=10)
        meta = res.json()['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # 1. 抓取净值和价格
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5)
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=5)
            mp = float(price_res.text.split('~')[3])

            # 2. 海外变动
            us_change = 0.0
            if isinstance(info['ticker'], dict):
                for tk, weight in info['ticker'].items():
                    us_change += get_market_data(tk) * weight
            else:
                us_change = get_market_data(info['ticker'])

            # 3. 精算
            p1 = (mp - nav) / nav
            est_nav = nav * (1 + (us_change + fx_change) * info['w'])
            p2 = (mp - est_nav) / est_nav
            
            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0 else "minus"
            })
        except: continue

    # 4. 排序
    results.sort(key=lambda x: x['p2'], reverse=True)

    # 5. 渲染
    rows = []
    for item in results:
        rows.append(f'''
        <div class="row">
            <div><b>{item['name']}</b><br><small>{item['code']}</small></div>
            <div class="premium {item['color']}">{item['p1']:.2%} ~ {item['p2']:.2%}</div>
        </div>''')

    html_tpl = f"""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha 监控</title>
    <style>
        body {{ font-family: sans-serif; background: #f0f2f5; padding: 15px; }}
        .container {{ max-width: 600px; margin: auto; background: white; border-radius: 12px; shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }}
        .header {{ background: #1890ff; color: white; padding: 15px; text-align: center; }}
        .row {{ display: flex; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid #eee; }}
        .plus {{ color: #cf1322; }} .minus {{ color: #389e0d; }} .premium {{ font-weight: bold; }}
    </style>
    </head><body><div class="container">
        <div class="header">?? Alpha 跨境实时精算<br><small>更新时间: {now_str}</small></div>
        {"".join(rows)}
    </div></body></html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_tpl)

if __name__ == "__main__":
    run()
