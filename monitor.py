import os, re, requests, json

# 配置
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
    sz_results = []
    sh_results = []
    
    # --- 1. 深交所：完全独立的计算闭环 ---
    for code in ["161116", "160416"]:
        try:
            r = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5).text
            nav = float(re.search(r'dwjz":"(.*?)"', r).group(1))
            mp = float(requests.get(f"http://qt.gtimg.cn/q=sz{code}", timeout=5).text.split('~')[3])
            asset = get_market_data(FUND_CONFIG[code]['ticker'])
            est = nav * (1 + asset * FUND_CONFIG[code]['w'])
            sz_results.append({"name": FUND_CONFIG[code]["name"], "p1": (mp-nav)/nav, "p2": (mp-est)/est})
        except Exception as e: print(f"深交所{code}异常: {e}")

    # --- 2. 沪交所：完全独立的计算闭环 (彻底换源) ---
    try:
        code = "501225"
        # 换源：直接抓取天天基金沪市专用页面内容，不再请求 API
        url = "https://fund.eastmoney.com/501225.html"
        r = requests.get(url, timeout=10).text
        # 从页面直接正则获取单位净值，最稳健
        nav = float(re.search(r'data-value="(\d+\.\d+)"', r.split('单位净值')[1][:20]).group(1))
        mp = float(requests.get(f"http://qt.gtimg.cn/q=sh{code}", timeout=5).text.split('~')[3])
        asset = get_market_data(FUND_CONFIG[code]['ticker'])
        est = nav * (1 + asset * FUND_CONFIG[code]['w'])
        sh_results.append({"name": "全球芯片", "p1": (mp-nav)/nav, "p2": (mp-est)/est})
    except Exception as e: print(f"沪交所501225异常: {e}")

    # --- 3. 独立渲染 (绝对不会混淆) ---
    html_content = "<html><body>"
    for item in sz_results + sh_results:
        html_content += f'<div class="row"><b>{item["name"]}</b>: {item["p1"]:.2%} ~ {item["p2"]:.2%}</div>'
    html_content += "</body></html>"
    
    with open("index.html", "w", encoding="utf-8") as f: f.write(html_content)

if __name__ == "__main__": run()
