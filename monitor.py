import os
import re
import random
import requests
from datetime import datetime
import pytz
import time
import pickle

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
    
    # ==================== 黄金类 ====================
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
CACHE_DURATION_SECONDS = 2 * 3600  # 2小时缓存
CN_TZ = pytz.timezone('Asia/Shanghai')

# ==================== 雪球API访问频率控制配置 (核心新增) ====================
# 每个标的请求之间的最小/最大间隔时间（秒）
MIN_REQUEST_INTERVAL = 2  # 最小2秒
MAX_REQUEST_INTERVAL = 5  # 最大5秒

# ==================== 随机UA池 ====================
USER_AGENT_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
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
            <div style="font-size: 10px; margin-top: 4px; opacity: 0.9;">数据来源：雪球API (精准溢价率) | 访问间隔：{interval_range}秒</div>
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
                if isinstance(cache_data, dict):
                    return cache_data
    except Exception as e:
        print(f"加载缓存失败: {e}")
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

# ==================== 雪球Cookie获取 ====================
def get_xueqiu_cookies():
    """获取雪球主页Cookie"""
    session = requests.Session()
    headers = {
        'User-Agent': random.choice(USER_AGENT_POOL),
        'Referer': 'https://xueqiu.com/'
    }
    try:
        # 访问雪球主页获取Cookie
        session.get('https://xueqiu.com/', headers=headers, timeout=10)
        return session.cookies
    except Exception as e:
        print(f"获取雪球Cookie失败: {e}")
        return None

# ==================== 安全请求函数 ====================
def safe_request(url, headers=None, timeout=10, cookies=None):
    if headers is None:
        headers = {}
    headers['User-Agent'] = random.choice(USER_AGENT_POOL)
    headers['Referer'] = 'https://xueqiu.com/'  # 增加Referer避免被风控
    try:
        return requests.get(url, headers=headers, timeout=timeout, cookies=cookies)
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

# ==================== 获取雪球精准溢价率 ====================
def get_xueqiu_premium_rate(fund_code):
    """
    从雪球API获取精准的溢价率
    :param fund_code: 基金代码
    :return: 溢价率（小数形式），如0.02表示2%
    """
    cache = load_cache()
    now_ts = time.time()
    
    # 检查缓存是否有效
    cache_key = f"xueqiu_{fund_code}"
    if cache_key in cache:
        cache_item = cache[cache_key]
        if isinstance(cache_item, dict) and 'ts' in cache_item and 'premium' in cache_item:
            if now_ts - cache_item['ts'] < CACHE_DURATION_SECONDS:
                print(f"[缓存命中] {fund_code} - 使用缓存的溢价率数据")
                return cache_item['premium']
    
    # 确定市场前缀 SH/SZ
    if fund_code.startswith(('5', '6', '9')):
        market_prefix = "SH"
    else:
        market_prefix = "SZ"
    
    # 获取雪球Cookie
    cookies = get_xueqiu_cookies()
    if not cookies:
        # 缓存中有数据则返回，否则返回None
        return cache.get(cache_key, {}).get('premium') if cache_key in cache else None
    
    # 雪球行情接口
    api_url = f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={market_prefix}{fund_code}"
    print(f"[API请求] 正在获取 {fund_code} 的溢价率数据...")
    res = safe_request(api_url, cookies=cookies, timeout=10)
    
    if not res:
        return cache.get(cache_key, {}).get('premium') if cache_key in cache else None
    
    try:
        data = res.json()
        
        # 提取溢价率（雪球返回的是百分比数值，如2.5表示2.5%）
        premium_rate = data['data']['quote'].get('premium_rate', 0.0)
        # 转换为小数形式（如2.5% → 0.025）
        premium = premium_rate / 100.0
        
        # 更新缓存
        cache[cache_key] = {'premium': premium, 'ts': now_ts}
        save_cache(cache)
        print(f"[API成功] {fund_code} - 溢价率: {premium:.2%}")
        
        return premium
    except Exception as e:
        print(f"解析雪球溢价率失败 {fund_code}: {e}")
        # 异常时返回缓存数据（如果有）
        return cache.get(cache_key, {}).get('premium') if cache_key in cache else None

# ==================== 格式化 ====================
def format_premium(premium):
    if premium is None:
        return "数据获取失败", "neutral"
    
    sign = "+" if premium > 0 else ""
    color = "plus" if premium > 0 else "minus" if premium < 0 else "neutral"
    return f"{sign}{premium:.2%}", color

# ==================== 主函数 ====================
def run_monitor_task():
    now = datetime.now(CN_TZ)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    
    # 遍历所有标的，每个标的请求后添加随机时间间隔
    total_funds = len(FUND_CONFIG)
    current_index = 0
    
    for code, info in FUND_CONFIG.items():
        current_index += 1
        name = info['name']
        
        print(f"\n===== 处理第 {current_index}/{total_funds} 个标的: {code} {name} =====")
        
        # 获取雪球精准溢价率
        premium = get_xueqiu_premium_rate(code)
        display, color = format_premium(premium)

        rows.append(f'''
        <div class="row">
            <div>
                <div class="name">{name}</div>
                <div class="code">代码: {code}</div>
            </div>
            <div class="premium {color}">{display}</div>
        </div>''')
        
        # 为每个标的请求后添加随机时间间隔（最后一个标的不添加）
        if current_index < total_funds:
            interval = random.uniform(MIN_REQUEST_INTERVAL, MAX_REQUEST_INTERVAL)
            print(f"[频率控制] 等待 {interval:.1f} 秒后继续下一个标的...")
            time.sleep(interval)

    # 生成HTML（新增显示间隔范围）
    interval_range = f"{MIN_REQUEST_INTERVAL}-{MAX_REQUEST_INTERVAL}"
    html = HTML_TPL.format(
        now_str=now_str, 
        content_html="".join(rows),
        interval_range=interval_range
    )
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n✅ 所有标的处理完成，HTML文件已更新 - {now_str}")

if __name__ == "__main__":
    print("🚀 启动LOF基金溢价率监控程序（带频率控制）")
    print(f"📋 配置：请求间隔 {MIN_REQUEST_INTERVAL}-{MAX_REQUEST_INTERVAL} 秒 | 缓存有效期 {CACHE_DURATION_SECONDS/3600} 小时")
    run_monitor_task()
