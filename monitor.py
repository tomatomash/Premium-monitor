import requests, re, json, time

FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88}
}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    results = []
    # 1. 深市逻辑 (保持现状)
    for code in ["161116", "160416"]:
        try:
            r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5).text
            nav = float(re.search(r'dwjz":"(.*?)"', r).group(1))
            mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", timeout=5).text.split('~')[3])
            asset = get_market_data(FUND_CONFIG[code]['ticker'])
            est = nav * (1 + asset * FUND_CONFIG[code]['w'])
            results.append({"name": FUND_CONFIG[code]["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
        except: pass

    # 2. 沪市逻辑 (更换至网易财经接口，无风控拦截)
    try:
        # 使用网易行情接口，它对所有 IP 开放，且无需 Referer
        code = "501225"
        # 此接口返回的是基金盘中净值
        url = f"https://api.money.126.net/data/feed/1{code},money.api"
        # 增加重试机制
        for _ in range(3):
            try:
                res = requests.get(url, timeout=8).text
                # 数据处理：从 JSONP 中提取净值 (网易数据源)
                match = re.search(r'"NAV":(\d+\.\d+)', res)
                nav = float(match.group(1))
                mp = float(requests.get(f"http://qt.gtimg.cn/q=sh{code}", timeout=5).text.split('~')[3])
                asset = get_market_data(FUND_CONFIG[code]['ticker'])
                est = nav * (1 + asset * FUND_CONFIG[code]['w'])
                results.append({"name": FUND_CONFIG[code]["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
                break 
            except: time.sleep(1)
    except Exception as e: print(f"DEBUG: 沪市{code}抓取失败: {e}", flush=True)

    # 渲染 (保持简洁)
    rows = "".join([f'<div class="row"><b>{i["name"]}</b>: {i["p1"]:.2%} ~ {i["p2"]:.2%}</div>' for i in results])
    with open("index.html", "w", encoding="utf-8") as f: f.write(f'<html><body>{rows}</body></html>')

if __name__ == "__main__": run()
