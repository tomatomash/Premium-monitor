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
# 说明：当自动化抓取失效或官方公告有变时，在此手动强行覆盖。
# ==============================================================================
MANUAL_OVERRIDES = {
    # 示例: "161128": {"申购状态": "暂停申购", "日累计限定金额": 0},
}

# ==============================================================================
# ====== 3. 公用工具函数 (COMMON UTILS) ======
# ==============================================================================
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
CN_TZ = pytz.timezone("Asia/Shanghai")

def safe_get(url):
    """通用的安全请求函数"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200: return r.text
    except Exception as e:
        print(f"请求失败: {url}, 错误: {e}")
    return None

def should_run():
    """判断是否在 A 股交易时间段或附近执行"""
    now = datetime.now(CN_TZ)
    if now.weekday() >= 5: return True # 周末允许运行用于测试
    curr_time = now.time()
    # 9:00 - 15:30 视为有效监控时段
    return time(9,0) <= curr_time <= time(15,35)

def update_last_run():
    """记录最后一次运行成功的时间，防止 GitHub Actions 运行过于频繁"""
    with open("last_run.txt", "w") as f:
        f.write(datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"))

# ==============================================================================
# ====== 4. 限购信息模块 (PURCHASE LIMITS) ======
# 说明：基于 akshare 实时抓取东方财富网的限购数据。
# ==============================================================================
def get_fund_data():
    """抓取全量基金申购状态数据"""
    try:
        df = ak.fund_purchase_em()
        limit_col_map = ['日累计限定金额', '日累计限额', '日限额']
        for col in limit_col_map:
            if col in df.columns:
                df = df.rename(columns={col: '日累计限定金额'})
                break
        target_codes = list(FUND_CONFIG.keys())
        return df[df['基金代码'].isin(target_codes)].copy()
    except Exception as e:
        print(f"限购数据抓取失败: {e}")
        return pd.DataFrame()

def apply_manual_overrides(df):
    """应用手动修正逻辑"""
    for code, override in MANUAL_OVERRIDES.items():
        mask = df['基金代码'] == code
        if mask.any():
            idx = df[mask].index[0]
            if '申购状态' in override: df.at[idx, '申购状态'] = override['申购状态']
            if '日累计限定金额' in override: df.at[idx, '日累计限定金额'] = override['日累计限定金额']
    return df

def get_purchase_limits_dict():
    """将 DataFrame 转换为易于查询的代码-信息字典"""
    df = get_fund_data()
    if df.empty: return {}
    df = apply_manual_overrides(df)
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
# ====== 5. 交易方式判断模块 (TRADE TYPE JUDGE) ======
# ==============================================================================
def fund_type_judge(code):
    """根据代码开头初步判断交易属性"""
    if code.startswith("50"): return "场内_身份证限购"
    elif code.startswith("16"): return "场内_账户限购(可拖拉机)"
    else: return "场内交易"

def enhance_judge(code, base_result):
    """预留：针对特定基金做更细致的交易策略修正"""
    return base_result

# ==============================================================================
# ====== 6. 溢价率计算核心模块 (PREMIUM CALCULATION) ======
# ==============================================================================
def get_market_change(ticker):
    """从 Yahoo Finance 获取实时资产涨跌幅"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev_close = meta["previousClose"]
        change = (price / prev_close) - 1
        return max(min(change, 0.15), -0.15)
    except: return 0.0

def get_fx():
    """获取离岸人民币 (CNH) 实时汇率波动"""
    return get_market_change("CNH=F")

def get_fund_estimate(code):
    """从天天基金获取昨日净值(dwjz)和实时估算值(gsz)"""
    txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt: return None, None
    try:
        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        return float(data["dwjz"]), float(data["gsz"])
    except: return None, None

def get_em_nav(code):
    """备选：从东方财富基金列表抓取净值（当 fundgz 接口失效时）"""
    url = f"http://fund.eastmoney.com/{code}.html"
    txt = safe_get(url)
    if not txt: return None
    try:
        soup = BeautifulSoup(txt, 'html.parser')
        nav_text = soup.find('dl', class_='dataItem02').find('dd', class_='dataNums').find('span').text
        return float(nav_text)
    except: return None

def get_price(code):
    """获取场内实时成交价（腾讯接口）"""
    prefix = "sh" if code.startswith("5") else "sz"
    txt = safe_get(f"http://qt.gtimg.cn/q={prefix}{code}")
    if not txt: return None
    try:
        data = txt.split("~")
        p = float(data[3])
        return p if p != 0 else None
    except: return None

# ==============================================================================
# ====== 8. HTML 报告生成 (HTML GENERATOR) ======
# ==============================================================================
def generate_html(results, audit_data, report_time):
    # 分离出关注和无机会
    hot_items = [r for r in results if r['premium'] >= 0.03]
    normal_items = [r for r in results if r['premium'] < 0.03]

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

    # 构建审计表格行
    audit_rows = ""
    for d in audit_data:
        audit_rows += f"""
        <tr>
            <td>{d['name']}<br><small>{d['code']}</small></td>
            <td>{d['price']:.3f}</td>
            <td>{d['dwjz']:.4f}</td>
            <td>{d['gsz'] if d['gsz'] else '-'}</td>
            <td>{d['ticker_change']:.2%}</td>
            <td>{d['p1']:.2%}</td>
            <td>{d['p2']:.2%}</td>
            <td style="font-size:10px; color:#666;">{d['formula']}</td>
            <td style="font-weight:bold;">{d['final_p']:.2%}</td>
        </tr>"""

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
            .section-title {{ font-size: 17px; font-weight: 600; padding: 16px 16px 8px; color: var(--text); }}
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
            details summary {{ cursor: pointer; outline: none; list-style: none; }}
            details summary::-webkit-details-marker {{ display: none; }}
            .dimmed {{ filter: grayscale(1); opacity: 0.6; }}
            
            /* 新增审计表格样式，完全独立 */
            .audit-section {{ margin-top: 40px; padding-bottom: 50px; }}
            .audit-summary {{ padding: 14px; background: #e5e5ea; border-radius: 12px; font-weight: 600; display: flex; justify-content: space-between; align-items: center; font-size: 14px; color: #3a3a3c; }}
            .audit-table-container {{ overflow-x: auto; margin-top: 10px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 11px; background: white; border-radius: 8px; }}
            th, td {{ padding: 8px 4px; border: 0.5px solid #eee; text-align: center; }}
            th {{ background: #f8f9fa; color: #8e8e93; font-weight: 500; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>折溢价监控</h1>
                <div class="time">最后更新: {report_time} (北京时间)</div>
            </div>
            
            <div class="card">
                <div class="section-title">今日关注 🔥</div>
                {build_rows(hot_items) if hot_items else '<div style="padding:20px; color:#8e8e93; text-align:center; font-size:14px;">暂无高溢价标的</div>'}
            </div>

            <details>
                <summary>
                    <div class="card dimmed" style="margin-bottom: 10px;">
                        <div class="section-title" style="display: flex; justify-content: space-between;">
                            <span>暂无机会 (折价/平价)</span>
                            <span style="font-size: 12px; font-weight: 400;">点击展开查看 ▼</span>
                        </div>
                    </div>
                </summary>
                <div class="card dimmed">
                    {build_rows(normal_items)}
                </div>
            </details>

            <details class="audit-section">
                <summary class="audit-summary">
                    <span>📊 标的数据 (实时计算审计)</span>
                    <span style="font-size:12px; font-weight:normal;">点击展开核对过程 ▼</span>
                </summary>
                <div class="audit-table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>标的</th><th>价格</th><th>昨净</th><th>估值</th><th>Ticker</th><th>P1</th><th>P2</th><th>公式</th><th>最终</th>
                            </tr>
                        </thead>
                        <tbody>
                            {audit_rows}
                        </tbody>
                    </table>
                </div>
            </details>
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

# ==============================================================================
# ====== 9. 主程序入口 (MAIN RUNNER) ======
# ==============================================================================
def run():
    now_str = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"任务启动: {now_str}")
    
    # 1. 抓取全局公共数据
    limits = get_purchase_limits_dict()
    fx_change = get_fx()
    
    results = []
    audit_data = [] # 记录审计数据
    
    # 2. 遍历配置进行计算
    for code, info in FUND_CONFIG.items():
        try:
            # 基础数据抓取
            price = get_price(code)
            if not price: continue
            
            dwjz, gsz = get_fund_estimate(code)
            if not dwjz: dwjz = get_em_nav(code)
            if not dwjz: continue
            
            ticker = info["ticker"]
            asset_change = 0
            
            # --- 核心逻辑分支 (完全保留 monitor (1222).py 逻辑) ---
            if ticker:
                asset_change = get_market_change(ticker)
                fx = (1 + fx_change) if ticker != "GC=F" else 1
                est_nav = dwjz * (1 + asset_change * info["w"]) * fx
                
                # 计算审计中间变量
                p1 = (price - dwjz) / dwjz  # 静态
                p2 = (price - est_nav) / est_nav # 实时
                premium = (p1 + p2) / 2 # 平衡算法
                formula = "(P1+P2)/2 [平衡]"
            else:
                realtime_val = gsz if gsz else dwjz
                premium = (price - realtime_val) / realtime_val
                p1 = (price - dwjz) / dwjz
                p2 = premium
                formula = "Price/GSZ [同步]"

            # --- 信号判定 ---
            if premium >= 0.05: signal, color = "🔴 尝试", "strong_arbitrage"
            elif premium >= 0.03: signal, color = "🟡 关注", "watch"
            elif premium >= 0: signal, color = "⚪ 正常", "normal"
            else: signal, color = "⚫ 折价", "discount"
            
            # 封装结果
            res_obj = {
                "code": code, "name": info["name"], "premium": premium,
                "signal": signal, "color": color, 
                "limit": limits.get(code, "未知状态, -"),
                "trade_type": enhance_judge(code, fund_type_judge(code))
            }
            results.append(res_obj)

            # 记录审计信息
            audit_data.append({
                "code": code, "name": info["name"], "price": price, "dwjz": dwjz, "gsz": gsz,
                "ticker_change": asset_change, "p1": p1, "p2": p2, "formula": formula, "final_p": premium
            })
            
        except Exception as e:
            print(f"处理基金 {code} 时出错: {e}")
            continue

    # 3. 排序并生成报告
    results.sort(key=lambda x: x["premium"], reverse=True)
    generate_html(results, audit_data, now_str)
    
    print(f"报告生成成功，总计处理 {len(results)} 个标的。")

if __name__ == "__main__":
    run()
