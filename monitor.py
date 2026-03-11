import os
import re
import random
import requests
from datetime import datetime
import pytz
import time
import pickle


# ==================== 【核心配置】支持复合权重与汇率对冲 ====================
# 配置说明：
# us_ticker: 美股对标代码
# us_weight: 美股资产占比
# cn_ticker: 国内对标指数/ETF代码 (这里以芯片ETF 159995 为例代表中证芯片产业)
# cn_weight: 国内资产占比
# usd_exposure: 美元汇率敞口比例 (通常与美股权重一致)
# ==================== 【全量精算版】17个标的完整配置 ====================
# ==================== 【校对版】17个标的官方名称及参数 ====================
FUND_CONFIG = {
    # --- 原油及商品类 ---
    "160216": {"name": "国泰原油", "us_ticker": "CL=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "160416": {"name": "石油基金", "us_ticker": "CL=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95}, # 已修正：诺安石油
    "161129": {"name": "原油LOF", "us_ticker": "CL=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},  # 易方达原油
    "501018": {"name": "南方原油", "us_ticker": "CL=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95}, # 南方原油C
    "160723": {"name": "嘉实原油", "us_ticker": "CL=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "162719": {"name": "广发石油", "us_ticker": "XOP", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "162411": {"name": "华宝油气", "us_ticker": "XOP", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},

    # --- 黄金类 ---
    "161116": {"name": "易基黄金", "us_ticker": "GC=F", "us_weight": 0.50, "cn_ticker": "sh600547", "cn_weight": 0.45, "usd_exposure": 0.50},
    "160719": {"name": "嘉实黄金", "us_ticker": "GC=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "161226": {"name": "国泰黄金", "us_ticker": "GC=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "164701": {"name": "添富黄金", "us_ticker": "GC=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},

    # --- 科技及行业类 ---
    "501225": {"name": "全球芯片", "us_ticker": "SOXX", "us_weight": 0.75, "cn_ticker": "sz159995", "cn_weight": 0.15, "usd_exposure": 0.75},
    "159509": {"name": "纳指科技", "us_ticker": "NQ=F", "us_weight": 0.98, "cn_weight": 0.0, "usd_exposure": 0.98},
    "161128": {"name": "标普科技", "us_ticker": "XLK", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "162415": {"name": "生物科技", "us_ticker": "XBI", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "164906": {"name": "中概互联", "us_ticker": "KWEB", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.50},
    "160644": {"name": "港美互联", "us_ticker": "KWEB", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.50},

    # --- 宽基类 ---
    "161125": {"name": "标普500", "us_ticker": "ES=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "513500": {"name": "标普ETF", "us_ticker": "ES=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "161127": {"name": "纳指100", "us_ticker": "NQ=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
    "513100": {"name": "纳指ETF", "us_ticker": "NQ=F", "us_weight": 0.95, "cn_weight": 0.0, "usd_exposure": 0.95},
}

# ==================== 基础配置与缓存 ====================
CACHE_FILE = "fund_cache.pkl"
CACHE_DURATION_SECONDS = 2 * 3600  
CN_TZ = pytz.timezone('Asia/Shanghai')

USER_AGENT_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
]

def safe_request(url, headers=None, timeout=10):
    if headers is None: headers = {}
    headers['User-Agent'] = random.choice(USER_AGENT_POOL)
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

# ==================== 数据获取模块 ====================

def get_latest_official_nav(fund_code):
    """获取最新官方净值 (口径1的基础)"""
    # 简化版示例，建议保留你原有的缓存逻辑
    api_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
    res = safe_request(api_url)
    if not res: return None
    try:
        match = re.search(r'jsonpgz\((.*?)\);', res.text)
        if match:
            import json
            data = json.loads(match.group(1))
            return float(data.get('dwjz'))
    except:
        pass
    return None

def get_cn_market_data(code):
    """获取A股场内价格或指数涨跌幅"""
    if not code: return None, 0.0
    prefix = "sh" if code.startswith(('5', '6', '9')) else "sz"
    # 如果代码已经带有 sz/sh 前缀则不加
    full_code = code if code.startswith(('sh', 'sz')) else f"{prefix}{code}"
    url = f"http://qt.gtimg.cn/q={full_code}"
    res = safe_request(url, timeout=8)
    if not res: return None, 0.0
    try:
        res.encoding = 'gbk'
        parts = res.text.split('~')
        price = float(parts[3]) if len(parts) > 3 else None
        change_pct = float(parts[32]) / 100.0 if len(parts) > 32 else 0.0 # 腾讯接口32位是涨跌幅%
        return price, change_pct
    except:
        return None, 0.0

def get_yahoo_change(ticker):
    """获取美股/汇率涨跌幅 (使用Yahoo API)"""
    if not ticker: return 0.0
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
    res = safe_request(url)
    if not res: return 0.0
    try:
        data = res.json()
        meta = data['chart']['result'][0]['meta']
        latest = meta.get('regularMarketPrice', meta.get('previousClose'))
        prev = meta.get('previousClose')
        if not latest or not prev or prev == 0: return 0.0
        return (latest / prev) - 1
    except:
        return 0.0

# ==================== 格式化与输出 ====================

def format_premium(premium):
    sign = "+" if premium > 0 else ""
    color = "plus" if premium > 0 else "minus" if premium < 0 else "neutral"
    return f"{sign}{premium:.2%}", color

def run_monitor_task():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    
    # 获取实时美元兑人民币汇率涨跌幅
    fx_change = get_yahoo_change("CNY=X") 

    for code, info in FUND_CONFIG.items():
        name = info['name']
        
        # 1. 获取场内交易价格
        mp, _ = get_cn_market_data(code)
        # 2. 获取官方 T-1 净值
        nav = get_latest_official_nav(code)

        if not mp or not nav:
            rows.append(f'<div class="row"><div><div class="name">{name}</div><div class="code">{code}</div></div><div class="premium neutral">数据缺失</div></div>')
            continue

        # ==================== 核心逻辑计算 ====================
        
        # 口径 1: 官方分口径溢价率 (直接计算)
        p1 = (mp - nav) / nav
        
        # 获取各底层资产涨跌幅
        us_change = get_yahoo_change(info.get('us_ticker'))
        cn_change = get_cn_market_data(info.get('cn_ticker'))[1]
        
        # 提取权重参数 (没有配置则默认为0)
        us_weight = info.get('us_weight', 0.0)
        cn_weight = info.get('cn_weight', 0.0)
        usd_exposure = info.get('usd_exposure', 0.0)
        
        # 口径 2: 公允估算净值 (严格套用截图公式)
        # 估算当日净值涨跌幅 = 海外成分(资产涨跌 + 汇率涨跌) + 国内成分(国内涨跌)
        est_daily_return = (us_weight * us_change) + (usd_exposure * fx_change) + (cn_weight * cn_change)
        
        # 计算估算净值及实时溢价率
        est_nav = nav * (1 + est_daily_return)
        p2 = (mp - est_nav) / est_nav if est_nav else p1


        # 在 HTML 模板里的 <head> 部分加上这一行，强制浏览器每分钟重新抓取
HTML_TPL = """
<head>
    ...
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <meta http-equiv="refresh" content="60">
</head>
"""
        # ==================== 渲染 HTML ====================
        t1, c1 = format_premium(p1)
        t2, c2 = format_premium(p2)
        display = f"{t1} ~ {t2}"

        rows.append(f'''
        <div class="row">
            <div>
                <div class="name">{name}</div>
                <div class="code">代码: {code}</div>
            </div>
            <div class="premium {c2}">{display}</div>
        </div>''')

    # （此处省略 HTML_TPL 的拼接保存逻辑，与你原代码保持一致即可）
    print("监控执行完毕，结果已更新。")

if __name__ == "__main__":
    run_monitor_task()
