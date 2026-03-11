import os
import re
import random
import requests
import json
from datetime import datetime, timedelta
import pytz
import time
import pickle
import hashlib

# ==================== 【核心配置区】仅需维护标的代码和对标ticker ====================
MONITOR_TARGETS = [
    # 原油类标的
    {"code": "162411", "ticker": "XOP"},
    {"code": "160216", "ticker": "USO"},
    {"code": "160416", "ticker": "USO"},
    {"code": "161129", "ticker": "USO"},
    # 科技/权益类标的
    {"code": "159509", "ticker": "IXN"},
    {"code": "501225", "ticker": "SOXX"},
    {"code": "161128", "ticker": "XLK"},
    {"code": "162415", "ticker": "XBI"},
    {"code": "164906", "ticker": "KWEB"},
    # 宽基类标的
    {"code": "161125", "ticker": "IVV"},
    {"code": "513500", "ticker": "IVV"},
    {"code": "161127", "ticker": "QQQ"},
    {"code": "513100", "ticker": "QQQ"},
]

# ==================== 核心配置 ====================
# 缓存配置（解决IP封禁时兜底）
CACHE_FILE = "fund_cache.pkl"
CACHE_EXPIRE_HOURS = 12  # 缓存12小时
# 防频控配置
GLOBAL_SLEEP = 3  # 全局请求间隔
ITEM_SLEEP_MIN = 2
ITEM_SLEEP_MAX = 5
# 熔断配置（连续失败3个标的直接停止请求，避免浪费）
FAIL_THRESHOLD = 3
# 时区
CN_TZ = pytz.timezone('Asia/Shanghai')
US_EAST_TZ = pytz.timezone('America/New_York')
UTC_TZ = pytz.UTC

# ==================== 请求头池（模拟真实浏览器） ====================
HEADERS_POOL = [
    {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Referer': 'https://www.jisilu.cn/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'X-Requested-With': 'XMLHttpRequest'
    },
    {
        'User-Agent': 'Mozilla/5.0 (Android 14; Mobile; rv:109.0) Gecko/115.0 Firefox/115.0',
        'Referer': 'https://www.jisilu.cn/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    },
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
        'Referer': 'https://www.jisilu.cn/data/qdii/qdii_list/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6'
    }
]

# ==================== HTML模板 ====================
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOF溢价精准监控</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f7fa; margin: 0; padding: 12px; }}
        .container {{ max-width: 680px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1890ff, #096dd9); color: white; padding: 18px; text-align: center; }}
        .header .title {{ font-size: 20px; font-weight: 700; }}
        .header .subinfo {{ font-size: 12px; margin-top: 6px; opacity: 0.9; }}
        .table-header {{ display: flex; justify-content: space-between; padding: 12px 20px; background: #fafafa; border-bottom: 1px solid #f0f0f0; font-size: 13px; color: #666; }}
        .row {{ display: flex; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid #f5f5f5; align-items: center; }}
        .fund-info .name {{ font-weight: 600; font-size: 16px; color: #262626; }}
        .fund-info .code {{ font-size: 12px; color: #8c8c8c; margin-top: 3px; }}
        .fund-info .nav-date {{ font-size: 11px; color: #bfbfbf; margin-top: 2px; }}
        .premium {{ font-family: 'SF Mono', Monaco, Menlo, Consolas, monospace; font-weight: 700; font-size: 17px; white-space: nowrap; }}
        .plus {{ color: #cf1322; }}
        .minus {{ color: #389e0d; }}
        .neutral {{ color: #595959; }}
        .warn-tag {{ font-size: 11px; background: #fff2e8; color: #d46b08; padding: 2px 4px; border-radius: 3px; margin-left: 6px; }}
        .cache-tag {{ font-size: 11px; background: #e8f4ff; color: #1890ff; padding: 2px 4px; border-radius: 3px; margin-left: 6px; }}
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">📊 LOF溢价精准监控</div>
            <div class="subinfo">更新时间: {now_str} | 格式：低溢价~高溢价 | 按溢价从高到低排序</div>
        </div>
        <div class="table-header">
            <span>基金标的</span>
            <span>溢价率区间</span>
        </div>
        {content_html}
    </div>
</body>
</html>"""

# ==================== 缓存工具函数 ====================
def load_cache():
    """加载本地缓存"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    return {}

def save_cache(cache_data):
    """保存缓存到本地"""
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)
    except:
        print("缓存保存失败")

def get_cached_fund_data(fund_code):
    """获取缓存的基金数据，判断是否过期"""
    cache = load_cache()
    if fund_code in cache:
        data = cache[fund_code]
        cache_time = data.get('cache_time', 0)
        # 检查是否过期
        if time.time() - cache_time < CACHE_EXPIRE_HOURS * 3600:
            return data
    return None

def set_cached_fund_data(fund_code, data):
    """设置基金数据缓存"""
    cache = load_cache()
    data['cache_time'] = time.time()
    cache[fund_code] = data
    save_cache(cache)

# ==================== 核心请求函数 ====================
def get_random_headers():
    """获取随机请求头"""
    return random.choice(HEADERS_POOL)

def safe_request(url, headers=None, timeout=15, retry=2):
    """安全请求函数，带重试和延迟"""
    if headers is None:
        headers = get_random_headers()
    
    for i in range(retry + 1):
        try:
            time.sleep(GLOBAL_SLEEP)  # 全局请求间隔
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"请求失败 (重试{i+1}/{retry+1}): {url} | 错误: {str(e)}")
            if i < retry:
                time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
                continue
            return None

# ==================== 数据获取核心函数 ====================
def get_jisilu_qdii_data():
    """从集思录获取全量QDII/LOF数据（核心数据源）"""
    url = "https://www.jisilu.cn/data/qdii/qdii_list/"
    headers = get_random_headers()
    response = safe_request(url, headers=headers)
    
    if not response:
        return None
    
    try:
        # 解析页面中的JSON数据
        html = response.text
        # 匹配核心数据
        match = re.search(r'var g_qdii_data = (\[.*?\]);', html, re.S)
        if not match:
            return None
        
        qdii_data = json.loads(match.group(1))
        # 转换为字典，方便按代码查找
        fund_dict = {}
        for fund in qdii_data:
            fund_code = fund.get('fund_code')
            if fund_code:
                fund_dict[fund_code] = fund
        return fund_dict
    except Exception as e:
        print(f"解析集思录数据失败: {str(e)}")
        return None

def get_fund_detail_from_jisilu(fund_code, jisilu_data):
    """从集思录数据中提取单只基金信息"""
    if not jisilu_data or fund_code not in jisilu_data:
        return None
    
    fund = jisilu_data[fund_code]
    try:
        # 核心数据提取
        return {
            'name': fund.get('fund_nm', fund_code),
            'nav': float(fund.get('fund_nav', 0)) if fund.get('fund_nav') else None,
            'nav_date': fund.get('nav_dt', ''),
            'market_price': float(fund.get('price', 0)) if fund.get('price') else None,
            'premium_rate': float(fund.get('premium_rt', 0)) / 100 if fund.get('premium_rt') else None
        }
    except Exception as e:
        print(f"解析{fund_code}数据失败: {str(e)}")
        return None

def get_us_ticker_change(ticker):
    """获取美股标的涨跌幅（带缓存）"""
    cache_key = f"us_{ticker}"
    cached = get_cached_fund_data(cache_key)
    if cached:
        return cached.get('change', 0.0)
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    headers = {
        'User-Agent': random.choice([h['User-Agent'] for h in HEADERS_POOL]),
        'Referer': 'https://finance.yahoo.com/'
    }
    
    response = safe_request(url, headers=headers, retry=1)
    if not response:
        return 0.0
    
    try:
        data = response.json()
        if 'chart' not in data or 'result' not in data['chart'] or not data['chart']['result']:
            return 0.0
        
        meta = data['chart']['result'][0]['meta']
        latest = meta.get('regularMarketPrice', meta.get('previousClose', 0))
        prev = meta.get('previousClose', 0)
        
        if latest <= 0 or prev <= 0:
            change = 0.0
        else:
            change = (latest - prev) / prev
        
        # 缓存结果
        set_cached_fund_data(cache_key, {'change': change})
        return change
    except:
        return 0.0

def format_premium(p1, p2):
    """格式化溢价，低的在前"""
    min_p = min(p1, p2) if p1 and p2 else (p1 or p2 or 0)
    max_p = max(p1, p2) if p1 and p2 else (p1 or p2 or 0)
    
    def fmt(p):
        sign = "+" if p > 0 else ""
        return f"{sign}{p:.2%}"
    
    color = "plus" if max_p > 0 else "minus" if max_p < 0 else "neutral"
    return f"{fmt(min_p)}~{fmt(max_p)}", color

# ==================== 主函数 ====================
def main():
    now = datetime.now(CN_TZ)
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    results = []
    fail_count = 0
    
    # 1. 先获取集思录全量数据
    print("获取集思录QDII/LOF全量数据...")
    jisilu_data = get_jisilu_qdii_data()
    
    # 2. 遍历处理每个标的
    for idx, target in enumerate(MONITOR_TARGETS):
        code = target['code']
        ticker = target['ticker']
        print(f"\n===== 处理第{idx+1}/{len(MONITOR_TARGETS)}个标的: {code} =====")
        
        # 检查熔断阈值
        if fail_count >= FAIL_THRESHOLD:
            print(f"连续{FAIL_THRESHOLD}个标的失败，触发熔断，使用缓存数据")
            cached = get_cached_fund_data(code)
            if cached:
                fund_data = cached
                is_cache = True
            else:
                results.append({
                    'max_premium': -9999,
                    'html': f'''
                    <div class="row">
                        <div class="fund-info">
                            <div class="name">{code}<span class="warn-tag">熔断无数据</span></div>
                            <div class="code">代码: {code}</div>
                        </div>
                        <div class="premium neutral">--</div>
                    </div>'''
                })
            continue
        
        # 2.1 尝试从集思录获取数据
        fund_data = None
        is_cache = False
        
        if jisilu_data:
            fund_data = get_fund_detail_from_jisilu(code, jisilu_data)
        
        # 2.2 集思录失败，尝试缓存
        if not fund_data:
            fund_data = get_cached_fund_data(code)
            is_cache = True
            if fund_data:
                print(f"使用缓存数据: {code}")
        
        # 2.3 数据仍为空，标记失败
        if not fund_data:
            fail_count += 1
            results.append({
                'max_premium': -9999,
                'html': f'''
                <div class="row">
                    <div class="fund-info">
                        <div class="name">{code}<span class="warn-tag">无数据</span></div>
                        <div class="code">代码: {code}</div>
                    </div>
                    <div class="premium neutral">--</div>
                </div>'''
            })
            continue
        
        # 重置失败计数
        fail_count = 0
        
        # 提取核心数据
        name = fund_data.get('name', code)
        nav = fund_data.get('nav')
        market_price = fund_data.get('market_price')
        nav_date = fund_data.get('nav_date', '')
        premium_official = fund_data.get('premium_rate')
        
        # 2.4 计算实时估算溢价
        if nav and market_price:
            us_change = get_us_ticker_change(ticker)
            estimated_nav = nav * (1 + us_change)
            premium_estimated = (market_price - estimated_nav) / estimated_nav if estimated_nav else None
            
            # 格式化溢价显示
            if premium_official and premium_estimated:
                premium_text, color = format_premium(premium_official, premium_estimated)
                max_premium = max(premium_official, premium_estimated)
            elif premium_official:
                premium_text, color = format_premium(premium_official, premium_official)
                max_premium = premium_official
            elif premium_estimated:
                premium_text, color = format_premium(premium_estimated, premium_estimated)
                max_premium = premium_estimated
            else:
                premium_text = "--"
                color = "neutral"
                max_premium = -9999
            
            # 构建HTML
            tag = '<span class="cache-tag">缓存数据</span>' if is_cache else ''
            row_html = f'''
            <div class="row">
                <div class="fund-info">
                    <div class="name">{name}{tag}</div>
                    <div class="code">代码: {code}</div>
                    <div class="nav-date">净值日期: {nav_date}</div>
                </div>
                <div class="premium {color}">{premium_text}</div>
            </div>'''
            
            results.append({
                'max_premium': max_premium,
                'html': row_html
            })
            
            # 缓存数据（备用）
            if not is_cache:
                set_cached_fund_data(code, fund_data)
        else:
            fail_count += 1
            results.append({
                'max_premium': -9999,
                'html': f'''
                <div class="row">
                    <div class="fund-info">
                        <div class="name">{name}<span class="warn-tag">数据不全</span></div>
                        <div class="code">代码: {code}</div>
                    </div>
                    <div class="premium neutral">--</div>
                </div>'''
            })
        
        # 随机延迟
        time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
    
    # 3. 按溢价排序
    results.sort(key=lambda x: x['max_premium'], reverse=True)
    
    # 4. 生成HTML
    content_html = ''.join([r['html'] for r in results])
    final_html = HTML_TPL.format(now_str=now_str, content_html=content_html)
    
    # 5. 保存HTML
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"\n✅ 监控任务完成 | 北京时间: {now_str}")
    print(f"📊 生成文件: index.html")

if __name__ == "__main__":
    main()
