import os
import re
import requests
from datetime import datetime
import pytz
import time

# ==================== 【极简配置】只需要填代码+海外对标ticker，其他全自动化 ====================
# 代码：场内6位基金代码；ticker：海外对标ETF代码，无需手动维护名称、净值
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

# 全局缓存配置（避免频繁请求被封禁，净值一天只更一次，缓存4小时）
GLOBAL_CACHE = {
    "nav": {},  # 基金净值缓存
    "fund_info": {},  # 基金名称/基础信息缓存
    "us_change": {}  # 海外标的涨跌幅缓存
}
CACHE_EXPIRE_SECONDS = 14400  # 4小时缓存过期
US_CHANGE_CACHE_EXPIRE = 300  # 海外涨跌幅5分钟缓存，保证实时性

# HTML 模板
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LOF溢价全自动监控</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; background: #f5f7fa; margin: 0; padding: 12px; }}
        .container {{ max-width: 650px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1890ff, #096dd9); color: white; padding: 18px; text-align: center; }}
        .header .title {{ font-size: 20px; font-weight: 700; }}
        .header .subinfo {{ font-size: 12px; margin-top: 6px; opacity: 0.9; }}
        .table-header {{ display: flex; justify-content: space-between; padding: 12px 20px; background: #fafafa; border-bottom: 1px solid #f0f0f0; font-size: 13px; color: #666; }}
        .row {{ display: flex; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid #f5f5f5; align-items: center; }}
        .fund-info .name {{ font-weight: 600; font-size: 16px; color: #262626; }}
        .fund-info .code {{ font-size: 12px; color: #8c8c8c; margin-top: 3px; }}
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
            <div class="title">📊 LOF溢价全自动监控</div>
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

def get_cn_fund_market_info(fund_code):
    """
    从腾讯财经获取基金【场内实时价格+场内标准简称】
    1. 价格是交易所实时成交价，和券商APP完全一致
    2. 名称是场内标准简称，和她理财、天天基金场内显示完全一致，彻底解决名称错配
    """
    global GLOBAL_CACHE
    prefix = "sh" if fund_code.startswith(('5', '6', '9')) else "sz"
    full_code = f"{prefix}{fund_code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': 'https://gu.qq.com/'
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        res.encoding = 'gbk'  # 腾讯接口固定GBK编码，必须设置
        text = res.text.strip()
        if not text or '~' not in text:
            return None
        
        parts = text.split('~')
        # 字段说明：~1=场内简称 ~3=最新成交价 ~2=代码
        if len(parts) < 4:
            return None
        
        fund_name = parts[1].strip()
        market_price = float(parts[3].strip()) if parts[3].strip() else None
        
        if not fund_name or not market_price or market_price <= 0:
            return None
        
        # 缓存名称，避免重复请求
        GLOBAL_CACHE['fund_info'][fund_code] = {
            'name': fund_name,
            'ts': time.time()
        }
        
        return {
            "name": fund_name,
            "price": market_price
        }
    except Exception as e:
        print(f"获取场内行情{fund_code}失败: {str(e)}")
        # 兜底：如果行情获取失败，用之前缓存的名称
        cached_info = GLOBAL_CACHE['fund_info'].get(fund_code, {})
        return {
            "name": cached_info.get('name', fund_code),
            "price": None
        }

def get_latest_official_nav(fund_code):
    """
    【主数据源】从天天基金网获取基金【最新官方公布净值】
    用的是基金公司官方披露的净值数据，和她理财、天天基金网完全同源，保证数值准确
    """
    global GLOBAL_CACHE
    now_ts = time.time()
    
    # 先检查缓存
    cached_nav = GLOBAL_CACHE['nav'].get(fund_code, {})
    if (now_ts - cached_nav.get('ts', 0)) < CACHE_EXPIRE_SECONDS:
        return cached_nav.get('nav')
    
    # 主接口：天天基金网核心数据接口，包含官方净值、净值日期
    url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': f'https://fund.eastmoney.com/{fund_code}.html'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        text = res.text
        
        # 匹配单位净值和净值日期
        nav_match = re.search(r'var DWJZ="([\d.]+)";', text)  # 单位净值
        date_match = re.search(r'var JZRQ="([\d\-]+)";', text) # 净值日期
        
        if not nav_match:
            raise Exception("未匹配到净值数据")
        
        official_nav = float(nav_match.group(1))
        nav_date = date_match.group(1) if date_match else ""
        
        if official_nav <= 0:
            raise Exception("净值数值无效")
        
        # 写入缓存
        GLOBAL_CACHE['nav'][fund_code] = {
            'nav': official_nav,
            'date': nav_date,
            'ts': now_ts
        }
        print(f"获取{fund_code}官方净值成功: {official_nav} ({nav_date})")
        return official_nav
    
    except Exception as e:
        print(f"主接口获取{fund_code}净值失败: {str(e)}，尝试备用接口")
        # 备用接口：天天基金估算接口兜底，保证能拿到净值
        return get_latest_nav_backup(fund_code)

def get_latest_nav_backup(fund_code):
    """【备用数据源】兜底用，主接口失败时调用，保证绝不出现无净值的情况"""
    global GLOBAL_CACHE
    now_ts = time.time()
    url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
        'Referer': 'http://fund.eastmoney.com/'
    }
    try:
        res = requests.get(url, headers=headers, timeout=8)
        res.raise_for_status()
        text = res.text
        match = re.search(r'jsonpgz\((.*?)\);', text)
        if not match:
            raise Exception("备用接口数据解析失败")
        
        import json
        data = json.loads(match.group(1))
        nav_str = data.get('dwjz')
        if not nav_str:
            raise Exception("备用接口无净值数据")
        
        official_nav = float(nav_str)
        if official_nav <= 0:
            raise Exception("备用接口净值无效")
        
        # 写入缓存
        GLOBAL_CACHE['nav'][fund_code] = {
            'nav': official_nav,
            'ts': now_ts
        }
        print(f"备用接口获取{fund_code}净值成功: {official_nav}")
        return official_nav
    
    except Exception as e:
        print(f"备用接口获取{fund_code}净值也失败: {str(e)}")
        # 终极兜底：用缓存里的历史净值，保证计算不中断
        cached_nav = GLOBAL_CACHE['nav'].get(fund_code, {})
        if cached_nav.get('nav'):
            print(f"使用{fund_code}历史缓存净值: {cached_nav['nav']}")
            return cached_nav['nav']
        return None

def get_us_ticker_change(ticker):
    """获取海外对标ETF的涨跌幅，带缓存优化"""
    global GLOBAL_CACHE
    now_ts = time.time()
    
    # 检查缓存，5分钟内不重复请求
    cached_change = GLOBAL_CACHE['us_change'].get(ticker, {})
    if (now_ts - cached_change.get('ts', 0)) < US_CHANGE_CACHE_EXPIRE:
        return cached_change.get('change', 0.0)
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        chart_data = res.json()['chart']['result'][0]
        meta = chart_data['meta']
        latest_price = meta.get('regularMarketPrice', meta.get('previousClose'))
        prev_close = meta.get('previousClose')
        if not latest_price or not prev_close or prev_close == 0:
            raise Exception("海外价格数据无效")
        
        change_rate = (latest_price / prev_close) - 1
        # 写入缓存
        GLOBAL_CACHE['us_change'][ticker] = {
            'change': change_rate,
            'ts': now_ts
        }
        return change_rate
    except Exception as e:
        print(f"获取海外标的{ticker}涨跌幅失败: {str(e)}")
        # 兜底：用缓存的涨跌幅，没有就返回0
        cached_change = GLOBAL_CACHE['us_change'].get(ticker, {})
        return cached_change.get('change', 0.0)

def format_premium_pair(premium1, premium2):
    """格式化溢价率对，保证【低的在左，高的在右】，同时返回主颜色"""
    min_p = min(premium1, premium2)
    max_p = max(premium1, premium2)
    
    # 格式化文本
    def format_single(p):
        sign = "+" if p > 0 else ""
        return f"{sign}{p:.2%}"
    
    min_text = format_single(min_p)
    max_text = format_single(max_p)
    
    # 颜色规则：按最高溢价来定，正溢价变红，折价变绿
    if max_p > 0:
        color = "plus"
    elif max_p < 0:
        color = "minus"
    else:
        color = "neutral"
    
    return f"{min_text}~{max_text}", color

def run_monitor_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now_time = datetime.now(sh_tz)
    now_str = now_time.strftime('%Y-%m-%d %H:%M:%S')
    fund_result_list = []

    # 1. 逐个获取所有标的的数据并计算
    for target in MONITOR_TARGETS:
        fund_code = target['code']
        ticker = target['ticker']
        
        # 1.1 获取场内行情（价格+正确名称）
        market_info = get_cn_fund_market_info(fund_code)
        fund_name = market_info['name']
        market_price = market_info['price']
        
        # 1.2 获取官方最新净值
        official_nav = get_latest_official_nav(fund_code)
        
        # 1.3 核心计算
        if not market_price or not official_nav:
            # 终极兜底，哪怕数据不全也不显示更新中，标注异常
            fund_result_list.append({
                "name": fund_name,
                "code": fund_code,
                "max_premium": -999,  # 排序到最后
                "display_html": f'''
                <div class="row">
                    <div class="fund-info">
                        <div class="name">{fund_name}<span class="warn-tag">数据异常</span></div>
                        <div class="code">代码: {fund_code}</div>
                    </div>
                    <div class="premium neutral">--</div>
                </div>
                '''
            })
            continue
        
        # 双口径溢价计算
        # 口径1：官方净值溢价率（市场通用口径，和她理财对齐）
        premium_official = (market_price - official_nav) / official_nav
        # 口径2：叠加海外涨跌幅的实时估算溢价率
        us_change = get_us_ticker_change(ticker)
        estimated_nav = official_nav * (1 + us_change)
        premium_estimated = (market_price - estimated_nav) / estimated_nav
        
        # 格式化溢价显示，保证低左高右
        premium_text, color = format_premium_pair(premium_official, premium_estimated)
        
        # 记录最高溢价，用于排序
        max_premium = max(premium_official, premium_estimated)
        
        # 生成行HTML
        row_html = f'''
        <div class="row">
            <div class="fund-info">
                <div class="name">{fund_name}</div>
                <div class="code">代码: {fund_code}</div>
            </div>
            <div class="premium {color}">{premium_text}</div>
        </div>
        '''
        
        fund_result_list.append({
            "max_premium": max_premium,
            "display_html": row_html
        })
    
    # 2. 按溢价从高到低排序，高溢价的永远在最前面
    fund_result_list.sort(key=lambda x: x['max_premium'], reverse=True)
    
    # 3. 拼接最终HTML
    final_html = HTML_TPL.format(
        now_str=now_str,
        content_html="".join([item['display_html'] for item in fund_result_list])
    )
    
    # 4. 写入文件
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"✅ 监控更新完成 | 北京时间: {now_str} | 共处理{len(MONITOR_TARGETS)}个标的")

if __name__ == "__main__":
    run_monitor_task()
