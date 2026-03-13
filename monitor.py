import requests, json

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
    final_output = []
    
    # 1. 统一数据源：放弃正则，全部使用标准的 JS 数据文件 (Fundgz 接口)
    for code, info in FUND_CONFIG.items():
        try:
            # 深市用 fundgz, 沪市用东方财富的基金配置文件
            url = f"http://fundgz.1234567.com.cn/js/{code}.js" if code.startswith('1') else f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
            r = requests.get(url, timeout=8).text
            
            if code.startswith('1'):
                nav = float(json.loads(r.split('jsonpgz(')[1].split(');')[0])['dwjz'])
            else:
                # 沪市专用：解析 Data_currentNetAssetPerShare
                nav = float(r.split('Data_currentNetAssetPerShare=[')[1].split(']')[0].split('"')[1])
            
            market_type = 'sz' if code.startswith('1') else 'sh'
            mp = float(requests.get(f"http://qt.gtimg.cn/q={market_type}{code}", timeout=5).text.split('~')[3])
            
            asset = get_market_data(info['ticker'])
            est = nav * (1 + asset * info['w'])
            
            # 严格计算 P1/P2，并手动赋予不同变量
            p1 = (mp - nav) / nav
            p2 = (mp - est) / est
            
            final_output.append(f'<div class="row"><b>{info["name"]}</b>: {p1:.2%} ~ {p2:.2%}</div>')
        except Exception as e:
            print(f"DEBUG: {code} 获取失败: {e}", flush=True)

    # 2. 独立写入，防止干扰
    with open("index.html", "w", encoding="utf-8") as f: 
        f.write(f'<html><body>{"".join(final_output)}</body></html>')

if __name__ == "__main__": run()
