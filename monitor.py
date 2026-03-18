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
    "162411": {"name": "华宝油气", "ticker": "XOP", "w": 0.90},
    "163208": {"name": "全球油气", "ticker": "XOP", "w": 0.90},

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
# 说明：当 akShare 返回数据滞后时，在此强制覆盖申购状态或金额。
#       格式：{"基金代码": {"申购状态": "xxx", "日累计限定金额": 数值或字符串}}
# ==============================================================================
MANUAL_OVERRIDES = {
    # 示例（需根据实际情况填写）：
    # "501225": {"申购状态": "暂停申购", "日累计限定金额": 0},
}

# ==============================================================================
# ====== 3. 公用工具函数 ======
# ==============================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
CN_TZ = pytz.timezone("Asia/Shanghai")
PING_CACHE = {}  # 用于缓存 pingzhongdata.js 的内容

def safe_get(url):
    """安全发起 GET 请求，返回文本或 None"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

# ==============================================================================
# ====== 4. 限购信息模块 (原 fund_monitor_custom限购监控报告.py) ======
# ==============================================================================
def get_fund_data():
    """获取基金申购状态原始数据（akshare）并初步清洗"""
    print("--- 正在连接 akshare 获取基础数据 ---")
    try:
        df = ak.fund_purchase_em()
        
        # 兼容处理列名（防止接口变动导致找不到限额列）
        limit_col_map = ['日累计限定金额', '日累计限额', '日限额']
        for col in limit_col_map:
            if col in df.columns:
                df = df.rename(columns={col: '日累计限定金额'})
                break
        
        target_codes = list(FUND_CONFIG.keys())  # 使用主配置的所有基金代码
        df = df[df['基金代码'].isin(target_codes)].copy()
        
        print(f"数据获取成功: 匹配到 {len(df)} 支基金")
        return df
    except Exception as e:
        print(f"错误: 抓取失败: {e}")
        return pd.DataFrame()

def apply_manual_overrides(df):
    """应用手动修正逻辑"""
    if df.empty:
        return df
    
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
    """根据业务逻辑格式化显示状态和金额"""
    status = row['申购状态']
    amount = row['日累计限定金额']
    
    if status == "暂停申购":
        return "暂停申购", "-"
    
    # 阈值判断：极大数据或空值视为不限额
    if pd.isna(amount) or amount is None or amount >= 1e10:
        return "开放申购", "不限额"
    
    # 金额格式化（去除.0）
    amount_str = f"{int(amount):,}" if isinstance(amount, (int, float)) and amount % 1 == 0 else str(amount)
    return "限额申购", amount_str

def get_purchase_limits_dict():
    """
    获取限购信息字典，供主程序调用。
    返回格式：{code: "申购状态, 限额字符串"}，例如 "开放申购, 不限额" 或 "限额申购, 1,000" 或 "暂停申购, -"
    """
    df = get_fund_data()
    if df.empty:
        return {}
    
    df = apply_manual_overrides(df)
    # 添加基金名称列（便于调试，但不用于输出）
    df['基金名称'] = df['基金代码'].map(lambda c: FUND_CONFIG.get(c, {}).get('name', ''))
    
    limit_dict = {}
    for _, row in df.iterrows():
        code = row['基金代码']
        status, amount_str = format_display_logic(row)
        limit_dict[code] = f"{status}, {amount_str}"
    
    return limit_dict

# ==============================================================================
# ====== 5. 交易方式判断模块 (原 mode_monitor 场内场外和拖拉机判断.py) ======
# ==============================================================================
def fund_type_judge(code):
    """
    根据基金代码前缀判断交易方式/类型。
    返回：
        "场内_账户限购(可拖拉机)"
        "场内_身份证限购"
        "场内交易"
        "场外申购"
    """
    if code.startswith("50"):
        return "场内_身份证限购"
    elif code.startswith("16"):
        return "场内_账户限购(可拖拉机)"
    elif code.startswith("15"):
        return "场内交易"
    elif code.startswith(("51", "58")):
        return "场内交易"
    else:
        return "场外申购"

def fetch_notice_text(code):
    """获取基金公告页面前2000字符"""
    try:
        url = f"https://fundf10.eastmoney.com/jjgg_{code}.html"
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            return r.text[:2000]
    except:
        pass
    return ""

def enhance_judge(code, base_result):
    """根据公告内容修正交易方式判断，优先检测身份证限购关键词"""
    text = fetch_notice_text(code)

    if not text:
        return base_result

    # 调试输出公告前200字符（便于查看抓取内容）
    print(f"\n[公告调试] {code} 前200字符:\n{text[:200]}\n")

    # 扩展身份证限购关键词列表
    id_keywords = [
        "单个投资者", "单个账户", "单一投资者", "单一账户",
        "单个基金账户", "每个基金账户", "单日单个基金账户"
    ]
    # 先检查身份证限购关键词（即使有暂停申购字样）
    if any(kw in text for kw in id_keywords):
        return "场内_身份证限购（公告识别）"

    # 再检查暂停申购
    if "暂停申购" in text:
        return "暂停申购"

    return base_result

# ==============================================================================
# ====== 6. 溢价率计算核心模块 (原 monitor溢价率计算.py) ======
# ==============================================================================
def get_ping_data(code):
    """获取并缓存 pingzhongdata.js 内容"""
    if code in PING_CACHE:
        return PING_CACHE[code]
    txt = safe_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")
    if not txt:
        return None
    PING_CACHE[code] = txt
    return txt

def get_market_change(ticker):
    """获取标的资产涨跌幅（Yahoo Finance）"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()["chart"]["result"][0]["meta"]
        return (data["regularMarketPrice"] / data["previousClose"]) - 1
    except:
        return 0.0

def get_fx():
    """获取离岸人民币汇率涨跌幅"""
    return get_market_change("CNH=F")

def get_fund_estimate(code):
    """获取天天基金实时估值和昨日净值"""
    txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt:
        return None, None
    try:
        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        return float(data["dwjz"]), float(data["gsz"])
    except:
        return None, None

def get_em_nav(code):
    """从东方财富 pingzhongdata 获取最新净值"""
    txt = get_ping_data(code)
    if not txt:
        return None
    try:
        match = re.search(r"Data_netWorthTrend = (.*?);", txt)
        return float(json.loads(match.group(1))[-1]["y"])
    except:
        return None

def get_price(code):
    """获取基金实时价格（腾讯接口）"""
    prefix = "sh" if code.startswith("5") else "sz"
    txt = safe_get(f"http://qt.gtimg.cn/q={prefix}{code}")
    if not txt:
        return None
    try:
        price = float(txt.split("~")[3])
        return price if price != 0 else None
    except:
        return None

def detect_type(dwjz, gsz):
    """判断基金类型：若存在估值且与昨日净值差异明显，则为 QDII_LOF，否则为普通"""
    if gsz and abs(gsz - dwjz) > 0.005:
        return "QDII_LOF"
    return "NORMAL"

# ==============================================================================
# ====== 7. 运行频率控制（开市/休市） ======
# ==============================================================================
def should_run():
    """
    判断当前是否应该运行监控。
    若在交易时段内（周一至周五 9:30-11:30 或 13:00-15:00），返回 True；
    若不在交易时段，则检查上次运行时间是否超过3小时，若超过返回 True，否则 False。
    使用文件 last_run.txt 记录上次运行时间戳（UTC+8 日期时间字符串）。
    """
    now = datetime.now(CN_TZ)
    weekday = now.weekday()  # 0=周一, 6=周日
    hour = now.hour
    minute = now.minute

    # 判断是否在交易时段内
    in_trading_session = False
    if 0 <= weekday <= 4:  # 周一至周五
        # 上午 9:30 - 11:30
        if (hour == 9 and minute >= 30) or (10 <= hour <= 10) or (hour == 11 and minute <= 30):
            in_trading_session = True
        # 下午 13:00 - 15:00
        elif (13 <= hour <= 14) or (hour == 15 and minute == 0):
            in_trading_session = True

    if in_trading_session:
        # 交易时段直接运行
        return True

    # 休市时段：检查上次运行时间
    last_run_file = "last_run.txt"
    if os.path.exists(last_run_file):
        try:
            with open(last_run_file, "r") as f:
                last_run_str = f.read().strip()
                last_run = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
                last_run = CN_TZ.localize(last_run)  # 设为北京时间
        except:
            last_run = None
    else:
        last_run = None

    if last_run is None:
        # 没有记录，允许运行
        return True

    # 计算时间差（秒）
    delta = (now - last_run).total_seconds()
    if delta >= 3 * 3600:  # 3小时
        return True
    else:
        print(f"休市时段，距离上次运行不足3小时（{delta/3600:.1f}小时），跳过本次运行。")
        return False

def update_last_run():
    """更新上次运行时间文件"""
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with open("last_run.txt", "w") as f:
        f.write(now)

# ==============================================================================
# ====== 8. HTML 报告生成（分板块，加强视觉区分） ======
# ==============================================================================
def parse_limit_info(limit_str):
    """从 "状态, 金额描述" 解析出状态和限额数值（如果存在）"""
    if ', ' in limit_str:
        status_part, amount_desc = limit_str.split(', ', 1)
    else:
        status_part, amount_desc = limit_str, ""
    # 从金额描述中提取数字（忽略逗号）
    digits = re.findall(r'\d+', amount_desc.replace(',', ''))
    if digits:
        limit_value = int(''.join(digits))
    else:
        limit_value = None
    return status_part, amount_desc, limit_value

def generate_html(results, report_time):
    """生成包含溢价、限购、交易方式的移动端友好 HTML，并分为今日关注和暂无机会"""
    # 分类
    focus_list = []
    other_list = []
    for item in results:
        premium = item['premium']
        limit_str = item['limit']
        status_part, amount_desc, limit_value = parse_limit_info(limit_str)

        # 今日关注基本条件：溢价率>3% 且 状态不是暂停申购 且 有限额（不是不限额）
        if premium > 0.03 and status_part != "暂停申购" and amount_desc != "不限额":
            # 额外条件：如果是开放申购，且限额>10000，则放入暂无机会
            if status_part == "开放申购" and limit_value is not None and limit_value > 10000:
                other_list.append(item)
            else:
                focus_list.append(item)
        else:
            other_list.append(item)

    # 生成两个板块的HTML行
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
        <div class="trade_type" style="font-size:11px; color:#aaa; margin-top:2px;">{item['trade_type']}</div>
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
    .section {{ padding: 10px 15px; background: #f9f9fc; border-bottom: 1px solid #e0e0e0; font-weight: 600; color: #555; }}
    /* 为第二个板块增加上边距，视觉区分更明显 */
    .section + .section {{ margin-top: 15px; }}
    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #f0f0f0; }}
    .right {{ text-align: right; }}
    .premium_line {{ display: flex; align-items: baseline; justify-content: flex-end; margin-bottom: 4px; }}
    .premium {{ font-weight: 900; font-size: 20px; }}
    .signal-tag {{ font-size: 13px; margin-left: 6px; color: #666; }}
    .limit_info {{ font-size: 12px; color: #888; margin-top: 2px; }}
    .trade_type {{ font-size: 11px; color: #aaa; }}
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
            <h3 style="margin:0; font-size:18px;">实时溢价与限购监控</h3>
            <p style="margin:5px 0 0; font-size:12px; color:#999;">更新: {report_time}</p>
        </div>

        <div class="section">今日关注</div>
        {focus_rows if focus_rows else '<div class="empty">暂无满足条件的基金</div>'}

        <div class="section">暂无机会</div>
        {other_rows if other_rows else '<div class="empty">暂无其他基金</div>'}
    </div>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("--- 报告生成成功: index.html (分板块，视觉优化) ---")

# ==============================================================================
# ====== 9. 主程序入口 ======
# ==============================================================================
def run():
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"基金监控系统 v3.4 启动... {now}")

    # 运行频率控制
    if not should_run():
        print("本次触发未满足运行条件，退出。")
        return

    # 获取限购信息字典
    print("正在获取限购数据...")
    limits = get_purchase_limits_dict()
    
    # 获取汇率变化
    fx_change = get_fx()
    
    results = []
    for code, info in FUND_CONFIG.items():
        try:
            # 获取实时价格
            price = get_price(code)
            if not price:
                print(f"警告: {code} 无法获取实时价格，跳过")
                continue

            # 获取净值及估值
            dwjz, gsz = get_fund_estimate(code)
            if not dwjz:
                dwjz = get_em_nav(code)
            if not dwjz:
                print(f"警告: {code} 无法获取净值，跳过")
                continue

            ftype = detect_type(dwjz, gsz)
            ticker = info["ticker"]

            if ticker:
                asset_change = get_market_change(ticker)
                fx = 1 + fx_change if ticker != "GC=F" else 1
            else:
                asset_change, fx = 0, 1

            # 估算净值
            est_nav = dwjz * (1 + asset_change * info["w"]) * fx
            if ftype == "QDII_LOF" and gsz:
                est_nav = gsz

            # 计算溢价率（简单平均）
            p1 = (price - dwjz) / dwjz if dwjz else 0
            p2 = (price - est_nav) / est_nav if est_nav else 0
            premium = (p1 + p2) / 2

            # 信号处理
            if premium >= 0.05:
                signal, color = "🔴 套利", "strong_arbitrage"
            elif premium >= 0.03:
                signal, color = "🟡 关注", "watch"
            elif premium >= 0:
                signal, color = "⚪ 正常", "normal"
            else:
                signal, color = "⚫ 折价", "discount"

            # 获取限购信息（默认显示未知）
            limit_info = limits.get(code, "未知状态, -")
            
            # 获取交易方式（基础判断 + 公告增强）
            base_trade_type = fund_type_judge(code)
            trade_type = enhance_judge(code, base_trade_type)

            results.append({
                "code": code,
                "name": info["name"],
                "premium": premium,
                "signal": signal,
                "color": color,
                "limit": limit_info,
                "trade_type": trade_type
            })
        except Exception as e:
            print(f"错误 {code}: {str(e)}")
            continue

    # 按溢价率降序排序
    results.sort(key=lambda x: x["premium"], reverse=True)

    # 生成 HTML
    generate_html(results, now)
    
    # 更新上次运行时间
    update_last_run()
    print("任务执行完毕。")

if __name__ == "__main__":
    run()
