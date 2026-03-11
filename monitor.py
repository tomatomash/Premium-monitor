import os, re, requests, pytz, json
from datetime import datetime

# ==================== 【生产级】定制化精算配置 ====================
# 支持单标的(str)或复合标的(dict)
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
    """实时抓取雅虎财经数据，返回涨跌幅"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, timeout=10)
        meta = res.json()['chart']['result'][0]['meta']
        return (meta['regularMarketPrice'] / meta['previousClose']) - 1
    except: return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    # 获取实时汇率变动 (美元兑人民币)
    fx_change = get_market_data("CNH=F") 
    
    results = []
    for code, info in FUND_CONFIG.items():
        # 1. 抓取国内价格和净值
        try:
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", timeout=5)
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
            
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", timeout=5)
            mp = float(price_res.text.split('~')[3])
            
            # 2. 计算海外组合涨跌幅
            us_change = 0.0
            if isinstance(info['ticker'], dict):
                for tk, weight in info['ticker'].items():
                    us_change += get_market_data(tk) * weight
            else:
                us_change = get_market_data(info['ticker'])
            
            # 3. 双口径精算
            p1 = (mp - nav) / nav
            # 核心公式：考虑汇率和资产权重
            est_nav = nav * (1 + (us_change + fx_change) * info['w'])
            p2 = (mp - est_nav) / est_nav
            
            results.append({
                "code": code, "name": info['name'], "p1": p1, "p2": p2,
                "color": "plus" if p2 > 0 else "minus"
            })
        except: continue

    # 按口径 2 降序排列
    results.sort(key=lambda x: x['p2'], reverse=True)

    # 4. 生成 HTML (此处略，保持你现有的 HTML 模板逻辑即可)
    # ... 渲染 rows 逻辑 ...
    print(f"Successfully calculated {len(results)} funds at {now_str}")
