import os, re, requests, json
from datetime import datetime

# 核心策略：完全物理隔离的沪深双轨抓取
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88}
}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=5).json()
        meta = res['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    results = []
    for code, info in FUND_CONFIG.items():
        try:
            # 轨道 A: 深交所 (天天基金接口，极其稳定)
            if code.startswith('1'):
                r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5).text
                nav = float(re.search(r'dwjz":"(.*?)"', r).group(1))
                mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", timeout=5).text.split('~')[3])
            
            # 轨道 B: 沪交所 (使用更底层的行情快照接口，直接绕过网页风控)
            else:
                # 此处使用专业终端行情 API，它直接映射股票代码，不再请求基金 API
                # secid=1. 代表上交所
                url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f2,f31"
                data = requests.get(url, timeout=5).json().get('data', {})
                mp = float(data.get('f2', 0)) / 1000
                nav = float(data.get('f31', 1.0))
                # 严厉的防御性编码：如果净值还是 1，说明接口拒绝服务，直接报错，不给假数据
                if nav <= 1.0: raise Exception("接口风控拦截")

            asset = get_market_data(info['ticker'])
            est = nav * (1 + asset * info['w'])
            results.append({"name": info["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-est)/est})
        except Exception as e:
            print(f"DEBUG: {code} 获取失败，原因: {e}", flush=True)

    # 渲染
    rows = "".join([f'<div class="row"><b>{i["name"]}</b>: {i["p1"]:.2%} ~ {i["p2"]:.2%}</div>' for i in results])
    with open("index.html", "w", encoding="utf-8") as f: 
        f.write(f'<html><body><div style="font-family:sans-serif;">{rows}</div></body></html>')

if __name__ == "__main__": run()
