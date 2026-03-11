import os
import requests
from datetime import datetime
import pytz
import time

# ==================== 监控配置中心 ====================
# 注意：base_nav 请务必保持为基金公司官方披露的最新净值 (T日净值通常T+1日晚更新)
FUND_CONFIG = {
    "162411": {"name": "华宝油气", "ticker": "XOP",  "base_nav": 0.5420},
    "160216": {"name": "原油LOF", "ticker": "USO",  "base_nav": 0.8950},
    "160416": {"name": "南方原油", "ticker": "USO",  "base_nav": 1.1230},
    "159509": {"name": "纳指科技", "ticker": "IXN",  "base_nav": 1.4520},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "base_nav": 2.1464},
    "161128": {"name": "标普科技", "ticker": "XLK",  "base_nav": 1.2340},
    "161129": {"name": "生物科技", "ticker": "XBI",  "base_nav": 1.1560},
    "164906": {"name": "中概互联", "ticker": "KWEB", "base_nav": 0.9850},
    "161125": {"name": "标普500",  "ticker": "IVV",  "base_nav": 2.2190},
    "513500": {"name": "标普500ETF", "ticker": "IVV", "base_nav": 2.2190},
    "161127": {"name": "纳指100",  "ticker": "QQQ",  "base_nav": 1.8540},
    "513100": {"name": "纳指ETF",  "ticker": "QQQ",  "base_nav": 1.8540},
}

# HTML 模板
HTML_TPL = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alpha 实时套利监控</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }}
        .container {{ max-width: 500px; margin: auto; background: white; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; }}
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
            <div style="font-size: 20px; font-weight: bold;">📊 Alpha 实时溢价监控</div>
            <div style="font-size: 12px; margin-top: 8px;">更新时间: {now_str}</div>
            <div style="font-size: 10px; margin-top: 4px; opacity: 0.8;">显示格式: 口径1(官方)~口径2(估算)</div>
        </div>
        {content_html}
    </div>
</body>
</html>"""

def get_us_change(ticker):
    """获取海外对标指数的涨跌幅"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        m = res.json()['chart']['result'][0]['meta']
        return (m.get('regularMarketPrice') / m.get('previousClose')) - 1
    except Exception as e:
        # print(f"获取{ticker}失败: {e}") # 调试用
        return 0.0

def get_cn_price(code):
    """获取国内LOF/ETF的实时二级市场价格"""
    prefix = "sh" if code.startswith(('5', '6')) else "sz"
    url = f"http://qt.gtimg.cn/q={prefix}{code}"
    try:
        res = requests.get(url, timeout=5)
        res.encoding = 'gbk' # 腾讯财经接口是GBK编码
        parts = res.text.split('~')
        return float(parts[3]) if len(parts) > 3 and parts[3] else None
    except Exception as e:
        # print(f"获取{code}失败: {e}") # 调试用
        return None

def format_premium(premium_value):
    """格式化溢价率显示，带正负号和颜色判断"""
    sign = "+" if premium_value > 0 else ""
    txt = f"{sign}{premium_value:.2%}"
    # 判断颜色类
    if premium_value > 0:
        color = "plus"
    elif premium_value < 0:
        color = "minus"
    else:
        color = "neutral"
    return txt, color

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now_str = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    rows = []

    for code, info in FUND_CONFIG.items():
        cn_p = get_cn_price(code)
        
        if cn_p:
            # --- 核心计算逻辑开始 ---
            
            # 1. 计算口径1：基于官方最新披露的净值 (base_nav)
            # 公式：(市价 - 官方净值) / 官方净值
            premium_1 = (cn_p - info['base_nav']) / info['base_nav']
            
            # 2. 计算口径2：基于海外指数估算的净值
            us_c = get_us_change(info['ticker'])
            est_nav = info['base_nav'] * (1 + us_c)
            # 公式：(市价 - 估算净值) / 估算净值
            premium_2 = (cn_p - est_nav) / est_nav
            
            # --- 核心计算逻辑结束 ---

            # 格式化两个数值
            p1_txt, _ = format_premium(premium_1)
            p2_txt, color = format_premium(premium_2) # 颜色主要随估算值(口径2)变动
            
            # 组合显示文本：X%~Y%
            display_txt = f"{p1_txt}~{p2_txt}"
            
            row = f'<div class="row"><div><div class="name">{info["name"]}</div><div class="code">代码: {code}</div></div><div class="premium {color}">{display_txt}</div></div>'
            rows.append(row)
        else:
            # 如果获取不到价格，显示停牌或等待
            row = f'<div class="row"><div><div class="name">{info["name"]}</div><div class="code">代码: {code}</div></div><div class="premium neutral">--</div></div>'
            rows.append(row)

    full_html = HTML_TPL.format(now_str=now_str, content_html="".join(rows))
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"监控页面已生成: {now_str}")

if __name__ == "__main__":
    run_task()
