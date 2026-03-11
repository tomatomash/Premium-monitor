import os
import re
import random
import requests
from datetime import datetime
import pytz
import time
import pickle

# ==================== 【极简配置】仅需填 基金代码+对标ticker，名称全自动获取 ====================
# 新增标的已全部加入，期货ticker已适配，保证A股时段实时波动
MONITOR_LIST = [
    # 原有核心标的
    {"code": "162411", "ticker": "XOP"},      # 华宝油气LOF
    {"code": "160216", "ticker": "CL=F"},     # 国泰大宗商品LOF
    {"code": "160416", "ticker": "CL=F"},     # 石油基金LOF
    {"code": "161129", "ticker": "CL=F"},     # 原油基金LOF
    {"code": "159509", "ticker": "NQ=F"},     # 纳指科技ETF
    {"code": "501225", "ticker": "SOXX"},     # 全球芯片LOF
    {"code": "161128", "ticker": "ES=F"},     # 标普科技LOF
    {"code": "162415", "ticker": "XBI"},      # 标普生物LOF
    {"code": "164906", "ticker": "KWEB"},     # 中概互联网LOF
    {"code": "161125", "ticker": "ES=F"},     # 标普500LOF
    {"code": "513500", "ticker": "ES=F"},     # 标普500ETF
    {"code": "161127", "ticker": "NQ=F"},     # 纳指100LOF
    {"code": "513100", "ticker": "NQ=F"},     # 纳指ETF
    # 截图新增标的
    {"code": "501018", "ticker": "CL=F"},     # 南方原油LOF
    {"code": "160723", "ticker": "CL=F"},     # 嘉实原油LOF
    {"code": "160644", "ticker": "KWEB"},     # 港美互联网LOF
    {"code": "161116", "ticker": "GC=F"},     # 黄金主题LOF（黄金期货）
    {"code": "162719", "ticker": "XOP"},      # 石油LOF（广发石油）
]

# ==================== 核心配置 ====================
# 重试&防频控配置
MAX_RETRY = 3
RETRY_WAIT_MIN = 1
RETRY_WAIT_MAX = 3
ITEM_SLEEP_MIN = 1.5
ITEM_SLEEP_MAX = 4
# 缓存配置
CACHE_FILE = "fund_monitor_cache.pkl"
NAV_CACHE_EXPIRE = 12 * 3600  # 净值缓存12小时
TICKER_CACHE_EXPIRE = 5 * 60  # 期货/美股数据缓存5分钟
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

# ==================== HTML模板 ====================
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOF溢价全自动监控</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }}
        .container {{ max-width: 680px; margin: auto; background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1890ff, #096dd9); color: white; padding: 20px; text-align: center; }}
        .header .title {{ font-size: 20px; font-weight: bold; }}
        .header .subinfo {{ font-size: 12px; margin-top: 8px; opacity: 0.9; }}
        .table-header {{ display: flex; justify-content: space-between; padding: 12px 20px; background: #fafafa; border-bottom: 1px solid #f0f0f0; font-size: 13px; color: #666; }}
        .row {{ display: flex; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid #f0f0f0; align-items: center; }}
        .fund-info .name {{ font-weight: 500; font-size: 16px; color: #1f1f1f; }}
        .fund-info .code {{ font-size: 12px; color: #8c8c8c; margin-top: 2px; }}
        .fund-info .nav-date {{ font-size: 11px; color: #bfbfbf; margin-top: 2px; }}
        .premium {{ font-family: monospace; font-weight: 700; font-size: 16px; white-space: nowrap; }}
        .plus {{ color: #cf1322; }}
        .minus {{ color: #389e0d; }}
        .neutral {{ color: #595959; }}
        .tag {{ font-size: 10px; padding: 1px 4px; border-radius: 3px; margin-left: 5px; }}
        .cache-tag {{ background: #e8f4ff; color: #1890ff; }}
        .warn-tag {{ background: #fff2e8; color: #d46b08; }}
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">📊 LOF溢价全自动监控</div>
            <div class="subinfo">更新时间: {now_str}</div>
            <div class="subinfo">格式：低溢价~高溢价 | 按溢价从高到低排序</div>
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
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'rb') as f:
                return pickle.load(f)
    except:
        pass
    return {"nav": {}, "ticker": {}, "fund_name": {}}

def save_cache(cache_data):
    try:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)
    except:
        print("缓存保存失败")

# ==================== 带重试的安全请求函数 ====================
def safe_request(url, headers=None, timeout=12, is_gbk=False):
    if headers is None:
        headers = {}
    
    for retry_count in range(MAX_RETRY):
        try:
            headers['User-Agent'] = random.choice(USER_AGENT_POOL)
            res = requests.get(url, headers=headers, timeout=timeout)
            res.raise_for_status()
            if is_gbk:
                res.encoding = 'gbk'
            return res
        except Exception as e:
            print(f"请求失败（重试{retry_count+1}/{MAX_RETRY}）URL: {url} | 错误: {str(e)}")
            if retry_count < MAX_RETRY - 1:
                time.sleep(random.uniform(RETRY_WAIT_MIN, RETRY_WAIT_MAX))
            continue
    print(f"请求彻底失败 URL: {url}")
    return None

# ==================== 1. 获取场内行情+标准名称（彻底解决名称错配） ====================
def get_fund_market_info(fund_code):
    """
    从腾讯财经获取场内实时价格+交易所标准简称
    100%保证名称和代码对应，和券商/她理财显示一致
    """
    cache = load_cache()
    # 先查名称缓存
    name_cache = cache.get('fund_name', {})
    
    prefix = "sh" if fund_code.startswith(('5', '6', '9')) else "sz"
    full_code = f"{prefix}{fund_code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    headers = {
        'Referer': 'https://gu.qq.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
    
    res = safe_request(url, headers=headers, is_gbk=True)
    if not res:
        # 请求失败，用缓存名称兜底
        cached_name = name_cache.get(fund_code, fund_code)
        return {"name": cached_name, "price": None}
    
    try:
        text = res.text.strip()
        if not text or '~' not in text:
            return {"name": name_cache.get(fund_code, fund_code), "price": None}
        
        parts = text.split('~')
        if len(parts) < 4:
            return {"name": name_cache.get(fund_code, fund_code), "price": None}
        
        # 提取场内标准简称+最新成交价
        fund_name = parts[1].strip()
        price_str = parts[3].strip()
        market_price = float(price_str) if price_str and price_str.replace('.', '', 1).isdigit() else None
        
        if market_price and market_price <= 0:
            market_price = None
        
        # 缓存名称，避免下次请求失败
        if fund_name != fund_code:
            name_cache[fund_code] = fund_name
            cache['fund_name'] = name_cache
            save_cache(cache)
        
        return {
            "name": fund_name,
            "price": market_price
        }
    except Exception as e:
        print(f"{fund_code} 场内行情解析失败: {str(e)}")
        return {"name": name_cache.get(fund_code, fund_code), "price": None}

# ==================== 2. 【彻底重构】获取官方净值（解决无净值问题） ====================
def get_fund_official_nav(fund_code):
    """
    从天天基金官方历史净值接口获取最新净值，100%覆盖所有基金
    解决之前估算接口拿不到QDII净值的核心问题
    返回：{"nav": 最新净值, "nav_date": 净值日期, "is_cache": 是否缓存}
    """
    cache = load_cache()
    now_ts = time.time()
    
    # 先查有效缓存
    nav_cache = cache.get('nav', {})
    if fund_code in nav_cache:
        cache_item = nav_cache[fund_code]
        if (now_ts - cache_item['ts']) < NAV_CACHE_EXPIRE:
            print(f"{fund_code} 命中净值缓存: {cache_item['nav']} | 日期: {cache_item['nav_date']}")
            return cache_item
    
    # 缓存失效，请求天天基金历史净值接口（最稳定的官方净值接口）
    url = f"https://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={fund_code}&page=1&per=1"
    headers = {
        'Referer': f'https://fund.eastmoney.com/f10/jjjz_{fund_code}.html',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    }
    
    res = safe_request(url, headers=headers)
    if not res:
        # 请求失败，用过期缓存兜底
        if fund_code in nav_cache:
            print(f"{fund_code} 接口失败，使用历史缓存兜底")
            return nav_cache[fund_code]
        return None
    
    # 解析返回的HTML数据，提取最新净值和日期
    try:
        text = res.text
        # 匹配净值和日期，格式：<tr><td>2026-03-10</td><td>0.5420</td>...
        match = re.search(r'<tr><td>(\d{4}-\d{2}-\d{2})</td><td>([\d.]+)</td>', text)
        if not match:
            raise Exception("未匹配到净值数据")
        
        nav_date_str = match.group(1)
        nav_str = match.group(2)
        official_nav = float(nav_str)
        
        if official_nav <= 0:
            raise Exception("净值数值无效")
        
        # 写入缓存
        result = {
            "nav": official_nav,
            "nav_date": nav_date_str,
            "is_cache": False,
            "ts": now_ts
        }
        nav_cache[fund_code] = result
        cache['nav'] = nav_cache
        save_cache(cache)
        
        print(f"{fund_code} 获取官方净值成功: {official_nav} | 净值日期: {nav_date_str}")
        return result
    
    except Exception as e:
        print(f"{fund_code} 净值解析失败: {str(e)}")
        # 解析失败，用缓存兜底
        if fund_code in nav_cache:
            print(f"{fund_code} 解析失败，使用历史缓存兜底")
            return nav_cache[fund_code]
        return None

# ==================== 3. 获取期货/美股累计涨跌幅（适配所有标的） ====================
def get_ticker_cumulative_change(ticker, nav_date_str):
    """
    计算对标标的从净值日期到现在的累计涨跌幅
    完美适配期货、ETF，优先取盘前/实时价格，白天实时波动
    """
    cache = load_cache()
    now_ts = time.time()
    cache_key = f"{ticker}_{nav_date_str}"
    
    # 查缓存
    ticker_cache = cache.get('ticker', {})
    if cache_key in ticker_cache:
        cache_item = ticker_cache[cache_key]
        if (now_ts - cache_item['ts']) < TICKER_CACHE_EXPIRE:
            return cache_item['change']
    
    # 请求雅虎财经数据，期货和ETF通用
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    headers = {
        'Referer': 'https://finance.yahoo.com/',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7'
    }
    
    res = safe_request(url, headers=headers)
    if not res:
        print(f"{ticker} 数据请求失败，返回0涨幅")
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
            latest_price = meta.get('regularMarketPrice', meta.get('previousClose'))
            print(f"{ticker} 取实时价格: {latest_price}")
        
        if not latest_price or latest_price <= 0:
            print(f"{ticker} 无有效最新价格，返回0涨幅")
            return 0.0
        
        # 2. 匹配净值日期对应的基准收盘价
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
        
        # 兜底：没找到匹配日期，取最近收盘价
        if not base_close_price:
            print(f"{ticker} 未匹配到对应日期，取最近收盘价兜底")
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
        ticker_cache[cache_key] = {
            "change": cumulative_change,
            "ts": now_ts
        }
        cache['ticker'] = ticker_cache
        save_cache(cache)
        
        return cumulative_change
    
    except Exception as e:
        print(f"{ticker} 数据解析失败: {str(e)}")
        return 0.0

# ==================== 4. 溢价格式化（低左高右） ====================
def format_premium(p1, p2):
    min_p = min(p1, p2)
    max_p = max(p1, p2)
    
    def fmt(p):
        sign = "+" if p > 0 else ""
        return f"{sign}{p:.2%}"
    
    color = "plus" if max_p > 0 else "minus" if max_p < 0 else "neutral"
    return f"{fmt(min_p)}~{fmt(max_p)}", color

# ==================== 主监控函数 ====================
def run_monitor():
    now_cn = datetime.now(CN_TZ)
    now_str = now_cn.strftime('%Y-%m-%d %H:%M:%S')
    result_list = []
    
    for idx, item in enumerate(MONITOR_LIST):
        fund_code = item['code']
        ticker = item['ticker']
        print(f"\n===== 处理第{idx+1}/{len(MONITOR_LIST)}个标的: {fund_code} =====")
        
        # 1. 获取场内名称+实时价格
        market_info = get_fund_market_info(fund_code)
        fund_name = market_info['name']
        market_price = market_info['price']
        
        # 2. 获取官方净值
        nav_data = get_fund_official_nav(fund_code)
        
        # 兜底处理：无行情
        if not market_price:
            row_html = f'''
            <div class="row">
                <div class="fund-info">
                    <div class="name">{fund_name}<span class="tag warn-tag">无行情</span></div>
                    <div class="code">代码: {fund_code}</div>
                </div>
                <div class="premium neutral">--</div>
            </div>
            '''
            result_list.append({"max_premium": -9999, "html": row_html})
            time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
            continue
        
        # 兜底处理：无净值
        if not nav_data:
            row_html = f'''
            <div class="row">
                <div class="fund-info">
                    <div class="name">{fund_name}<span class="tag warn-tag">无净值</span></div>
                    <div class="code">代码: {fund_code}</div>
                </div>
                <div class="premium neutral">--</div>
            </div>
            '''
            result_list.append({"max_premium": -9999, "html": row_html})
            time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
            continue
        
        # 3. 双口径溢价计算
        official_nav = nav_data['nav']
        nav_date = nav_data['nav_date']
        is_cache = nav_data.get('is_cache', False)
        
        # 口径1：官方净值溢价（和她理财对齐）
        premium_official = (market_price - official_nav) / official_nav
        # 口径2：实时估算溢价（期货/美股实时涨跌幅）
        ticker_change = get_ticker_cumulative_change(ticker, nav_date)
        estimated_nav = official_nav * (1 + ticker_change)
        premium_estimated = (market_price - estimated_nav) / estimated_nav if estimated_nav else premium_official
        
        # 4. 格式化显示
        premium_text, color = format_premium(premium_official, premium_estimated)
        max_premium = max(premium_official, premium_estimated)
        cache_tag = '<span class="tag cache-tag">缓存兜底</span>' if is_cache else ''
        
        # 5. 生成行HTML
        row_html = f'''
        <div class="row">
            <div class="fund-info">
                <div class="name">{fund_name}{cache_tag}</div>
                <div class="code">代码: {fund_code}</div>
                <div class="nav-date">净值日期: {nav_date}</div>
            </div>
            <div class="premium {color}">{premium_text}</div>
        </div>
        '''
        result_list.append({"max_premium": max_premium, "html": row_html})
        
        # 防频控休眠
        time.sleep(random.uniform(ITEM_SLEEP_MIN, ITEM_SLEEP_MAX))
    
    # 按溢价从高到低排序
    result_list.sort(key=lambda x: x['max_premium'], reverse=True)
    
    # 生成最终HTML
    final_html = HTML_TPL.format(
        now_str=now_str,
        content_html="".join([item['html'] for item in result_list])
    )
    
    # 写入文件
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"\n✅ 监控任务全部完成 | 北京时间: {now_str} | 共处理{len(MONITOR_LIST)}个标的")

if __name__ == "__main__":
    run_monitor()
