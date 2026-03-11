import os
import re
import requests
from datetime import datetime
import pytz
import time

# ==================== 【全自动配置】监控标的中心 ====================
# 现在只需要配置代码、名称、对标ticker，净值会自动获取，无需手动更新！
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

# 全局缓存，避免短时间内重复请求净值（净值一天只更一次，缓存2小时）
NAV_CACHE = {}
CACHE_DURATION_SECONDS = 7200

# HTML 模板
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha 全自动套利监控</title>
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

def get_latest_official_nav(fund_code):
    """
    自动获取国内基金的最新官方单位净值
    数据源：天天基金网 (Eastmoney)
    """
    global NAV_CACHE
    now_ts = time.time()
    
    # 1. 检查缓存，如果有有效缓存直接返回
    if fund_code in NAV_CACHE:
        cache_data = NAV_CACHE[fund_code]
        if (now_ts - cache_data['ts']) < CACHE_DURATION_SECONDS:
            return cache_data['nav']
    
    # 2. 缓存未命中，发起网络请求
    # 使用天天基金网的移动端接口，数据轻量且稳定
    api_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'Referer': 'http://fund.eastmoney.com/'
    }
    
    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        res.raise_for_status()
        text = res.text
        
        # 解析返回的JSONP数据
        # 数据格式类似：jsonpgz({"dwjz":"1.2340","gsz":"1.2400",...});
        match = re.search(r'jsonpgz\((.*?)\);', text)
        if not match:
            return None
        
        import json
        data = json.loads(match.group(1))
        
        # 'dwjz' 字段代表：昨日净值 (即最新官方公布净值)
        # 对于QDII，如果是在白天交易时间，'dwjz'通常是T-1日的净值，也就是我们能拿到的最新官方数据
        nav_str = data.get('dwjz')
        if not nav_str:
            return None
            
        latest_nav = float(nav_str)
        
        # 写入缓存
        NAV_CACHE[fund_code] = {
            'nav': latest_nav,
            'ts': now_ts
        }
        
        return latest_nav
        
    except Exception as e:
        print(f"自动获取基金{fund_code}净值失败: {str(e)}")
        # 如果获取失败且有旧缓存，凑合着用旧缓存
        if fund_code in NAV_CACHE:
            return NAV_CACHE[fund_code]['nav']
        return None

def get_us_ticker_change(ticker):
    """获取海外对标ETF的涨跌幅"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        chart_data = res.json()['chart']['result'][0]
        meta = chart_data['meta']
        latest_price = meta.get('regularMarketPrice', meta.get('previousClose'))
        prev_close = meta.get('previousClose')
        if not latest_price or not prev_close or prev_close == 0:
            return 0.0
        return (latest_price / prev_close) - 1
    except Exception as e:
        print(f"获取海外标的{ticker}数据失败: {str(e)}")
        return 0.0

def get_cn_fund_market_price(code):
    """获取国内LOF/ETF的实时二级市场成交价"""
    prefix = "sh" if code.startswith(('5', '6', '9')) else "sz"
    full_code = f"{prefix}{code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        res.encoding = 'gbk'
        text = res.text.strip()
        if not text or '~' not in text:
            return None
        parts = text.split('~')
        if len(parts) > 3 and parts[3].strip():
            price = float(parts[3])
            return price if price > 0 else None
        return None
    except Exception as e:
        print(f"获取国内基金{code}价格失败: {str(e)}")
        return None

def format_premium_text(premium_value):
    sign = "+" if premium_value > 0 else ""
    formatted_text = f"{sign}{premium_value:.2%}"
    if premium_value > 0:
        color_class = "plus"
    elif premium_value < 0:
        color_class = "minus"
    else:
        color_class = "neutral"
    return formatted_text, color_class

def run_monitor_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(sh_tz)
    now_str = now_time.strftime('%Y-%m-%d %H:%M:%S')
    html_rows = []

    for fund_code, fund_info in FUND_CONFIG.items():
        # 1. 获取国内实时价格
        market_price = get_cn_fund_market_price(fund_code)
        # 2. 自动获取最新官方净值 (核心优化！)
        official_nav = get_latest_official_nav(fund_code)
        
        if not market_price or not official_nav:
            # 数据不全时的显示
            status_text = "数据缺失" if not market_price else "净值更新中"
            row_html = f'''
            <div class="row">
                <div>
                    <div class="name">{fund_info["name"]}</div>
                    <div class="code">代码: {fund_code}</div>
                </div>
                <div class="premium neutral">{status_text}</div>
            </div>
            '''
            html_rows.append(row_html)
            continue
        
        # 3. 双口径计算
        # 口径1：基于自动获取的官方净值
        premium_official = (market_price - official_nav) / official_nav
        
        # 口径2：基于实时估算
        us_change = get_us_ticker_change(fund_info["ticker"])
        estimated_nav = official_nav * (1 + us_change)
        premium_estimated = (market_price - estimated_nav) / estimated_nav

        # 4. 格式化
        official_text, _ = format_premium_text(premium_official)
        estimated_text, color = format_premium_text(premium_estimated)
        display_text = f"{official_text}~{estimated_text}"

        row_html = f'''
        <div class="row">
            <div>
                <div class="name">{fund_info["name"]}</div>
                <div class="code">代码: {fund_code}</div>
            </div>
            <div class="premium {color}">{display_text}</div>
        </div>
        '''
        html_rows.append(row_html)

    final_html = HTML_TPL.format(now_str=now_str, content_html="".join(html_rows))
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"[全自动] 监控更新完成 | 北京: {now_str}")

if __name__ == "__main__":
    run_monitor_task()
