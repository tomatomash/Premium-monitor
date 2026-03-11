import os, re, random, requests, pytz
from datetime import datetime

# ==================== 【精算排序版】核心配置 ====================
# us_ticker: 最相关的海外标的
# weight: 海外资产仓位权重 (通常 0.9 - 0.95)
FUND_CONFIG = {
    # 石油/能源类 (以 XOP/CL=F 为准)
    "160416": {"name": "石油基金", "us_ticker": "XOP", "weight": 0.95},
    "162411": {"name": "华宝油气", "us_ticker": "XOP", "weight": 0.95},
    "160216": {"name": "国泰原油", "us_ticker": "CL=F", "weight": 0.95},
    "161129": {"name": "原油LOF", "us_ticker": "CL=F", "weight": 0.95},
    "501018": {"name": "南方原油", "us_ticker": "CL=F", "weight": 0.95},
    
    # 科技/宽基类 (以期货指数为准，捕捉盘中波动)
    "159509": {"name": "纳指科技", "us_ticker": "NQ=F", "weight": 0.98},
    "161128": {"name": "标普科技", "us_ticker": "XLK", "weight": 0.95},
    "161125": {"name": "标普500", "us_ticker": "ES=F", "weight": 0.95},
    "161127": {"name": "纳指100", "us_ticker": "NQ=F", "weight": 0.95},
    "513500": {"name": "标普ETF", "us_ticker": "ES=F", "weight": 0.95},
    "513100": {"name": "纳指ETF", "us_ticker": "NQ=F", "weight": 0.95},
    
    # 行业/中概类
    "501225": {"name": "全球芯片", "us_ticker": "SOXX", "weight": 0.85}, # 含有A股成分
    "164906": {"name": "中概互联", "us_ticker": "KWEB", "weight": 0.95},
    "162415": {"name": "生物科技", "us_ticker": "XBI", "weight": 0.95},
    
    # 黄金类
    "161116": {"name": "易基黄金", "us_ticker": "GC=F", "weight": 0.95},
    "160719": {"name": "嘉实黄金", "us_ticker": "GC=F", "weight": 0.95},
}

CN_TZ = pytz.timezone('Asia/Shanghai')

def get_official_nav(code):
    """从天天基金获取官方 T-1 净值"""
    try:
        url = f"http://fundgz.1234567.com.cn/js/{code}.js"
        res = requests.get(url, timeout=5)
        data = re.search(r'jsonpgz\((.*?)\);', res.text)
        import json
        return float(json.loads(data.group(1))['dwjz'])
    except: return None

def get_cn_price(code):
    """获取场内实时价格"""
    prefix = "sh" if code.startswith(('5', '6')) else "sz"
    try:
        res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=5)
        return float(res.text.split('~')[3])
    except: return None

def get_market_change(ticker):
    """获取雅虎财经标的/汇率实时变动"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=5)
        meta = res.json()['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run_monitor():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    results = []
    
    # 提前获取实时汇率变动 (美元兑人民币)
    fx_change = get_market_change("CNY=X")

    for code, info in FUND_CONFIG.items():
        nav = get_official_nav(code)
        mp = get_cn_price(code)
        us_change = get_market_change(info['us_ticker'])
        
        if nav and mp:
            # 口径 1: 基础溢价
            p1 = (mp - nav) / nav
            
            # 口径 2: 精算溢价 (趋近雪球/她理财逻辑)
            # 净值预估 = T-1净值 * (1 + (海外标的涨跌 + 汇率变动) * 权重)
            est_nav = nav * (1 + (us_change + fx_change) * info['weight'])
            p2 = (mp - est_nav) / est_nav
            
            results.append({
                "code": code,
                "name": info['name'],
                "p1": p1,
                "p2": p2,
                "color": "plus" if p2 > 0 else "minus"
            })

    # ==================== 排序逻辑：按口径2溢价率降序排列 ====================
    results.sort(key=lambda x: x['p2'], reverse=True)

    # 渲染 HTML
    rows = []
    for item in results:
        rows.append(f'''
        <div class="row">
            <div><b>{item['name']}</b><br><small>{item['code']}</small></div>
            <div class="premium {item['color']}">{item['p1']:.2%} ~ {item['p2']:.2%}</div>
        </div>''')

    html_content = f"""
    <!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Alpha 实时精算监控</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f5f5f7; padding: 20px; }}
        .container {{ max-width: 500px; margin: auto; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: #007aff; color: white; padding: 20px; text-align: center; }}
        .row {{ display: flex; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid #f0f0f0; align-items: center; }}
        .plus {{ color: #ff3b30; }} .minus {{ color: #34c759; }}
        .premium {{ font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.1em; }}
    </style>
    </head><body>
    <div class="container">
        <div class="header">📈 跨境基金实时精算<br><small>按溢价率降序 | 更新: {now_str}</small></div>
        {"".join(rows)}
    </div>
    </body></html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

if __name__ == "__main__":
    run_monitor()
