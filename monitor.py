import re
import json
import requests
import pytz
from datetime import datetime
from bs4 import BeautifulSoup

# ================= 基金配置 =================
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
    "161130": {"name": "纳指100", "ticker": "QQQ", "w": 0.95},
    "162411": {"name": "华宝油气", "ticker": "XOP", "w": 0.90},
    "163208": {"name": "全球油气", "ticker": "XOP", "w": 0.90},

    # ------ 国内 A 股基金 (已取消海外关联) ------
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}
CN_TZ = pytz.timezone("Asia/Shanghai")

# ================= pingzhongdata缓存 =================
PING_CACHE = {}

# ================= 安全请求 =================
def safe_get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return None

# ================= 爬取 GitHub Pages 限购数据 =================
def fetch_purchase_limits():
    """解析 GitHub Pages 中的表格数据"""
    url = "https://tomatomash.github.io/fund-monitor-report/"
    html = safe_get(url)
    limit_map = {}
    if not html:
        return limit_map

    try:
        soup = BeautifulSoup(html, 'html.parser')
        # 查找所有表格行 (Pandas 生成的 HTML 会有 tr 标签)
        rows = soup.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 4:
                # 根据你提供的生成代码：0:代码, 1:基金名称, 2:当前状态, 3:单日限额(元)
                code = cols[0].get_text(strip=True)
                status = cols[2].get_text(strip=True)
                amount = cols[3].get_text(strip=True)
                
                # 统一显示格式
                if "暂停" in status:
                    display_text = "暂停申购, -"
                elif "不限额" in amount:
                    display_text = "开放申购, 不限额"
                else:
                    display_text = f"{status}, {amount}元"
                
                limit_map[code] = display_text
    except Exception as e:
        print(f"Fetch limit page error: {e}")
    return limit_map

# ================= ping数据缓存 =================
def get_ping_data(code):
    if code in PING_CACHE:
        return PING_CACHE[code]
    txt = safe_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")
    if not txt:
        return None
    PING_CACHE[code] = txt
    return txt

# ================= 市场涨跌 =================
def get_market_change(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()["chart"]["result"][0]["meta"]
        return (data["regularMarketPrice"] / data["previousClose"]) - 1
    except:
        return 0.0

# ================= 汇率 =================
def get_fx():
    return get_market_change("CNH=F")

# ================= 天天基金估值 =================
def get_fund_estimate(code):
    txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt: return None, None
    try:
        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        return float(data["dwjz"]), float(data["gsz"])
    except:
        return None, None

# ================= 东方财富NAV =================
def get_em_nav(code):
    txt = get_ping_data(code)
    if not txt: return None
    try:
        match = re.search(r"Data_netWorthTrend = (.*?);", txt)
        return float(json.loads(match.group(1))[-1]["y"])
    except:
        return None

# ================= 实时价格 =================
def get_price(code):
    prefix = "sh" if code.startswith("5") else "sz"
    txt = safe_get(f"http://qt.gtimg.cn/q={prefix}{code}")
    if not txt: return None
    try:
        price = float(txt.split("~")[3])
        return price if price != 0 else None
    except:
        return None

# ================= 类型识别 =================
def detect_type(dwjz, gsz):
    if gsz and abs(gsz - dwjz) > 0.005:
        return "QDII_LOF"
    return "NORMAL"

# ================= 主程序 =================
def run():
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    fx_change = get_fx()
    
    # 核心：获取限购爬取数据
    limits = fetch_purchase_limits()
    
    results = []
    for code, info in FUND_CONFIG.items():
        try:
            price = get_price(code)
            if not price: continue

            dwjz, gsz = get_fund_estimate(code)
            if not dwjz: dwjz = get_em_nav(code)
            if not dwjz: continue

            ftype = detect_type(dwjz, gsz)
            ticker = info["ticker"]

            if ticker:
                asset_change = get_market_change(ticker)
                fx = 1 + fx_change if ticker != "GC=F" else 1
            else:
                asset_change, fx = 0, 1

            est_nav = dwjz * (1 + asset_change * info["w"]) * fx
            if ftype == "QDII_LOF" and gsz: est_nav = gsz

            p1, p2 = (price - dwjz) / dwjz, (price - est_nav) / est_nav
            premium = (p1 + p2) / 2

            # 信号处理
            if premium >= 0.05: signal, color = "🔴 套利", "strong_arbitrage"
            elif premium >= 0.03: signal, color = "🟡 关注", "watch"
            elif premium >= 0: signal, color = "⚪ 正常", "normal"
            else: signal, color = "⚫ 折价", "discount"

            results.append({
                "code": code,
                "name": info["name"],
                "premium": premium,
                "signal": signal,
                "color": color,
                "limit": limits.get(code, "未知状态, -")
            })
        except Exception as e:
            print(f"ERROR {code}: {str(e)}")

    # 排序
    results.sort(key=lambda x: x["premium"], reverse=True)

    # HTML 生成逻辑（针对你的需求进行布局优化）
    rows = ""
    for i in results:
        rows += f'''
<div class="row">
    <div>
        <b style="font-size:15px; color:#333;">{i['name']}</b><br>
        <span style="color:#999; font-size:12px;">{i['code']}</span>
    </div>
    <div class="right">
        <div class="premium_line">
            <span class="premium {i['color']}">{i['premium']:.2%}</span>
            <span class="signal-tag">{i['signal']}</span>
        </div>
        <div class="limit_info">{i['limit']}</div>
    </div>
</div>'''

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
    body {{ font-family: -apple-system, sans-serif; background: #f4f4f7; margin: 0; padding: 15px; }}
    .container {{ max-width: 500px; margin: auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
    .header {{ padding: 15px; border-bottom: 1px solid #eee; background: #fff; }}
    .row {{ display: flex; justify-content: space-between; align-items: center; padding: 15px; border-bottom: 1px solid #f9f9f9; }}
    .right {{ text-align: right; }}
    .premium_line {{ display: flex; align-items: baseline; justify-content: flex-end; margin-bottom: 4px; }}
    .premium {{ font-weight: 900; font-size: 20px; }} /* 溢价率数值加粗 */
    .signal-tag {{ font-size: 13px; margin-left: 6px; color: #666; }}
    .limit_info {{ font-size: 12px; color: #888; margin-top: 2px; }} /* 限购信息置于下方 */
    .strong_arbitrage {{ color: #e63946; }}
    .watch {{ color: #f4a261; }}
    .normal {{ color: #2a9d8f; }}
    .discount {{ color: #6d6d6d; }}
</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h3 style="margin:0; font-size:18px;">实时溢价与限购监控</h3>
            <p style="margin:5px 0 0; font-size:12px; color:#999;">更新: {now}</p>
        </div>
        {rows}
    </div>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
