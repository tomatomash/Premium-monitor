import os
import re
import random
import requests
from datetime import datetime
import pytz
import time
import pickle

# ==================== 【核心配置】严格对应：代码-名称-海外ticker ====================
FUND_CONFIG = {
    # ==================== 原油及商品类 ====================
    # 使用 CL=F (WTI原油期货) 捕捉亚洲时段实时波动
    "162411": {"name": "华宝油气LOF", "ticker": "XOP"},
    "160216": {"name": "国泰原油LOF", "ticker": "CL=F"},
    "160416": {"name": "南方原油LOF", "ticker": "CL=F"},
    "161129": {"name": "易方达原油LOF", "ticker": "CL=F"},
    "501018": {"name": "南方原油LOF(C)", "ticker": "CL=F"},
    "160723": {"name": "嘉实原油LOF", "ticker": "CL=F"},
    "162719": {"name": "广发石油LOF", "ticker": "CL=F"},
    
    # ==================== 黄金类 (新加入) ====================
    # 对标 GC=F (COMEX黄金期货) 以对齐实时金价变动
    "161116": {"name": "易方达黄金主题", "ticker": "GC=F"},
    "160719": {"name": "嘉实黄金LOF", "ticker": "GC=F"},
    "161226": {"name": "国泰黄金LOF", "ticker": "GC=F"},
    "164701": {"name": "汇添富黄金LOF", "ticker": "GC=F"},

    # ==================== 科技及行业权益类 ====================
    "159509": {"name": "纳指科技ETF", "ticker": "NQ=F"},
    "501225": {"name": "全球芯片LOF", "ticker": "SOXX"},
    "161128": {"name": "标普科技LOF", "ticker": "XLK"},
    "162415": {"name": "生物科技LOF", "ticker": "XBI"},
    "164906": {"name": "中概互联LOF", "ticker": "KWEB"},
    "160644": {"name": "港美互联网LOF", "ticker": "KWEB"},

    # ==================== 宽基类 ====================
    # 使用股指期货 (ES=F, NQ=F) 对齐 A 股盘中的美股走势
    "161125": {"name": "标普500LOF", "ticker": "ES=F"},
    "513500": {"name": "标普500ETF", "ticker": "ES=F"},
    "161127": {"name": "纳指100LOF", "ticker": "NQ=F"},
    "513100": {"name": "纳指ETF", "ticker": "NQ=F"},
}

# ==================== 缓存配置 ====================
CACHE_FILE = "fund_cache.pkl"
CACHE_DURATION_SECONDS = 2 * 3600  # 2小时缓存
CN_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 随机UA池 ====================
USER_AGENT_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
]

# ==================== HTML模板 ====================
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha 全自动监控</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }}
        .container {{ max-width: 600px; margin: auto; background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: #1890ff; color: white; padding: 20px; text-align: center; }}
        .row {{ display: flex; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid #f0f0f0; align-items: center; }}
        .name {{ font-weight: 500; font-size: 16px; color: #1f1f1f; }}
        .code {{ font-size: 12px; color: #8c8c8c; margin-top: 2px; }}
        .premium {{ font-family: monospace; font-weight: 700; font-size: 16px; white-space: nowrap; }}
        .plus {{ color: #cf1322; }}
        .minus {{ color: #389e0d; }}
        .neutral {{ color: #595959; }}
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div style="font-size: 20px; font-weight: bold;">📊 Alpha 全自动监控</div>
            <div style="font-size: 12px; margin-top: 8px;">更新时间: {now_str}</div>
            <div style="font-size: 10px; margin-top: 4px; opacity: 0.9;">格式：官方净值溢价~实时估算溢价</div>
        </div>
        {content_html}
    </div>
</body>
</html>"""

# ==================== 加载缓存 ====================
def load_cache():
    """修复：确保始终返回字典类型"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as f:
                cache_data = pickle.load(f)
                # 校验缓存数据是否为字典
                if isinstance(cache_data, dict):
                    return cache_data
    except Exception as e:
        # 打印异常信息便于调试（可选）
        print(f"加载缓存失败: {e}")
    # 任何异常/非法数据都返回空字典
    return {}

def save_cache(data):
    """优化：仅保存字典类型数据"""
    if not isinstance(data, dict):
        print("缓存数据不是字典，跳过保存")
        return
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(data, f)
    except Exception as e:
        print(f"保存缓存失败: {e}")

# ==================== 安全请求函数 ====================
def safe_request(url, headers=None, timeout=10):
    if headers is None:
        headers = {}
    headers['User-Agent'] = random.choice(USER_AGENT_POOL)
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

# ==================== 【回滚】获取净值（使用你要的原接口，不换） ====================
def get_latest_official_nav(fund_code):
    cache = load_cache()
    now_ts = time.time()
    
    # 检查缓存是否有效
    if fund_code in cache:
        cache_item = cache[fund_code]
        # 校验缓存项结构
        if isinstance(cache_item, dict) and 'ts' in cache_item and 'nav' in cache_item:
            if now_ts - cache_item['ts'] < CACHE_DURATION_SECONDS:
                return cache_item['nav']
    
    # 接口请求
    api_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    res = safe_request(api_url)
    if not res:
        # 缓存中有数据则返回，否则返回None
        return cache.get(fund_code, {}).get('nav') if fund_code in cache else None
    
    try:
        text = res.text
        match = re.search(r'jsonpgz\((.*?)\);', text)
        if not match:
            return cache.get(fund_code, {}).get('nav') if fund_code in cache else None
        
        import json
        data = json.loads(match.group(1))
        nav_str = data.get('dwjz')
        if not nav_str:
            return cache.get(fund_code, {}).get('nav') if fund_code in cache else None
        
        nav = float(nav_str)
        # 更新缓存
        cache[fund_code] = {'nav': nav, 'ts': now_ts}
        save_cache(cache)
        return nav
    except Exception as e:
        print(f"解析净值失败 {fund_code}: {e}")
        # 异常时返回缓存数据（如果有）
        return cache.get(fund_code, {}).get('nav') if fund_code in cache else None

# ==================== 【回滚】获取场内价格（原接口） ====================
def get_cn_fund_market_price(code):
    prefix = "sh" if code.startswith(('5', '6', '9')) else "sz"
    full_code = f"{prefix}{code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    res = safe_request(url, timeout=8)
    if not res:
        return None
    try:
        res.encoding = 'gbk'
        text = res.text
        if '~' not in text:
            return None
        parts = text.split('~')
        price = float(parts[3]) if len(parts) > 3 and parts[3] else None
        return price if price and price > 0 else None
    except Exception as e:
        print(f"解析场内价格失败 {code}: {e}")
        return None

# ==================== 【回滚】美股涨跌幅（原接口） ====================
def get_us_ticker_change(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
    res = safe_request(url)
    if not res:
        return 0.0
    try:
        data = res.json()
        meta = data['chart']['result'][0]['meta']
        latest = meta.get('regularMarketPrice', meta.get('previousClose'))
        prev = meta.get('previousClose')
        if not latest or not prev or prev == 0:
            return 0.0
        return (latest / prev) - 1
    except Exception as e:
        print(f"解析美股涨跌幅失败 {ticker}: {e}")
        return 0.0

# ==================== 格式化 ====================
def format_premium(premium):
    sign = "+" if premium > 0 else ""
    color = "plus" if premium > 0 else "minus" if premium < 0 else "neutral"
    return f"{sign}{premium:.2%}", color

# ==================== 主函数 ====================
def run_monitor_task():
    now = datetime.now(CN_TZ)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    rows = []

    for code, info in FUND_CONFIG.items():
        name = info['name']
        ticker = info['ticker']

        mp = get_cn_fund_market_price(code)
        nav = get_latest_official_nav(code)

        if not mp or not nav:
            rows.append(f'''
            <div class="row">
                <div>
                    <div class="name">{name}</div>
                    <div class="code">代码: {code}</div>
                </div>
                <div class="premium neutral">无净值</div>
            </div>''')
            continue

        p1 = (mp - nav) / nav
        us_change = get_us_ticker_change(ticker)
        est_nav = nav * (1 + us_change)
        p2 = (mp - est_nav) / est_nav if est_nav else p1

        t1, c1 = format_premium(p1)
        t2, c2 = format_premium(p2)
        display = f"{t1}~{t2}"
        color = c2

        rows.append(f'''
        <div class="row">
            <div>
                <div class="name">{name}</div>
                <div class="code">代码: {code}</div>
            </div>
            <div class="premium {color}">{display}</div>
        </div>''')

    html = HTML_TPL.format(now_str=now_str, content_html="".join(rows))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run_monitor_task()
