import os
import re
import random
import requests
import json
from datetime import datetime
import pytz
import time
import pickle

# ==================== 【原有配置完全保留】监控标的中心 ====================
# 只需要配置代码、名称、对标ticker，净值全自动获取+兜底
FUND_CONFIG = {
    # 原油类
    "162411": {"name": "华宝油气", "ticker": "XOP"},
    "160216": {"name": "国泰原油LOF", "ticker": "USO"},
    "160416": {"name": "南方原油", "ticker": "USO"},
    "161129": {"name": "易方达原油LOF", "ticker": "USO"},
    # 权益/科技类
    "159509": {"name": "纳指科技ETF", "ticker": "IXN"},
    "501225": {"name": "全球芯片LOF", "ticker": "SOXX"},
    "161128": {"name": "标普科技LOF", "ticker": "XLK"},
    "162415": {"name": "生物科技LOF", "ticker": "XBI"},
    "164906": {"name": "中概互联LOF", "ticker": "KWEB"},
    # 宽基类
    "161125": {"name": "标普500LOF", "ticker": "IVV"},
    "513500": {"name": "标普500ETF", "ticker": "IVV"},
    "161127": {"name": "纳指100LOF", "ticker": "QQQ"},
    "513100": {"name": "纳指ETF", "ticker": "QQQ"},
}

# ==================== 【核心优化配置】解决封禁+兜底 ====================
# 重试配置
MAX_RETRY = 3  # 单次请求最大重试次数
RETRY_WAIT_MIN = 1  # 重试前最小等待秒数
RETRY_WAIT_MAX = 3  # 重试前最大等待秒数
# 请求间隔配置（防频控核心）
ITEM_SLEEP_MIN = 1.5  # 每个标的处理完最少休眠秒数
ITEM_SLEEP_MAX = 4  # 每个标的处理完最多休眠秒数
# 缓存配置（解决GitHub Actions无状态问题，兜底用）
CACHE_FILE = "fund_data_cache.pkl"
NAV_CACHE_EXPIRE = 12 * 3600  # 净值缓存12小时
US_CHANGE_CACHE_EXPIRE = 5 * 60  # 美股涨跌幅缓存5分钟
# 时区配置
CN_TZ = pytz.timezone('Asia/Shanghai')
US_EAST_TZ = pytz.timezone('America/New_York')
UTC_TZ = pytz.UTC

# ==================== 随机UA池（反爬核心） ====================
USER_AGENT_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 14; Mobile; rv:124.0) Gecko/124.0 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
]

# ==================== 【优化后HTML模板】增加状态标注 ====================
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha 全自动套利监控</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }}
        .container {{ max-width: 650px; margin: auto; background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1890ff, #096dd9); color: white; padding: 20px; text-align: center; }}
        .row {{ display: flex; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid #f0f0f0; align-items: center; }}
        .name {{ font-weight: 500; font-size: 16px; color: #1f1f1f; }}
        .code {{ font-size: 12px; color: #8c8c8c; margin-top: 2px; }}
        .nav-date {{ font-size: 11px; color: #bfbfbf; margin-top: 2px; }}
        .premium {{ font-family: monospace; font-weight: 700; font-size: 16px; white-space: nowrap; }}
        .plus {{ color: #cf1322; }}
        .minus {{ color: #389e0d; }}
        .neutral {{ color: #595959; }}
        .cache-tag {{ font-size: 10px; background: #e8f4ff; color: #1890ff; padding: 1px 3px; border-radius: 2px; margin-left: 5px; }}
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div style="font-size: 20px; font-weight: bold;">📊 Alpha 全自动监控</div>
            <div style="font-size: 12px; margin-top: 8px;">更新时间: {now_str}</div>
            <div style="font-size: 10px; margin-top: 4px; opacity: 0.9;">格式：低溢价~高溢价 | 按溢价从高到低排序</div>
        </div>
        {content_html}
    </div>
</body>
</html>"""

# ==================== 【核心优化1：缓存工具函数】解决无状态问题 ====================
def load_cache():
    """加载本地缓存文件，GitHub Actions可配合actions/cache持久化"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        print(f"加载缓存失败: {str(e)}")
    return {"nav": {}, "us_change": {}}

def save_cache(cache_data):
    """保存数据到本地缓存"""
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)
    except Exception as e:
        print(f"保存缓存失败: {str(e)}")

# ==================== 【核心优化2：带重试的安全请求函数】解决403封禁 ====================
def safe_request(url, headers=None, timeout=12, is_gbk=False):
    """带重试、随机UA、异常处理的通用请求函数"""
    if headers is None:
        headers = {}
    
    for retry_count in range(MAX_RETRY):
        try:
            # 每次请求随机换UA，降低被识别概率
            headers['User-Agent'] = random.choice(USER_AGENT_POOL)
            res = requests.get(url, headers=headers, timeout=timeout)
            res.raise_for_status()  # 捕获403/404/500等HTTP错误
            if is_gbk:
                res.encoding = 'gbk'
            return res
        except Exception as e:
            print(f"请求失败（重试{retry_count+1}/{MAX_RETRY}）URL: {url} | 错误: {str(e)}")
            if retry_count < MAX_RETRY - 1:
                # 重试前随机等待，避开频控
                time.sleep(random.uniform(RETRY_WAIT_MIN, RETRY_WAIT_MAX))
            continue
    # 所有重试都失败
    print(f"请求彻底失败 URL: {url}")
    return None

# ==================== 【核心优化3：净值获取函数】彻底解决“净值更新中” ====================
def get_latest_official_nav(fund_code):
    """
    优化版净值获取：
    1. 带3次重试，解决单次请求失败
    2. 优化请求头，降低被封概率
    3. 文件缓存兜底，接口失败也能返回历史净值
    4. 同时返回净值+净值日期，解决美股涨跌幅错位问题
    """
    cache = load_cache()
    now_ts = time.time()
    
    # 先检查缓存是否有效
    if fund_code in cache['nav']:
        cache_item = cache['nav'][fund_code]
        if (now_ts - cache_item['ts']) < NAV_CACHE_EXPIRE:
            print(f"{fund_code} 命中有效缓存，净值: {cache_item['nav']} | 日期: {cache_item['nav_date']}")
            return {
                "nav": cache_item['nav'],
                "nav_date": cache_item['nav_date'],
                "is_cache": True
            }
    
    # 缓存失效，发起网络请求
    api_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    headers = {
        'Referer': 'https://fund.eastmoney.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive'
    }
    
    res = safe_request(api_url, headers=headers)
    if not res:
        # 请求失败，用过期缓存兜底（哪怕过期了也比没有强，彻底告别“净值更新中”）
        if fund_code in cache['nav']:
            cache_item = cache['nav'][fund_code]
            print(f"{fund_code} 接口失败，使用历史缓存兜底，净值: {cache_item['nav']}")
            return {
                "nav": cache_item['nav'],
                "nav_date": cache_item['nav_date'],
                "is_cache": True
            }
        return None
    
    # 解析返回数据
    try:
        text = res.text
        match = re.search(r'jsonpgz\((.*?)\);', text)
        if not match:
            raise Exception("JSONP数据解析失败")
        
        data = json.loads(match.group(1))
        # 核心字段：dwjz=最新官方净值，jzrq=净值日期
        nav_str = data.get('dwjz')
        nav_date_str = data.get('jzrq')
        
        if not nav_str or not nav_date_str:
            raise Exception("净值字段缺失")
        
        latest_nav = float(nav_str)
        if latest_nav <= 0:
            raise Exception("净值数值无效")
        
        # 写入缓存
        cache['nav'][fund_code] = {
            "nav": latest_nav,
            "nav_date": nav_date_str,
            "ts": now_ts
        }
        save_cache(cache)
        
        print(f"{fund_code} 获取净值成功: {latest_nav} | 净值日期: {nav_date_str}")
        return {
            "nav": latest_nav,
            "nav_date": nav_date_str,
            "is_cache": False
        }
    
    except Exception as e:
        print(f"{fund_code} 净值数据解析失败: {str(e)}")
        # 解析失败也用缓存兜底
        if fund_code in cache['nav']:
            cache_item = cache['nav'][fund_code]
            print(f"{fund_code} 解析失败，使用历史缓存兜底")
            return {
                "nav": cache_item['nav'],
                "nav_date": cache_item['nav_date'],
                "is_cache": True
            }
        return None

# ==================== 【核心优化4：美股涨跌幅计算】解决净值日期错位问题 ====================
def get_us_ticker_cumulative_change(ticker, nav_date_str):
    """
    优化版美股涨跌幅计算：
    1. 按净值日期匹配基准收盘价，解决T-1/T-2净值错位问题
    2. 优先取盘前/盘后价格，白天A股时段也能拿到实时变动
    3. 带重试+缓存，减少请求次数
    """
    cache = load_cache()
    now_ts = time.time()
    cache_key = f"{ticker}_{nav_date_str}"
    
    # 检查缓存
    if cache_key in cache['us_change']:
        cache_item = cache['us_change'][cache_key]
        if (now_ts - cache_item['ts']) < US_CHANGE_CACHE_EXPIRE:
            return cache_item['change']
    
    # 取5天数据，覆盖净值滞后的场景
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    headers = {
        'Referer': 'https://finance.yahoo.com/',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7'
    }
    
    res = safe_request(url, headers=headers)
    if not res:
        print(f"{ticker} 美股数据请求失败，返回0涨幅")
        return 0.0
    
    try:
        data = res.json()
        chart_result = data['chart']['result'][0]
        meta = chart_result['meta']
        timestamp_list = chart_result['timestamp']
        quote_data = chart_result['indicators']['quote'][0]
        
        # 1. 获取最新价格（优先盘前>盘后>常规收盘价）
        latest_price = None
        if 'preMarketPrice' in meta and meta['preMarketPrice']:
            latest_price = meta['preMarketPrice']
            print(f"{ticker} 取盘前价格: {latest_price}")
        elif 'postMarketPrice' in meta and meta['postMarketPrice']:
            latest_price = meta['postMarketPrice']
            print(f"{ticker} 取盘后价格: {latest_price}")
        else:
            latest_price = meta.get('regularMarketPrice')
            print(f"{ticker} 取常规收盘价: {latest_price}")
        
        if not latest_price or latest_price <= 0:
            print(f"{ticker} 无有效最新价格，返回0涨幅")
            return 0.0
        
        # 2. 匹配净值日期对应的美股基准收盘价
        # 净值日期（北京时间）转成美东时间，匹配美股交易日
        nav_date_cn = datetime.strptime(nav_date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ)
        nav_date_us = nav_date_cn.astimezone(US_EAST_TZ).date()
        
        base_close_price = None
        for i, ts in enumerate(timestamp_list):
            kline_utc = UTC_TZ.localize(datetime.utcfromtimestamp(ts))
            kline_date_us = kline_utc.astimezone(US_EAST_TZ).date()
            if kline_date_us == nav_date_us:
                close_list = quote_data['close']
                if close_list and close_list[i]:
                    base_close_price = close_list[i]
                    print(f"{ticker} 匹配净值日期{nav_date_str} 基准收盘价: {base_close_price}")
                    break
        
        # 兜底：没找到匹配日期，取最近的收盘价
        if not base_close_price:
            print(f"{ticker} 未匹配到对应日期K线，取最近收盘价兜底")
            close_list = quote_data['close']
            valid_closes = [c for c in close_list if c and c > 0]
            if valid_closes:
                base_close_price = valid_closes[-1]
            else:
                base_close_price = meta.get('previousClose')
        
        if not base_close_price or base_close_price <= 0:
            print(f"{ticker} 无有效基准收盘价，返回0涨幅")
            return 0.0
        
        # 3. 计算累计涨跌幅
        cumulative_change = (latest_price - base_close_price) / base_close_price
        print(f"{ticker} 累计涨跌幅: {cumulative_change:.4%}")
        
        # 写入缓存
        cache['us_change'][cache_key] = {
            "change": cumulative_change,
            "ts": now_ts
        }
        save_cache(cache)
        
        return cumulative_change
    
    except Exception as e:
        print(f"{ticker} 美股数据解析失败: {str(e)}")
        return 0.0

# ==================== 【优化5：场内价格获取】增加重试+反爬 ====================
def get_cn_fund_market_price(code):
    """获取国内LOF/ETF实时成交价，增加重试和请求头优化"""
    prefix = "sh" if code.startswith(('5', '6', '9')) else "sz"
    full_code = f"{prefix}{code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    headers = {
        'Referer': 'https://gu.qq.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
    
    res = safe_request(url, headers=headers, is_gbk=True)
    if not res:
        return None
    
    try:
        text = res.text.strip()
        if not text or '~' not in text:
            return None
        parts = text.split('~')
        if len(parts) > 3 and parts[3].strip():
            price = float(parts[3])
            return price if price > 0 else None
        return None
    except Exception as e:
        print(f"{code} 场内价格解析失败: {str(e)}")
        return None

# ==================== 【优化6：溢价格式化】保证低溢价在左，高溢价在右 ====================
def format_premium_pair(premium1, premium2):
    min_p = min(premium1, premium2)
    max_p = max(premium1, premium2)
    
    def format_single(p):
        sign = "+" if p > 0 else ""
        return f"{sign}{p:.2%}"
    
    min_text = format_single(min_p)
    max_text = format_single(max_p)
    
    # 颜色按最高溢价判断
    if max_p > 0:
        color = "plus"
    elif max_p < 0:
        color = "minus"
    else:
        color = "neutral"
    
    return f"{min_text}~{max_text}", color

# ==================== 主监控函数 ====================
def run_monitor_task():
    now_time = datetime.now(CN_TZ)
    now_str = now_time.strftime('%Y-%m-%d %H:%M:%S')
    fund_result_list = []

    for fund_code, fund_info in FUND_CONFIG.items():
        print(f"\n===== 处理标的: {fund_code} {fund_info['name']} =====")
        fund_name = fund_info['name']
        ticker = fund_info['ticker']
        
        # 1. 获取场内实时价格
        market_price = get_cn_fund_market_price(fund_code)
        # 2. 获取官方净值+日期
        nav_data = get_latest_official_nav(fund_code)
        
        # 兜底处理：价格获取失败
        if not market_price:
            row_html = f'''
            <div class="row">
                <div>
                    <div class="name">{fund_name}<span class="cache-tag">无行情</span></div>
                    <div class="code">代码: {fund_code}</div>
                </div>
                <div class="premium neutral">--</div>
            </div>
            '''
            fund_result_list.append({
                "max_premium": -9999,
                "html": row_html
            })
            # 处理完休眠，防频控
            time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
            continue
        
        # 兜底处理：净值获取彻底失败（连缓存都没有）
        if not nav_data:
            row_html = f'''
            <div class="row">
                <div>
                    <div class="name">{fund_name}<span class="cache-tag">无净值</span></div>
                    <div class="code">代码: {fund_code}</div>
                </div>
                <div class="premium neutral">--</div>
            </div>
            '''
            fund_result_list.append({
                "max_premium": -9999,
                "html": row_html
            })
            # 处理完休眠，防频控
            time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
            continue
        
        # 提取净值数据
        official_nav = nav_data['nav']
        nav_date = nav_data['nav_date']
        is_cache = nav_data['is_cache']
        
        # 3. 双口径溢价计算
        # 口径1：官方净值溢价率
        premium_official = (market_price - official_nav) / official_nav
        # 口径2：实时估算溢价率（对齐净值日期的累计涨跌幅）
        us_change = get_us_ticker_cumulative_change(ticker, nav_date)
        estimated_nav = official_nav * (1 + us_change)
        premium_estimated = (market_price - estimated_nav) / estimated_nav if estimated_nav else premium_official

        # 4. 格式化显示
        premium_text, color = format_premium_pair(premium_official, premium_estimated)
        max_premium = max(premium_official, premium_estimated)
        cache_tag = '<span class="cache-tag">缓存兜底</span>' if is_cache else ''

        # 5. 生成行HTML
        row_html = f'''
        <div class="row">
            <div>
                <div class="name">{fund_name}{cache_tag}</div>
                <div class="code">代码: {fund_code}</div>
                <div class="nav-date">净值日期: {nav_date}</div>
            </div>
            <div class="premium {color}">{premium_text}</div>
        </div>
        '''
        fund_result_list.append({
            "max_premium": max_premium,
            "html": row_html
        })
        
        # 【防频控核心】每个标的处理完，随机休眠，避免连续请求被封
        time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
    
    # 【优化7】按溢价从高到低排序，套利机会一眼看清
    fund_result_list.sort(key=lambda x: x['max_premium'], reverse=True)
    
    # 生成最终HTML
    final_html = HTML_TPL.format(
        now_str=now_str,
        content_html="".join([item['html'] for item in fund_result_list])
    )
    
    # 写入文件
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"\n✅ 监控更新完成 | 北京时间: {now_str} | 共处理{len(FUND_CONFIG)}个标的")

if __name__ == "__main__":
    run_monitor_task()
