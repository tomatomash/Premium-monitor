import os, re, requests, sys
from datetime import datetime

# 强制输出刷新，确保 GitHub Actions 能看到日志
sys.stdout.reconfigure(line_buffering=True)

FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82}, 
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
}

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=10).json()
        return (res['chart']['result'][0]['meta']['regularMarketPrice'] / 
                res['chart']['result'][0]['meta']['previousClose']) - 1
    except: return 0.0

def run():
    print("开始执行数据抓取...", flush=True)
    results = []
    
    # 深市：原样不动
    for code in ["161116", "160416"]:
        try:
            r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5)
            nav = float(re.search(r'dwjz":"(.*?)"', r.text).group(1))
            mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", timeout=5).text.split('~')[3])
            asset = get_market_data(FUND_CONFIG[code]['ticker'])
            results.append({"name": FUND_CONFIG[code]["name"], "code": code, "p1": (mp-nav)/nav, "p2": (mp-(nav*(1+asset*0.9)))/(nav*(1+asset*0.9))})
        except Exception as e: print(f"深市{code}异常: {e}", flush=True)

    # 沪市：使用权威的“历史行情导出”镜像接口
    # 该接口返回的是标准的文本表格数据，不容易被屏蔽
    try:
        code = "501225"
        # 使用 Eastmoney 数据中心导出接口，比 API 接口稳定得多
        url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
        r = requests.get(url, timeout=10)
        # 从该基金的 JS 数据文件中提取最新的 nav
        # Data结构: Data_currentNetAssetPerShare
        nav = float(re.search(r'Data_currentNetAssetPerShare=\[.*?,"(.*?)"', r.text).group(1))
        mp = float(requests.get(f"http://qt.gtimg.cn/q=sh{code}", timeout=5).text.split('~')[3])
        
        asset = get_market_data(FUND_CONFIG[code]['ticker'])
        p1 = (mp-nav)/nav
        p2 = (mp-(nav*(1+asset*0.88)))/(nav*(1+asset*0.88))
        results.append({"name": FUND_CONFIG[code]["name"], "code": code, "p1": p1, "p2": p2})
        print(f"沪市{code}计算成功: NAV={nav}, MP={mp}", flush=True)
    except Exception as e: print(f"沪市{code}获取失败: {e}", flush=True)

    # 渲染部分
    rows = "".join([f'<div class="row"><b>{i["name"]}</b>: {i["p1"]:.2%} ~ {i["p2"]:.2%}</div>' for i in results])
    with open("index.html", "w", encoding="utf-8") as f: f.write(f'<html><body>{rows}</body></html>')

if __name__ == "__main__": run()
