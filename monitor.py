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
FUND_CONFIG = {
    "501225": {
        "name": "全球芯片LOF", 
        "us_ticker": "SOXX", "us_weight": 0.75,
        "cn_ticker": "sz159995", "cn_weight": 0.15, # 使用对应国内ETF或指数作为国内涨跌幅代理
        "usd_exposure": 0.75
    },
    "161128": {
        "name": "标普科技LOF", 
        "us_ticker": "XLK", "us_weight": 0.95,
        "cn_ticker": None, "cn_weight": 0.0,
        "usd_exposure": 0.95
    },
    "162411": {
        "name": "华宝油气LOF", 
        "us_ticker": "XOP", "us_weight": 0.95,
        "usd_exposure": 0.95
    },
    "161125": {
        "name": "标普500LOF", 
        "us_ticker": "ES=F", "us_weight": 0.95, # 使用期指捕捉盘中波动
        "usd_exposure": 0.95
    }
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
