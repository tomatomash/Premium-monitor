import re
import json
import requests
import pytz
import pandas as pd
import akshare as ak
import os
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ==============================================================================
# ====== 1. 基金配置区间 (FUND CONFIGURATION) ======
# 说明：此区间定义监控的基金列表，包含代码、名称、对标 ticker 及权重 w。
#       该配置是主骨架的核心数据源，其他模块（限购、交易方式）均基于此。
# ==============================================================================
FUND_CONFIG = {
# ==================================================================================
# 💡 核心配置参数说明 (Core Parameter Guide):
# 
# 1. ticker (实时对标代码): 
#    - 数据源: Yahoo Finance (由 get_market_change 函数调用)。
#    - 逻辑: 海外QDII对标美股ETF(如SPY)或期货(如CL=F)；国内LOF若为空("")则跳过对标。
#
# 2. w (权重/仓位系数 - Weights): 
#    - 含义: 基金对标资产的【拟合优度】或【实时仓位】。
#    - 计算公式: 预估净值 = 昨收净值 × (1 + Ticker涨跌 × w) × 汇率系数(fx)
#    - 取值参考: 
#        - 0.95~0.99: 纯指数/满仓型。如 161116 黄金主题 (0.99)。
#        - 0.85~0.90: 主动管理/混合型。如 162411 华宝油气 (0.90)。
# ==================================================================================
    # ------ 海外与商品 (精准对标) ------
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
    "160416": {"name": "石油基金", "ticker": "IXC", "w": 0.82},
    "161129": {"name": "原油基金", "ticker": "CL=F", "w": 0.95},
    "501018": {"name": "南方原油", "ticker": "CL=F", "w": 0.95},
    "160723": {"name": "嘉实原油", "ticker": "CL=F", "w": 0.90},
    "160644": {"name": "港美互联", "ticker": "KWEB", "w": 0.95},
    "161125": {"name": "标普500", "ticker": "SPY", "w": 0.98},
    "161128": {"name": "标普科技", "ticker": "XLK", "w": 0.98},
    "161116": {"name": "黄金主题", "ticker": "GC=F", "w": 0.99},
    "161126": {"name": "标普医疗", "ticker": "XLV", "w": 0.98},
    "161226": {"name": "白银基金", "ticker": "SLV", "w": 0.95},
    "161130": {"name": "纳指100", "ticker": "QQQ", "w": 0.95},
    "162411": {"name": "华宝油油气", "ticker": "XOP", "w": 0.90},
    "163208": {"name": "全球油气", "ticker": "XOP", "w": 0.90},
    "162719": {"name": "石油LOF", "ticker": "IXC", "w": 0.85},
    "161127": {"name": "标普生物", "ticker": "XBI", "w": 0.95},
    "164701": {"name": "黄金LOF", "ticker": "GC=F", "w": 0.99},
    "161815": {"name": "抗通胀", "ticker": "DBC", "w": 0.90},
    "164824": {"name": "印度基金", "ticker": "EPI", "w": 0.90},
    "160216": {"name": "国泰商品", "ticker": "GSG", "w": 0.90},
    # ------ 国内 A 股基金 ------
    "501227": {"name": "弘德红利", "ticker": "", "w": 0.90},
    "501099": {"name": "平安新兴", "ticker": "", "w": 0.90},
    "501082": {"name": "科创投资", "ticker": "", "w": 0.85},
    "501188": {"name": "添富核心", "ticker": "", "w": 0.85},
    "501076": {"name": "创新动力", "ticker": "", "w": 0.85},
    "501096": {"name": "国联安科", "ticker": "", "w": 0.85},
    "501015": {"name": "财通升级", "ticker": "", "w": 0.85},
    "501022": {"name": "银华鑫盛", "ticker": "", "w": 0.85},
    "501001": {"name": "财通精选", "ticker": "", "w": 0.85},
}

# ==============================================================================
# ====== 2. 手动修正区间 (MANUAL OVERRIDES) ======
# ==============================================================================
MANUAL_OVERRIDES = {}

# ==============================================================================
# ====== 3. 公用工具函数 (COMMON UTILS) ======
# ==============================================================================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
CN_TZ = pytz.timezone("Asia/Shanghai")

def safe_get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200: return r.text
    except: pass
    return None

# ==============================================================================
# ====== 4. 限购信息模块 (PURCHASE LIMITS) ======
# ==============================================================================
def get_fund_data():
    try:
        df = ak.fund_purchase_em()
        limit_col_map = ['日累计限定金额', '日累计限额', '日限额']
        for col in limit_col_map:
            if col in df.columns:
                df = df.rename(columns={col: '日累计限定金额'})
                break
        target_codes = list(FUND_CONFIG.keys())
        return df[df['基金代码'].isin(target_codes)].copy()
    except: return pd.DataFrame()

def get_purchase_limits_dict():
    df = get_fund_data()
    if df.empty: return {}
    limit_dict = {}
    for _, row in df.iterrows():
        status = row['申购状态']
        amount = row['日累计限定金额']
        if status == "暂停申购": display = "暂停申购, -"
        elif pd.isna(amount) or amount >= 1e10: display = "开放申购, 不限额"
        else: display = f"限额申购, {int(amount):,}"
        limit_dict[row['基金代码']] = display
    return limit_dict

# ==============================================================================
# ====== 5. 交易方式判断模块 ======
# ==============================================================================
def fund_type_judge(code):
    if code.startswith("50"): return "场内_身份证限购"
    elif code.startswith("16"): return "场内_账户限购(可拖拉机)"
    else: return "场内交易"

# ==============================================================================
# ====== 6. 溢价率计算核心模块 ======
# ==============================================================================
def get_market_change(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()["chart"]["result"][0]["meta"]
        change = (data["regularMarketPrice"] / data["previousClose"]) - 1
        return max(min(change, 0.15), -0.15)
    except: return 0.0

def get_fund_estimate(code):
    txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt: return None, None
    try:
        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        return float(data["dwjz"]), float(data["gsz"])
    except: return None, None

def get_em_nav(code):
    url = f"http://fund.eastmoney.com/{code}.html"
    txt = safe_get(url)
    if not txt: return None
    try:
        soup = BeautifulSoup(txt, 'html.parser')
        nav_text = soup.find('dl', class_='dataItem02').find('dd', class_='dataNums').find('span').text
        return float(nav_text)
    except: return None

def get_price(code):
    prefix = "sh" if code.startswith("5") else "sz"
    txt = safe_get(f"http://qt.gtimg.cn/q={prefix}{code}")
    if not txt: return None
    try:
        p = float(txt.split("~")[3])
        return p if p != 0 else None
    except: return None

# ==============================================================================
# ====== 8. HTML 报告生成 (HTML GENERATOR) ======
# ==============================================================================
def generate_html(results, audit_data, report_time):
    # 保持你原来的 build_rows 封装
    def build_rows(items):
        html = ""
        for r in items:
            html += f"""
            <div class="row">
                <div class="info">
                    <div class="name-box">
                        <span class="name">{r['name']}</span>
                        <span class="code">{r['code']}</span>
                    </div>
                    <div class="trade-tag">{r['trade_type']}</div>
                </div>
                <div class="data-group">
                    <div class="premium {r['color']}">{r['premium']:.2%}</div>
                    <div class="signal-badge">{r['signal']}</div>
                    <div class="limit-info">{r['limit']}</div>
                </div>
            </div>
            """
        return html

    # 新增审计表格行（这是唯一的新增 HTML 片段）
    audit_rows = ""
    for d in audit_data:
        audit_rows += f"<tr><td>{d['name']}<br><small>{d['code']}</small></td><td>{d['price']:.3f}</td><td>{d['dwjz']:.4f}</td><td>{d['gsz'] if d['gsz'] else '-'}</td><td>{d['ticker_change']:.2%}</td><td>{d['p1']:.2%}</td><td>{d['p2']:.2%}</td><td style='font-size:9px;color:#888'>{d['formula']}</td><td style='font-weight:bold'>{d['final_p']:.2%}</td></tr>"

    # HTML 模版：严格保留你原来的 CSS 和 结构
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Premium Arbitrage Monitor</title>
        <style>
            :root {{ --bg: #f4f4f7; --card: #ffffff; --text: #1d1d1f; --sub: #86868b; --red: #ff3b30; --orange: #ff9500; --green: #34c759; --gray: #8e8e93; }}
            body {{ background-color: var(--bg); color: var(--text); font-family: -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif; margin: 0; padding: 20px 12px; -webkit-font-smoothing: antialiased; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ margin-bottom: 24px; padding: 0 4px; }}
            .header h1 {{ font-size: 28px; font-weight: 700; margin: 0 0 4px 0; letter-spacing: -0.5px; }}
            .header .time {{ color: var(--sub); font-size: 13px; font-weight: 400; }}
            .card {{ background: var(--card); border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.04); overflow: hidden; margin-bottom: 20px; }}
            .row {{ display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 0.5px solid #f2f2f7; }}
            .row:last-child {{ border-bottom: none; }}
            .info .name {{ display: block; font-size: 16px; font-weight: 600; margin-bottom: 2px; }}
            .info .code {{ color: var(--sub); font-size: 12px; font-family: "SF Mono", monospace; }}
            .trade-tag {{ display: inline-block; margin-top: 6px; padding: 2px 6px; background: #f2f2f7; color: #636366; font-size: 10px; font-weight: 500; border-radius: 4px; }}
            .data-group {{ text-align: right; }}
            .premium {{ font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.1; }}
            .signal-badge {{ font-size: 11px; font-weight: 600; margin: 4px 0; }}
            .limit-info {{ font-size: 10px; color: var(--sub); white-space: nowrap; }}
            .strong_arbitrage {{ color: var(--red); }} .watch {{ color: var(--orange); }} .normal {{ color: var(--green); }} .discount {{ color: var(--gray); }}
            
            /* 仅为新增模块增加的样式，不影响上方 */
            .audit-box {{ margin-top: 30px; border-top: 1px solid #ddd; padding-top: 20px; }}
            .audit-btn {{ background: #e5e5ea; padding: 12px; border-radius: 10px; font-weight: 600; font-size: 14px; cursor: pointer; display: block; text-align: center; color: #333; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 10px; background: #fff; }}
            th, td {{ padding: 6px 2px; border: 1px solid #eee; text-align: center; }}
            th {{ background: #f9f9fb; color: #888; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>折溢价监控</h1>
                <div class="time">最后更新: {report_time} (北京时间)</div>
            </div>
            
            <div class="card">
                {build_rows(results)}
            </div>

            <div class="audit-box">
                <details>
                    <summary class="audit-btn">📊 查看标的数据 (计算审计)</summary>
                    <div style="overflow-x: auto;">
                        <table>
                            <thead>
                                <tr><th>标的</th><th>价</th><th>昨净</th><th>估值</th><th>Ticker</th><th>P1</th><th>P2</th><th>公式</th><th>最终</th></tr>
                            </thead>
                            <tbody>
                                {audit_rows}
                            </tbody>
                        </table>
                    </div>
                </details>
            </div>
        </div> </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f: f.write(html_content)

# ==============================================================================
# ====== 9. 主程序入口 (MAIN RUNNER) ======
# ==============================================================================
def run():
    now_str = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    limits = get_purchase_limits_dict()
    fx_change = get_market_change("CNH=F")
    
    results, audit_data = [], []
    
    for code, info in FUND_CONFIG.items():
        try:
            price = get_price(code)
            if not price: continue
            dwjz, gsz = get_fund_estimate(code)
            if not dwjz: dwjz = get_em_nav(code)
            if not dwjz: continue
            
            ticker = info["ticker"]
            t_change = 0
            
            # --- 保持你原来的逻辑分支 ---
            if ticker:
                t_change = get_market_change(ticker)
                fx = (1 + fx_change) if ticker != "GC=F" else 1
                est_nav = dwjz * (1 + t_change * info["w"]) * fx
                # 分别计算两个维度的溢价用于核对
                p1 = (price - dwjz) / dwjz
                p2 = (price - est_nav) / est_nav
                premium = (p1 + p2) / 2
                formula = "(P1+P2)/2 [平衡]"
            else:
                real_val = gsz if gsz else dwjz
                premium = (price - real_val) / real_val
                p1 = (price - dwjz) / dwjz
                p2 = premium
                formula = "Price/GSZ [同步]"

            # 信号判定
            if premium >= 0.05: signal, color = "🔴 尝试", "strong_arbitrage"
            elif premium >= 0.03: signal, color = "🟡 关注", "watch"
            elif premium >= 0: signal, color = "⚪ 正常", "normal"
            else: signal, color = "⚫ 折价", "discount"
            
            # 基础展示数据
            results.append({
                "code": code, "name": info["name"], "premium": premium,
                "signal": signal, "color": color, "limit": limits.get(code, "-"),
                "trade_type": fund_type_judge(code)
            })
            # 审计用数据（新增）
            audit_data.append({
                "code": code, "name": info["name"], "price": price, "dwjz": dwjz, "gsz": gsz,
                "ticker_change": t_change, "p1": p1, "p2": p2, "formula": formula, "final_p": premium
            })
        except: continue

    results.sort(key=lambda x: x["premium"], reverse=True)
    generate_html(results, audit_data, now_str)

if __name__ == "__main__":
    run()
