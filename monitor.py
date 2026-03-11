import os
import re
import random
import requests
from datetime import datetime, timedelta
import pytz
import time

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

# ==================== 反爬与稳定性配置 ====================
# 随机User-Agent池，避免被识别为机器人
USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
]
# 请求重试配置
MAX_RETRY = 3  # 单次请求最大重试次数
RETRY_WAIT_MIN = 1  # 重试前最小等待秒数
RETRY_WAIT_MAX = 3  # 重试前最大等待秒数
# 单标的处理后休眠（核心防频控）
REQUEST_SLEEP_MIN = 2  # 每个标的处理完最少休眠秒数
REQUEST_SLEEP_MAX = 4  # 每个标的处理完最多休眠秒数

# 时区配置（核心解决日期对齐问题）
CN_TZ = pytz.timezone('Asia/Shanghai')
US_EAST_TZ = pytz.timezone('America/New_York')  # 美股交易时区
UTC_TZ = pytz.UTC

# 单次运行内的缓存（解决同ticker重复请求问题，单次运行内有效）
RUNTIME_CACHE = {
    "us_ticker_data": {},  # 美股ticker数据缓存，同ticker只请求一次
    "fund_nav_data": {}    # 基金净值数据缓存
}

# ==================== HTML渲染模板 ====================
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOF溢价精准监控</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; background: #f5f7fa; margin: 0; padding: 12px; }}
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
    </style>
    <meta http-equiv="refresh" content="60">
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">📊 LOF溢价精准监控</div>
            <div class="subinfo">更新时间: {now_str} | 格式：官方净值溢价~实时估算溢价 | 按溢价从高到低排序</div>
        </div>
        <div class="table-header">
            <span>基金标的</span>
            <span>溢价率区间</span>
        </div>
        {content_html}
    </div>
</body>
</html>"""

# ==================== 核心工具函数 ====================
def request_with_retry(url, headers=None, timeout=10, is_gbk=False):
    """
    带重试、随机UA的通用请求函数，核心解决反爬和请求失败问题
    """
    if headers is None:
        headers = {}
    
    for retry_count in range(MAX_RETRY):
        try:
            # 每次请求随机换UA
            headers['User-Agent'] = random.choice(USER_AGENT_POOL)
            res = requests.get(url, headers=headers, timeout=timeout)
            res.raise_for_status()  # 抛出HTTP状态码异常
            if is_gbk:
                res.encoding = 'gbk'
            return res
        except Exception as e:
            print(f"请求失败（重试{retry_count+1}/{MAX_RETRY}）URL: {url} | 错误: {str(e)}")
            if retry_count < MAX_RETRY - 1:
                # 重试前随机等待
                time.sleep(random.uniform(RETRY_WAIT_MIN, RETRY_WAIT_MAX))
            continue
    # 所有重试都失败
    print(f"请求彻底失败 URL: {url}")
    return None

def get_cn_fund_market_info(fund_code):
    """
    获取国内基金场内【标准简称+实时成交价】，带重试机制
    """
    prefix = "sh" if fund_code.startswith(('5', '6', '9')) else "sz"
    full_code = f"{prefix}{fund_code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    
    res = request_with_retry(url, is_gbk=True)
    if not res:
        return {"name": fund_code, "price": None}
    
    try:
        text = res.text.strip()
        if not text or '~' not in text:
            return {"name": fund_code, "price": None}
        
        parts = text.split('~')
        if len(parts) < 4:
            return {"name": fund_code, "price": None}
        
        fund_name = parts[1].strip()
        price_str = parts[3].strip()
        market_price = float(price_str) if price_str else None
        
        if market_price and market_price <= 0:
            market_price = None
        
        return {
            "name": fund_name,
            "price": market_price
        }
    except Exception as e:
        print(f"解析{fund_code}场内行情失败: {str(e)}")
        return {"name": fund_code, "price": None}

def get_fund_official_nav(fund_code):
    """
    【核心优化】获取基金【最新官方净值+净值日期】，和她理财同源，解决T-1/T-2错位问题
    返回格式: {"nav": 1.234, "nav_date": "2026-03-10"} 失败返回None
    """
    # 先查运行时缓存
    if fund_code in RUNTIME_CACHE['fund_nav_data']:
        return RUNTIME_CACHE['fund_nav_data'][fund_code]
    
    # 主接口：天天基金网核心净值接口，稳定获取官方净值和日期
    url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
    headers = {
        "Referer": f"https://fund.eastmoney.com/{fund_code}.html",
        "Host": "fund.eastmoney.com"
    }
    
    res = request_with_retry(url, headers=headers)
    if not res:
        return None
    
    try:
        text = res.text
        # 匹配单位净值和净值日期
        nav_match = re.search(r'var DWJZ="([\d.]+)";', text)
        date_match = re.search(r'var JZRQ="([\d\-]+)";', text)
        
        if not nav_match or not date_match:
            print(f"{fund_code} 未匹配到净值/净值日期")
            return None
        
        official_nav = float(nav_match.group(1))
        nav_date_str = date_match.group(1)
        
        # 校验数据有效性
        if official_nav <= 0 or not nav_date_str:
            print(f"{fund_code} 净值数据无效")
            return None
        
        # 存入运行时缓存
        result = {
            "nav": official_nav,
            "nav_date": nav_date_str
        }
        RUNTIME_CACHE['fund_nav_data'][fund_code] = result
        print(f"获取{fund_code}官方净值成功: {official_nav} | 净值日期: {nav_date_str}")
        return result
    
    except Exception as e:
        print(f"解析{fund_code}净值数据失败: {str(e)}")
        return None

def get_us_ticker_cumulative_change(ticker, nav_date_str):
    """
    【彻底重构】计算对标美股从净值日期到现在的累计涨跌幅，解决日期错位、盘前数据缺失问题
    1. 优先取盘前/盘后最新价格，白天A股时段也能拿到实时变动
    2. 按净值日期对齐基准收盘价，解决T-1/T-2净值滞后问题
    3. 同ticker单次运行只请求一次，减少频控
    """
    # 先查运行时缓存，同ticker复用数据
    cache_key = f"{ticker}_{nav_date_str}"
    if cache_key in RUNTIME_CACHE['us_ticker_data']:
        return RUNTIME_CACHE['us_ticker_data'][cache_key]
    
    # 雅虎财经接口，取5天数据，覆盖净值滞后的场景，同时拿到K线和最新价格
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    headers = {
        "Referer": "https://finance.yahoo.com/",
        "Host": "query1.finance.yahoo.com"
    }
    
    res = request_with_retry(url, headers=headers)
    if not res:
        print(f"{ticker} 美股数据请求失败，返回0涨幅")
        return 0.0
    
    try:
        data = res.json()
        chart_result = data['chart']['result'][0]
        meta = chart_result['meta']
        timestamp_list = chart_result['timestamp']
        quote_data = chart_result['indicators']['quote'][0]
        
        # ==================== 步骤1：获取最新价格（优先盘前>盘后>常规收盘价）====================
        # 优先级：盘前价格 > 盘后价格 > 常规市场收盘价
        latest_price = None
        # 先看有没有盘前价格
        if 'preMarketPrice' in meta and meta['preMarketPrice']:
            latest_price = meta['preMarketPrice']
            print(f"{ticker} 取盘前价格: {latest_price}")
        # 再看有没有盘后价格
        elif 'postMarketPrice' in meta and meta['postMarketPrice']:
            latest_price = meta['postMarketPrice']
            print(f"{ticker} 取盘后价格: {latest_price}")
        # 最后取常规收盘价
        else:
            latest_price = meta.get('regularMarketPrice')
            print(f"{ticker} 取常规收盘价: {latest_price}")
        
        if not latest_price or latest_price <= 0:
            print(f"{ticker} 无有效最新价格，返回0涨幅")
            return 0.0
        
        # ==================== 步骤2：找到净值日期对应的美股基准收盘价 ====================
        # 把净值日期（北京时间字符串）转换成美东时间的日期，匹配美股交易日
        nav_date_cn = datetime.strptime(nav_date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ)
        # 净值日期对应的美股交易日：QDII基金T日净值，对应的是T日美股收盘（北京时间T+1凌晨）
        # 比如净值日期2026-03-10，对应的是美股3月10日的收盘价
        nav_date_us = nav_date_cn.astimezone(US_EAST_TZ).date()
        
        # 遍历5天的K线，找到对应日期的收盘价
        base_close_price = None
        for i, ts in enumerate(timestamp_list):
            # 把K线的UTC时间戳转成美东时间
            kline_datetime_utc = UTC_TZ.localize(datetime.utcfromtimestamp(ts))
            kline_date_us = kline_datetime_utc.astimezone(US_EAST_TZ).date()
            
            # 找到和净值日期匹配的K线
            if kline_date_us == nav_date_us:
                close_list = quote_data['close']
                if close_list and close_list[i]:
                    base_close_price = close_list[i]
                    print(f"{ticker} 匹配净值日期{nav_date_str} 基准收盘价: {base_close_price}")
                    break
        
        # 如果没找到完全匹配的，取最近的一个收盘价兜底
        if not base_close_price:
            print(f"{ticker} 未找到{nav_date_str}对应K线，取最近收盘价兜底")
            close_list = quote_data['close']
            valid_closes = [c for c in close_list if c and c > 0]
            if valid_closes:
                base_close_price = valid_closes[-1]
            else:
                base_close_price = meta.get('previousClose')
        
        if not base_close_price or base_close_price <= 0:
            print(f"{ticker} 无有效基准收盘价，返回0涨幅")
            return 0.0
        
        # ==================== 步骤3：计算累计涨跌幅 ====================
        cumulative_change = (latest_price - base_close_price) / base_close_price
        print(f"{ticker} 累计涨跌幅: {cumulative_change:.4%}")
        
        # 存入运行时缓存
        RUNTIME_CACHE['us_ticker_data'][cache_key] = cumulative_change
        return cumulative_change
    
    except Exception as e:
        print(f"解析{ticker}美股数据失败: {str(e)}")
        return 0.0

def format_premium_pair(premium1, premium2):
    """
    格式化溢价率，保证【低溢价在左，高溢价在右】，同时返回显示颜色
    """
    min_p = min(premium1, premium2)
    max_p = max(premium1, premium2)
    
    def format_single(p):
        sign = "+" if p > 0 else ""
        return f"{sign}{p:.2%}"
    
    min_text = format_single(min_p)
    max_text = format_single(max_p)
    
    # 颜色规则：按最高溢价判断，正红负绿
    if max_p > 0:
        color = "plus"
    elif max_p < 0:
        color = "minus"
    else:
        color = "neutral"
    
    return f"{min_text}~{max_text}", color

# ==================== 主运行函数 ====================
def run_monitor_task():
    now_cn = datetime.now(CN_TZ)
    now_str = now_cn.strftime('%Y-%m-%d %H:%M:%S')
    fund_result_list = []

    # 遍历所有监控标的
    for idx, target in enumerate(MONITOR_TARGETS):
        fund_code = target['code']
        ticker = target['ticker']
        print(f"\n===== 处理第{idx+1}/{len(MONITOR_TARGETS)}个标的: {fund_code} =====")
        
        # 1. 获取场内行情（名称+实时价格）
        market_info = get_cn_fund_market_info(fund_code)
        fund_name = market_info['name']
        market_price = market_info['price']
        
        # 2. 获取官方净值+净值日期
        nav_data = get_fund_official_nav(fund_code)
        official_nav = nav_data['nav'] if nav_data else None
        nav_date_str = nav_data['nav_date'] if nav_data else ""
        
        # 3. 数据有效性判断，兜底处理
        if not market_price:
            print(f"{fund_code} 无有效场内价格")
            row_html = f'''
            <div class="row">
                <div class="fund-info">
                    <div class="name">{fund_name}<span class="warn-tag">无行情</span></div>
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
            time.sleep(random.uniform(REQUEST_SLEEP_MIN, REQUEST_SLEEP_MAX))
            continue
        
        if not official_nav:
            print(f"{fund_code} 无有效官方净值")
            row_html = f'''
            <div class="row">
                <div class="fund-info">
                    <div class="name">{fund_name}<span class="warn-tag">无净值</span></div>
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
            time.sleep(random.uniform(REQUEST_SLEEP_MIN, REQUEST_SLEEP_MAX))
            continue
        
        # 4. 双口径溢价率核心计算
        # --- 口径1：官方净值溢价率（市场通用口径，和她理财对齐）---
        premium_official = (market_price - official_nav) / official_nav
        
        # --- 口径2：精准估算溢价率（对齐净值日期的累计涨跌幅）---
        cumulative_change = get_us_ticker_cumulative_change(ticker, nav_date_str)
        estimated_nav = official_nav * (1 + cumulative_change)
        premium_estimated = (market_price - estimated_nav) / estimated_nav
        
        # 5. 格式化显示
        premium_text, color = format_premium_pair(premium_official, premium_estimated)
        max_premium = max(premium_official, premium_estimated)
        
        # 6. 生成行HTML
        row_html = f'''
        <div class="row">
            <div class="fund-info">
                <div class="name">{fund_name}</div>
                <div class="code">代码: {fund_code}</div>
                <div class="nav-date">净值日期: {nav_date_str}</div>
            </div>
            <div class="premium {color}">{premium_text}</div>
        </div>
        '''
        
        fund_result_list.append({
            "max_premium": max_premium,
            "html": row_html
        })
        
        # 【核心防频控】每个标的处理完，随机休眠，避免密集请求被封
        time.sleep(random.uniform(REQUEST_SLEEP_MIN, REQUEST_SLEEP_MAX))
    
    # 按溢价从高到低排序，高溢价排在最前面
    fund_result_list.sort(key=lambda x: x['max_premium'], reverse=True)
    
    # 生成最终HTML
    final_html = HTML_TPL.format(
        now_str=now_str,
        content_html="".join([item['html'] for item in fund_result_list])
    )
    
    # 写入文件
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"\n✅ 监控任务全部完成 | 北京时间: {now_str} | 共处理{len(MONITOR_TARGETS)}个标的")

if __name__ == "__main__":
    run_monitor_task()
