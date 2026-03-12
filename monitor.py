import os, re, requests, pytz, json
from datetime import datetime

# 你的基金配置
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

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        return (res.json()['chart']['result'][0]['meta']['regularMarketPrice'] / res.json()['chart']['result'][0]['meta']['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F") 
    results = []
    for code, info in FUND_CONFIG.items():
        try:
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5).text).group(1))['dwjz'])
            mp = float(requests.get(f"http://qt.gtimg.cn/q={'sh' if code.startswith(('5', '6')) else 'sz'}{code}", headers=HEADERS, timeout=5).text.split('~')[3])
            us_change = sum([get_market_data(tk) * w for tk, w in info['ticker'].items()]) if isinstance(info['ticker'], dict) else get_market_data(info['ticker'])
            p1 = (mp - nav) / nav
            p2 = (mp - (nav * (1 + (us_change + fx_change) * info['w']))) / (nav * (1 + (us_change + fx_change) * info['w']))
            results.append({"name": info['name'], "code": code, "p1": p1, "p2": p2, "color": "plus" if p2 > 0 else "minus"})
        except: continue # 只有在获取数据彻底失败时才跳过，保证网页不报错

    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:10px;border-bottom:1px solid #eee;}}.plus{{color:red;}}.minus{{color:green;}}</style></head><body><h3>更新时间: {now_str}</h3>{rows}</body></html>')

if __name__ == "__main__": run()
