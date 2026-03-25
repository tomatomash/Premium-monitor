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
import yfinance as yf  # 新增：用于获取稳定的历史复权收盘价

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
#        - 0.85~0.90: 主动管理/混合型。如 501225 全球芯片 (0.88)。
#    - 自动化说明: 代码会自动抓取 CNH=F 汇率，除黄金(GC=F)外均自动叠加汇率波动。
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
    # 新增基金
    "161130": {"name": "纳指100", "ticker": "QQQ", "w": 0.95},
    "162411": {"name": "华宝油油气", "ticker": "XOP", "w": 0.90},
    "163208": {"name": "全球油气", "ticker": "XOP", "w": 0.90},
# ------ 补全截图缺失标的 (Missing from Screenshots) ------
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
MANUAL_OVERRIDES = {
    # 示例："501225": {"申购状态": "暂停申购", "日累计限定金额": 0},
}

# ==============================================================================
# ====== 3. 公用工具函数 ======
# ==============================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
CN_TZ = pytz.timezone("Asia/Shanghai")
PING_CACHE = {}

def safe_get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

# ==============================================================================
# ====== 4. 限购信息模块 ======
# ==============================================================================
def get_fund_data():
    print("--- 正在连接 akshare 获取基础数据 ---")
    try:
        df = ak.fund_purchase_em()
        limit_col_map = ['日累计限定金额', '日累计限额', '日限额']
        for col in limit_col_map:
            if col in df.columns:
                df = df.rename(columns={col: '日累计限定金额'})
                break
        target_codes = list(FUND_CONFIG.keys())
        df = df[df['基金代码'].isin(target_codes)].copy()
        return df
    except Exception as e:
        print(f"错误: 抓取失败: {e}")
        return pd.DataFrame()

def apply_manual_overrides(df):
    if df.empty: return df
    for code, override in MANUAL_OVERRIDES.items():
        mask = df['基金代码'] == code
        if mask.any():
            idx = df[mask].index[0]
            if '申购状态' in override:
                df.at[idx, '申购状态'] = override['申购状态']
            if '日累计限定金额' in override:
                df.at[idx, '日累计限定金额'] = override['日累计限定金额']
    return df

def format_display_logic(row):
    status = row['申购状态']
    amount = row['日累计限定金额']
    if status == "暂停申购":
        return "暂停申购", "-"
    if pd.isna(amount) or amount is None or amount >= 1e10:
        return "开放申购", "不限额"
    amount_str = f"{int(amount):,}" if isinstance(amount, (int, float)) and amount % 1 == 0 else str(amount)
    return "限额申购", amount_str

def get_purchase_limits_dict():
    df = get_fund_data()
    if df.empty: return {}
    df = apply_manual_overrides(df)
    limit_dict = {}
    for _, row in df.iterrows():
        code = row['基金代码']
        status, amount_str = format_display_logic(row)
        limit_dict[code] = f"{status}, {amount_str}"
    return limit_dict

# ==============================================================================
# ====== 5. 交易方式判断模块 ======
# ==============================================================================
def fund_type_judge(code):
    if code.startswith("50"): return "场内_身份证限购"
    elif code.startswith("16"): return "场内_账户限购(可拖拉机)"
    elif code.startswith("15"): return "场内交易"
    elif code.startswith(("51", "58")): return "场内交易"
    else: return "场外申购"

def fetch_notice_text(code):
    try:
        url = f"https://fundf10.eastmoney.com/jjgg_{code}.html"
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200: return r.text[:2000]
    except: pass
    return ""

def enhance_judge(code, base_result):
    text = fetch_notice_text(code)
    if not text: return base_result
    id_keywords = ["单个投资者", "单个账户", "单一投资者", "单一账户", "单个基金账户", "每个基金账户", "单日单个基金账户"]
    if any(kw in text for kw in id_keywords): return "场内_身份证限购（公告识别）"
    if "暂停申购" in text: return "暂停申购"
    return base_result

# ==============================================================================
# ====== 6. 溢价率计算核心模块 (增强稳定性) ======
# ==============================================================================
def get_ping_data(code):
    if code in PING_CACHE: return PING_CACHE[code]
    txt = safe_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")
    if not txt: return None
    PING_CACHE[code] = txt
    return txt

def get_market_change(ticker):
    """
    使用 yfinance 获取最近5个交易日的调整后收盘价（Adj Close），
    自动处理除权、除息，并返回最新两个交易日的涨跌幅。
    同时对异常波动进行限幅（±15%），防止期货换月等数据错误。
    """
    try:
        # 获取5个交易日数据，使用调整后收盘价
        hist = yf.download(ticker, period="5d", progress=False)
        if len(hist) >= 2:
            # 使用 Adj Close 避免除权影响
            close_prev = hist['Adj Close'].iloc[-2]
            close_last = hist['Adj Close'].iloc[-1]
            change = (close_last / close_prev) - 1
            # 限制单日极端值（防止合约换月、数据跳空）
            return max(min(change, 0.15), -0.15)
    except Exception:
        pass
    return 0.0

def get_fx():
    return get_market_change("CNH=F")

def get_fund_estimate(code):
    txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt: return None, None
    try:
        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        return float(data["dwjz"]), float(data["gsz"])
    except: return None, None

def get_em_nav(code):
    txt = get_ping_data(code)
    if not txt: return None
    try:
        match = re.search(r"Data_netWorthTrend = (.*?);", txt)
        return float(json.loads(match.group(1))[-1]["y"])
    except: return None

def get_price(code):
    prefix = "sh" if code.startswith("5") else "sz"
    txt = safe_get(f"http://qt.gtimg.cn/q={prefix}{code}")
    if not txt: return None
    try:
        price = float(txt.split("~")[3])
        return price if price != 0 else None
    except: return None

# ==============================================================================
# ====== 7. 运行频率控制 ======
# ==============================================================================
def should_run():
    now = datetime.now(CN_TZ)
    weekday = now.weekday()
    hour, minute = now.hour, now.minute
    in_trading_session = False
    if 0 <= weekday <= 4:
        if (hour == 9 and minute >= 30) or (10 <= hour <= 10) or (hour == 11 and minute <= 30):
            in_trading_session = True
        elif (13 <= hour <= 14) or (hour == 15 and minute == 0):
            in_trading_session = True
    if in_trading_session: return True
    last_run_file = "last_run.txt"
    if os.path.exists(last_run_file):
        try:
            with open(last_run_file, "r") as f:
                last_run = CN_TZ.localize(datetime.strptime(f.read().strip(), "%Y-%m-%d %H:%M:%S"))
        except: last_run = None
    else: last_run = None
    if last_run is None: return True
    return (now - last_run).total_seconds() >= 3 * 3600

def update_last_run():
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with open("last_run.txt", "w") as f: f.write(now)

# ==============================================================================
# ====== 8. HTML 报告生成 (优化版：折叠与置灰) ======
# ==============================================================================
def parse_limit_info(limit_str):
    if ', ' in limit_str:
        status_part, amount_desc = limit_str.split(', ', 1)
    else:
        status_part, amount_desc = limit_str, ""
    digits = re.findall(r'\d+', amount_desc.replace(',', ''))
    limit_value = int(''.join(digits)) if digits else None
    return status_part, amount_desc, limit_value

def generate_html(results, report_time):
    focus_list = []
    other_list = []
    for item in results:
        premium = item['premium']
        limit_str = item['limit']
        status_part, amount_desc, limit_value = parse_limit_info(limit_str)
        if premium > 0.03 and status_part != "暂停申购" and amount_desc != "不限额":
            if limit_value is not None and limit_value > 10000:
                other_list.append(item)
            else:
                focus_list.append(item)
        else:
            other_list.append(item)

    def build_rows(items):
        rows = ""
        for item in items:
            rows += f'''
<div class="row">
    <div>
        <b style="font-size:15px; color:#333;">{item['name']}</b><br>
        <span style="color:#999; font-size:12px;">{item['code']}</span>
    </div>
    <div class="right">
        <div class="premium_line">
            <span class="premium {item['color']}">{item['premium']:.2%}</span>
            <span class="signal-tag">{item['signal']}</span>
        </div>
        <div class="limit_info">{item['limit']}</div>
        <div class="trade_type">{item['trade_type']}</div>
    </div>
</div>'''
        return rows

    focus_rows = build_rows(focus_list)
    other_rows = build_rows(other_list)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    body {{ font-family: -apple-system, sans-serif; background: #f4f4f7; margin: 0; padding: 15px; }}
    .container {{ max-width: 500px; margin: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
    .header {{ padding: 15px; border-bottom: 1px solid #eee; background: #fff; }}
    .section-title {{ padding: 12px 15px; background: #f9f9fc; border-bottom: 1px solid #e0e0e0; font-weight: 600; color: #555; display: flex; align-items: center; }}
    
    /* 暂无机会板块样式：通过 filter 实现全局变灰调低对比度 */
    .muted-section {{ 
        margin-top: 30px; 
        border-top: 1px solid #eee;
        /* --- 调色说明：修改下面的 grayscale(60%) 为 0% 即可恢复原色 --- */
        filter: grayscale(60%) opacity(0.7); 
        background: #fafafa;
    }}
    
    /* 折叠栏样式 */
    details summary {{ cursor: pointer; outline: none; list-style: none; }}
    details summary::-webkit-details-marker {{ display: none; }}
    .summary-box {{ display: flex; justify-content: space-between; width: 100%; align-items: center; }}
    .arrow {{ border: solid #999; border-width: 0 2px 2px 0; display: inline-block; padding: 3px; transform: rotate(45deg); transition: transform 0.2s; }}
    details[open] .arrow {{ transform: rotate(-135deg); }}

    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #f0f0f0; }}
    .right {{ text-align: right; }}
    .premium_line {{ display: flex; align-items: baseline; justify-content: flex-end; margin-bottom: 4px; }}
    .premium {{ font-weight: 900; font-size: 20px; }}
    .signal-tag {{ font-size: 13px; margin-left: 6px; color: #666; }}
    .limit_info {{ font-size: 12px; color: #888; margin-top: 2px; }}
    .trade_type {{ font-size: 11px; color: #aaa; margin-top: 2px; }}
    .strong_arbitrage {{ color: #e63946; }}
    .watch {{ color: #f4a261; }}
    .normal {{ color: #2a9d8f; }}
    .discount {{ color: #6d6d6d; }}
    .empty {{ padding: 20px; text-align: center; color: #aaa; }}
</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h3 style="margin:0; font-size:18px;">Premium Monitor</h3>
            <p style="margin:5px 0 0; font-size:12px; color:#999;">更新: {report_time}</p>
        </div>

        <div class="section-title">今日关注</div>
        {focus_rows if focus_rows else '<div class="empty">暂无满足条件的基金</div>'}

        <details class="muted-section">
            <summary class="section-title">
                <div class="summary-box">
                    <span>暂无机会</span>
                    <i class="arrow"></i>
                </div>
            </summary>
            {other_rows if other_rows else '<div class="empty">暂无其他基金</div>'}
        </details>
    </div>
</body>
</html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("--- 报告生成成功: index.html (优化折叠与置灰) ---")

# ==============================================================================
# ====== 9. 主程序入口 (动态平衡算法) ======
# ==============================================================================
def run():
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"基金监控系统 v4.1 启动... {now}")
    if not should_run(): return
    limits = get_purchase_limits_dict()
    fx_change = get_fx()
    results = []
    
    for code, info in FUND_CONFIG.items():
        try:
            price = get_price(code)
            if not price: continue
            
            dwjz, gsz = get_fund_estimate(code)
            if not dwjz: dwjz = get_em_nav(code)
            if not dwjz: continue
            
            ticker = info["ticker"]
            
            # --- 核心平衡逻辑 ---
            if ticker:
                asset_change = get_market_change(ticker)
                # 统一使用汇率修正（所有海外资产都受汇率影响）
                fx = (1 + fx_change)
                
                # 预估净值模型（实时估值）
                est_nav = dwjz * (1 + asset_change * info["w"]) * fx
                
                # 静态溢价（相对于官方已公布净值）
                p_static = (price - dwjz) / dwjz
                # 实时溢价（相对于模型预估净值）
                p_real = (price - est_nav) / est_nav
                
                # 动态权重：根据 asset_change 的合理性调整
                # 若涨跌幅绝对值超过 5%（例如期货换月、除权导致的异常），则提高静态权重
                if abs(asset_change) > 0.05:
                    static_weight = 0.8
                    real_weight = 0.2
                else:
                    static_weight = 0.5
                    real_weight = 0.5
                
                premium = p_static * static_weight + p_real * real_weight
                
            else:
                # 国内基金：优先使用天天基金的实时估算值 gsz
                realtime_val = gsz if gsz else dwjz
                premium = (price - realtime_val) / realtime_val

            # --- 信号判定 ---
            if premium >= 0.05: signal, color = "🔴 尝试", "strong_arbitrage"
            elif premium >= 0.03: signal, color = "🟡 关注", "watch"
            elif premium >= 0: signal, color = "⚪ 正常", "normal"
            else: signal, color = "⚫ 折价", "discount"
            
            results.append({
                "code": code, "name": info["name"], "premium": premium,
                "signal": signal, "color": color, 
                "limit": limits.get(code, "未知状态, -"),
                "trade_type": enhance_judge(code, fund_type_judge(code))
            })
        except Exception as e:
            # 保持原有异常处理，仅跳过出错基金
            continue

    results.sort(key=lambda x: x["premium"], reverse=True)
    generate_html(results, now)
    update_last_run()
    print("任务执行完毕。")

if __name__ == "__main__":
    run()
