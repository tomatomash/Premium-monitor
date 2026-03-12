import requests, re, json

# 配置：基金代码、挂钩标的、折算权重(w)
FUND_CONFIG = {
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.95},
    "161130": {"name": "纳指生物", "ticker": "IBB", "w": 0.95},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.90},
}

def get_market_data(ticker):
    """获取海外实时涨幅"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=10).json()
        meta = res['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    # 假设汇率波动 (可根据实际情况替换为实时获取)
    fx_change = 0.001 
    
    for code, info in FUND_CONFIG.items():
        # 1. 获取场内净值(NAV)和市场价格(MP)
        nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5)
        nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
        
        prefix = "sh" if code.startswith(('5', '6')) else "sz"
        price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=5)
        mp = float(price_res.text.split('~')[3])

        # 2. 计算动态溢价所需的数据
        us_change = get_market_data(info['ticker'])
        est_nav = nav * (1 + (us_change + fx_change) * info['w'])

        # 3. 计算双口径
        p1 = (mp - nav) / nav
        p2 = (mp - est_nav) / est_nav

        print(f"[{info['name']}] P1(静态): {p1:.2%}, P2(动态): {p2:.2%}")

if __name__ == "__main__":
    run()
