import os
import re
import random
import requests
from datetime import datetime
import pytz
import time
import pickle
import json

# ==================== 【核心配置】严格对应：代码-名称 ====================
FUND_CONFIG = {
    # ==================== 原油及商品类 ====================
    "162411": {"name": "华宝油气LOF"},
    "160216": {"name": "国泰原油LOF"},
    "160416": {"name": "南方原油LOF"},
    "161129": {"name": "易方达原油LOF"},
    "501018": {"name": "南方原油LOF(C)"},
    "160723": {"name": "嘉实原油LOF"},
    "162719": {"name": "广发石油LOF"},
    
    # ==================== 黄金类 (新加入) ====================
    "161116": {"name": "易方达黄金主题"},
    "160719": {"name": "嘉实黄金LOF"},
    "161226": {"name": "国泰黄金LOF"},
    "164701": {"name": "汇添富黄金LOF"},

    # ==================== 科技及行业权益类 ====================
    "159509": {"name": "纳指科技ETF"},
    "501225": {"name": "全球芯片LOF"},
    "161128": {"name": "标普科技LOF"},
    "162415": {"name": "生物科技LOF"},
    "164906": {"name": "中概互联LOF"},
    "160644": {"name": "港美互联网LOF"},

    # ==================== 宽基类 ====================
    "161125": {"name": "标普500LOF"},
    "513500": {"name": "标普500ETF"},
    "161127": {"name": "纳指100LOF"},
    "513100": {"name": "纳指ETF"},
}

# ==================== 缓存配置 ====================
CACHE_FILE = "fund_cache.pkl"
COOKIE_CACHE_FILE = "xueqiu_cookie.pkl"
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
        .source {{ font-size: 10px; color: #8c8c8c; margin-top: 2px; }}
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div style="font-size: 20px; font-weight: bold;">📊 Alpha 全自动监控</div>
            <div style="font-size: 12px; margin-top: 8px;">更新时间: {now_str}</div>
            <div style="font-size: 10px; margin-top: 4px; opacity: 0.9;">数据来源：雪球API，实时溢价率</div>
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

def load_xueqiu_cookie():
    """加载雪球Cookie缓存"""
    try:
        if os.path.exists(COOKIE_CACHE_FILE):
            with open(COOKIE_CACHE_FILE, 'rb') as f:
                cookie_data = pickle.load(f)
                if isinstance(cookie_data, dict) and 'cookie' in cookie_data:
                    return cookie_data.get('cookie')
    except Exception as e:
        print(f"加载雪球Cookie失败: {e}")
    return None

def save_xueqiu_cookie(cookie):
    """保存雪球Cookie到缓存"""
    try:
        with open(COOKIE_CACHE_FILE, 'wb') as f:
            pickle.dump({'cookie': cookie, 'timestamp': time.time()}, f)
    except Exception as e:
        print(f"保存雪球Cookie失败: {e}")

# ==================== 安全请求函数 ====================
def safe_request(url, headers=None, timeout=10, cookies=None):
    if headers is None:
        headers = {}
    headers['User-Agent'] = random.choice(USER_AGENT_POOL)
    try:
        return requests.get(url, headers=headers, timeout=timeout, cookies=cookies)
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

# ==================== 获取雪球Cookie ====================
def get_xueqiu_cookie():
    """获取雪球Cookie"""
    cached_cookie = load_xueqiu_cookie()
    if cached_cookie:
        # 检查缓存是否过期（假设24小时过期）
        try:
            with open(COOKIE_CACHE_FILE, 'rb') as f:
                cookie_data = pickle.load(f)
                if time.time() - cookie_data.get('timestamp', 0) < 24 * 3600:
                    return cached_cookie
        except:
            pass

    # 获取新的Cookie
    headers = {
        'User-Agent': random.choice(USER_AGENT_POOL),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        response = requests.get('https://xueqiu.com/', headers=headers, allow_redirects=True)
        cookie = response.cookies
        save_xueqiu_cookie(cookie)
        return cookie
    except Exception as e:
        print(f"获取雪球Cookie失败: {e}")
        return None

# ==================== 获取雪球溢价率 ====================
def get_xueqiu_premium_rate(fund_code):
    """从雪球API获取溢价率"""
    cookie = get_xueqiu_cookie()
    if not cookie:
        print(f"无法获取雪球Cookie，跳过 {fund_code}")
        return None

    # 判断基金代码前缀，确定交易所在雪球的符号
    if fund_code.startswith(('5', '6', '9')):
        symbol = f"SH{fund_code}"  # 上交所
    else:
        symbol = f"SZ{fund_code}"  # 深交所

    url = f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={symbol}&extend=detail"
    
    headers = {
        'User-Agent': random.choice(USER_AGENT_POOL),
        'Accept': 'application/json',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://xueqiu.com/',
    }
    
    try:
        response = requests.get(url, headers=headers, cookies=cookie, timeout=10)
        if response.status_code != 200:
            print(f"雪球API请求失败，状态码: {response.status_code}, {fund_code}")
            return None
            
        data = response.json()
        
        if 'data' not in data or 'quote' not in data['data']:
            print(f"雪球API响应格式错误，{fund_code}")
            return None
            
        quote = data['data']['quote']
        
        # 尝试获取溢价率
        if 'premium_rate' in quote:
            premium_rate = quote['premium_rate']
            if premium_rate is not None:
                return float(premium_rate)
        
        # 如果没有直接的溢价率，尝试通过其他字段计算
        if 'current' in quote and 'net_value' in quote:
            current_price = quote.get('current')
            net_value = quote.get('net_value')
            
            if current_price and net_value and net_value > 0:
                calculated_premium = (current_price - net_value) / net_value
                return calculated_premium
                
    except Exception as e:
        print(f"解析雪球溢价率失败 {fund_code}: {e}")
        return None
    
    return None

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

# ==================== 格式化 ====================
def format_premium(premium):
    if premium is None:
        return "N/A", "neutral"
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

        # 从雪球获取溢价率
        premium_rate = get_xueqiu_premium_rate(code)
        
        # 同时获取场内价格用于显示（备用）
        market_price = get_cn_fund_market_price(code)

        if premium_rate is None:
            rows.append(f'''
            <div class="row">
                <div>
                    <div class="name">{name}</div>
                    <div class="code">代码: {code}</div>
                </div>
                <div class="premium neutral">无数据</div>
            </div>''')
            continue

        display_text, color = format_premium(premium_rate)

        rows.append(f'''
        <div class="row">
            <div>
                <div class="name">{name}</div>
                <div class="code">代码: {code}</div>
                <div class="source">雪球API</div>
            </div>
            <div class="premium {color}">{display_text}</div>
        </div>''')

    html = HTML_TPL.format(now_str=now_str, content_html="".join(rows))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run_monitor_task()
