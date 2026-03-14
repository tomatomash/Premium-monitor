import re
import json
import requests
import pytz
from datetime import datetime

# ================= 调试开关 =================
DEBUG = True  # 设为 True 打印详细日志，False 只打印关键信息

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
def safe_get(url, headers=None):
    if headers is None:
        headers = HEADERS
    try:
        if DEBUG:
            print(f"🔍 请求 URL: {url}")
        r = requests.get(url, headers=headers, timeout=10)
        if DEBUG:
            print(f"  响应状态码: {r.status_code}")
            if r.status_code == 200:
                preview = r.text[:200].replace('\n', ' ').replace('\r', '')
                print(f"  响应预览: {preview}...")
        if r.status_code == 200:
            return r.text
    except Exception as e:
        if DEBUG:
            print(f"  请求异常: {str(e)}")
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
        # 去除 jsonpgz() 包裹
        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        dwjz = float(data["dwjz"])
        gsz = float(data["gsz"])
        return dwjz, gsz
    except Exception as e:
        if DEBUG:
            print(f"  解析 fundgz 失败: {e}")
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
        # 腾讯股票接口格式：v_sh501225="1~全球芯片LOF~501225~2.345~..."
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

# ================= 【修复核心】主数据源：天天基金 pingzhongdata =================
def get_purchase_status_primary(code):
    """
    主数据源：天天基金 pingzhongdata.js (最稳定，已成功获取)
    从文件中提取申购状态和限购额度
    """
    try:
        txt = get_ping_data(code)
        if not txt:
            if DEBUG:
                print("  pingzhongdata: 无响应")
            return "主源接口失败", None

        # --- 提取申购状态 ---
        status = "开放申购"  # 默认
        # 常见状态变量名：fS_purchaseStatus, fS_purchaseStatusName, fS_redemptionStatus 等
        # 方法1: 查找 purchaseStatusName 或类似字段
        status_match = re.search(r'var\s+fS_purchaseStatusName\s*=\s*["\']([^"\']+)["\']', txt)
        if not status_match:
            status_match = re.search(r'var\s+fS_purchaseStatus\s*=\s*["\']([^"\']+)["\']', txt)
        if not status_match:
            # 兜底：在文本中查找关键词
            if "暂停申购" in txt:
                status = "暂停申购"
            elif "限购" in txt or "限制申购" in txt:
                status = "限制申购"
            else:
                status = "开放申购"
        else:
            status_raw = status_match.group(1)
            if "暂停" in status_raw:
                status = "暂停申购"
            elif "限购" in status_raw or "限制" in status_raw:
                status = "限制申购"
            else:
                status = "开放申购"

        # --- 提取限购额度 ---
        limit = None
        # 常见限购变量名：fS_minBuyAmount, fS_purchaseLimit, fS_singlePurchaseLimit
        # 优先查找限购金额（单位可能是元）
        limit_match = re.search(r'var\s+fS_singlePurchaseLimit\s*=\s*["\']?([\d,.]+)["\']?', txt)
        if not limit_match:
            limit_match = re.search(r'var\s+fS_purchaseLimit\s*=\s*["\']?([\d,.]+)["\']?', txt)
        if not limit_match:
            limit_match = re.search(r'var\s+fS_minBuyAmount\s*=\s*["\']?([\d,.]+)["\']?', txt)
        
        if limit_match:
            limit_str = limit_match.group(1).replace(',', '')
            try:
                limit = float(limit_str)
                # 通常限购金额以元为单位，但如果数值很小（如1.0），可能是万元，需结合上下文判断
                # 这里简单处理：如果 limit < 100 且 存在 "万" 字，则乘以10000
                if limit < 100 and "万" in txt[limit_match.start()-10:limit_match.end()+10]:
                    limit *= 10000
            except:
                pass

        if DEBUG:
            print(f"  pingzhongdata 解析结果: 状态={status}, 限购={limit}元")
        return status, limit

    except Exception as e:
        if DEBUG:
            print(f"  pingzhongdata 异常: {str(e)}")
        return "主源异常", None

# ================= 备选数据源1：天天基金估值接口 fundgz =================
def get_purchase_status_backup_gz(code):
    """
    备选数据源：天天基金估值接口 fundgz.1234567.com.cn
    有时会包含申购状态（如 fundStatus）
    """
    try:
        txt = safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
        if not txt:
            if DEBUG:
                print("  fundgz: 无响应")
            return "备源接口失败", None

        json_str = re.search(r"jsonpgz\((.*)\);?", txt).group(1)
        data = json.loads(json_str)
        
        # 尝试获取状态字段（字段名可能为 fundStatus、applyStatus 等）
        status_raw = data.get("fundStatus", "") or data.get("applyStatus", "") or ""
        if status_raw:
            if "暂停" in status_raw:
                status = "暂停申购"
            elif "限购" in status_raw:
                status = "限制申购"
            else:
                status = "开放申购"
        else:
            status = "开放申购"  # 无字段时默认开放

        # 限购额度（字段名可能为 purchaseLimit、limitAmount 等）
        limit_raw = data.get("purchaseLimit", "") or data.get("limitAmount", "") or ""
        limit = None
        if limit_raw and "不限" not in limit_raw:
            match = re.search(r"(\d+(?:\.\d+)?)", str(limit_raw).replace(',', ''))
            if match:
                limit = float(match.group(1))
                if "万" in str(limit_raw):
                    limit *= 10000

        if DEBUG:
            print(f"  fundgz 解析结果: 状态={status}, 限购={limit}元")
        return status, limit

    except Exception as e:
        if DEBUG:
            print(f"  fundgz 异常: {str(e)}")
        return "备源异常", None

# ================= 备选数据源2：和讯基金 =================
def get_purchase_status_backup_hexun(code):
    """
    备选数据源：和讯基金（页面解析）
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

        if DEBUG:
            print(f"  和讯解析结果: 状态={status}, 限购={limit}元")
        return status, limit
    except Exception as e:
        if DEBUG:
            print(f"  和讯异常: {str(e)}")
        return "和讯异常", None

# ================= 备选数据源3：金融界基金 =================
def get_purchase_status_backup_jrj(code):
    """
    备选数据源：金融界基金（页面解析）
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

        if DEBUG:
            print(f"  金融界解析结果: 状态={status}, 限购={limit}元")
        return status, limit
    except Exception as e:
        if DEBUG:
            print(f"  金融界异常: {str(e)}")
        return "金融界异常", None

# ================= 【统一入口】申购状态获取（多源切换） =================
def get_purchase_status(code):
    """
    统一入口：主源(pingzhongdata) -> 备源1(fundgz) -> 备源2(和讯) -> 备源3(金融界)
    """
    # 主源
    status, limit = get_purchase_status_primary(code)
    if "失败" not in status and "异常" not in status:
        return status, limit
    print(f"🔄  主源失败 ({status})，切换到 fundgz 备源 {code}")
    status, limit = get_purchase_status_backup_gz(code)
    if "失败" not in status and "异常" not in status:
        return status, limit
    print(f"🔄  fundgz 备源失败 ({status})，切换到和讯备源 {code}")
    status, limit = get_purchase_status_backup_hexun(code)
    if "失败" not in status and "异常" not in status:
        return status, limit
    print(f"🔄  和讯备源失败 ({status})，切换到金融界备源 {code}")
    status, limit = get_purchase_status_backup_jrj(code)
    return status, limit

# ================= 格式化申购状态 =================
def format_purchase_status(status, limit):
    if status == "暂停申购":
        return "暂停申购"
    if limit:
        if limit >= 10000:
            return f"{int(limit/10000)}万元"
        else:
            return f"{int(limit)}元"
    return "不限购"

# ================= 主程序 =================
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
