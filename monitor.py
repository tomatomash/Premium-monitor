import re
import json
import requests
import pytz
from datetime import datetime

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
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.eastmoney.com/"
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
        price = data["regularMarketPrice"]
        prev = data["previousClose"]
        return (price / prev) - 1
    except:
        return 0.0

# ================= 汇率 =================
def get_fx():
    return get_market_change("CNH=F")

# ================= 天天基金估值 =================
def get_fund_estimate(code):
    txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt:
        return None, None
    try:
        data = json.loads(re.search(r"jsonpgz\((.*?)\);", txt).group(1))
        dwjz = float(data["dwjz"])
        gsz = float(data["gsz"])
        return dwjz, gsz
    except:
        return None, None

# ================= 东方财富NAV =================
def get_em_nav(code):
    txt = get_ping_data(code)
    if not txt:
        return None
    try:
        match = re.search(r"Data_netWorthTrend = (.*?);", txt)
        data = json.loads(match.group(1))
        return float(data[-1]["y"])
    except:
        return None

# ================= 实时价格 =================
def get_price(code):
    if code.startswith("5"):
        txt = safe_get(f"http://qt.gtimg.cn/q=sh{code}")
    else:
        txt = safe_get(f"http://qt.gtimg.cn/q=sz{code}")
    if not txt:
        return None
    try:
        price = float(txt.split("~")[3])
        if price == 0:
            return None
        return price
    except:
        return None

# ================= 类型识别 =================
def detect_type(dwjz, gsz):
    if gsz and abs(gsz - dwjz) > 0.005:
        return "QDII_LOF"
    return "NORMAL"

# ================= 【优化】主数据源：腾讯财经API（稳定） =================
def get_purchase_status_primary(code):
    """
    主数据源：腾讯财经基金基础信息接口（返回JSON，无需解析HTML）
    返回: (状态字符串, 限购额度元)
    """
    try:
        url = f"http://web.ifzq.gtimg.cn/fund/newfund/fund_base/getFundBase?app=web&fundid={code}"
        txt = safe_get(url)
        if not txt:
            return "主源接口失败", None

        data = json.loads(txt)
        if data.get("code") != 0:
            return "主源数据异常", None

        fund_base = data.get("data", {}).get("fund_base", {})
        status_raw = fund_base.get("funde_buy_status", "").strip()
        limit_raw = fund_base.get("funde_buy_limit", "").strip()

        # 状态解析
        if "暂停" in status_raw:
            status = "暂停申购"
        elif "限购" in status_raw or "限制" in status_raw:
            status = "限制申购"
        else:
            status = "开放申购"

        # 限购解析
        limit = None
        if limit_raw and "不限" not in limit_raw:
            # 提取数字（支持小数点）
            match = re.search(r"(\d+(?:\.\d+)?)", limit_raw.replace(',', ''))
            if match:
                limit = float(match.group(1))
                # 如果单位包含“万”，需转换
                if "万" in limit_raw:
                    limit *= 10000
        return status, limit

    except Exception as e:
        print(f"⚠️  腾讯财经主源异常 {code}: {str(e)}")
        return "主源异常", None

# ================= 【独立模块 - 备选数据源】和讯基金 =================
def get_purchase_status_backup_hexun(code):
    """
    备选数据源1：和讯基金（页面解析）
    """
    try:
        url = f"https://funds.hexun.com/{code}.shtml"
        txt = safe_get(url)
        if not txt:
            return "和讯接口失败", None

        status = "开放申购"
        limit = None

        if "暂停申购" in txt:
            status = "暂停申购"
        elif "限制申购" in txt or "限购" in txt:
            status = "限制申购"

        limit_patterns = [
            r'单日申购限额.*?[:：]\s*([\d,.]+)(?:万元|元)',
            r'单个账户单日累计申购上限.*?[:：]\s*([\d,.]+)(?:万元|元)',
            r'申购上限.*?[:：]\s*([\d,.]+)(?:万元|元)'
        ]
        for pattern in limit_patterns:
            limit_match = re.search(pattern, txt)
            if limit_match:
                limit_str = limit_match.group(1).replace(',', '').strip()
                limit = float(limit_str)
                if "万元" in limit_match.group(0):
                    limit *= 10000
                break

        return status, limit
    except Exception as e:
        print(f"⚠️  和讯备源异常 {code}: {str(e)}")
        return "和讯异常", None

# ================= 【独立模块 - 备选数据源】金融界基金 =================
def get_purchase_status_backup_jrj(code):
    """
    备选数据源2：金融界基金（页面解析）
    """
    try:
        url = f"https://fund.jrj.com.cn/{code}.shtml"
        txt = safe_get(url)
        if not txt:
            return "金融界接口失败", None

        status = "开放申购"
        limit = None

        if "暂停申购" in txt:
            status = "暂停申购"
        elif "限制申购" in txt or "限购" in txt:
            status = "限制申购"

        limit_patterns = [
            r'单日申购限额.*?[:：]\s*([\d,.]+)(?:万元|元)',
            r'单个账户单日累计申购上限.*?[:：]\s*([\d,.]+)(?:万元|元)',
            r'申购上限.*?[:：]\s*([\d,.]+)(?:万元|元)'
        ]
        for pattern in limit_patterns:
            limit_match = re.search(pattern, txt)
            if limit_match:
                limit_str = limit_match.group(1).replace(',', '').strip()
                limit = float(limit_str)
                if "万元" in limit_match.group(0):
                    limit *= 10000
                break

        return status, limit
    except Exception as e:
        print(f"⚠️  金融界备源异常 {code}: {str(e)}")
        return "金融界异常", None

# ================= 【统一入口】申购状态获取（主备切换） =================
def get_purchase_status(code):
    """
    统一入口函数，优先使用主数据源（腾讯API），失败则依次尝试备选源
    返回: (状态字符串, 限购额度元)
    """
    status, limit = get_purchase_status_primary(code)
    if "失败" in status or "异常" in status:
        print(f"🔄  主源失败，切换到和讯备源 {code}")
        status, limit = get_purchase_status_backup_hexun(code)
        if "失败" in status or "异常" in status:
            print(f"🔄  和讯备源失败，切换到金融界备源 {code}")
            status, limit = get_purchase_status_backup_jrj(code)
    return status, limit

# ================= 格式化申购状态（原逻辑完全不动） =================
def format_purchase_status(status, limit):
    if status == "暂停申购":
        return "暂停申购"
    if limit:
        if limit >= 10000:
            return f"{int(limit/10000)}万元"
        else:
            return f"{int(limit)}元"
    return "不限购"

# ================= 主程序（仅添加申购状态打印，核心逻辑完全不变） =================
def run():
    now = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    fx_change = get_fx()
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            price = get_price(code)
            if not price:
                print(f"SKIP {code} price error")
                continue

            dwjz, gsz = get_fund_estimate(code)
            if not dwjz:
                dwjz = get_em_nav(code)
            if not dwjz:
                print(f"SKIP {code} nav error")
                continue

            ftype = detect_type(dwjz, gsz)
            ticker = info["ticker"]

            if ticker:
                asset_change = get_market_change(ticker)
                fx = 1 + fx_change if ticker != "GC=F" else 1
            else:
                asset_change = 0
                fx = 1

            est_nav = dwjz * (1 + asset_change * info["w"]) * fx
            if ftype == "QDII_LOF" and gsz:
                est_nav = gsz

            p1 = (price - dwjz) / dwjz
            p2 = (price - est_nav) / est_nav

            # 获取申购状态
            status, limit = get_purchase_status(code)
            print(f"CHECK {code} {info['name']} -> P1:{p1:.2%} P2:{p2:.2%} 申购状态: {status} 限购额度: {limit}元")

            premium = (p1 + p2) / 2
            if premium >= 0.05:
                signal = "🔴 套利"
                color = "strong_arbitrage"
            elif premium >= 0.03:
                signal = "🟡 关注"
                color = "watch"
            elif premium >= 0:
                signal = "⚪ 正常"
                color = "normal"
            else:
                signal = "⚫ 折价"
                color = "discount"

            purchase = format_purchase_status(status, limit)

            results.append({
                "code": code,
                "name": info["name"],
                "premium": premium,
                "signal": signal,
                "color": color,
                "purchase": purchase
            })
        except Exception as e:
            print(f"ERROR {code}: {str(e)}")

    results.sort(key=lambda x: x["premium"], reverse=True)
    rows = ""
    for i in results:
        rows += f'''
<div class="row">
<div>
<b>{i['name']}</b><br>
{i['code']}<br>
申购: {i['purchase']}
</div>

<div class="right">
<div class="premium {i['color']}">{i['premium']:.2%}</div>
<div class="signal">{i['signal']}</div>
</div>
</div>
'''

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{{font-family:sans-serif;margin:0;padding:10px;background:#f6f6f6}}
.container{{max-width:480px;margin:auto;background:white;border-radius:10px;overflow:hidden}}
.header{{padding:15px 12px;border-bottom:1px solid #eee}}
.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee}}
.right{{text-align:right}}
.premium{{font-weight:bold;font-size:16px;margin-bottom:4px}}
.signal{{font-size:14px;color:#666}}
.strong_arbitrage{{color:#cf1322}}
.watch{{color:#faad14}}
.normal{{color:#1890ff}}
.discount{{color:#888}}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h3 style="margin:0">套利溢价率</h3>
<p style="margin:5px 0 0;color:#666">更新时间: {now}</p>
</div>
{rows}
</div>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
