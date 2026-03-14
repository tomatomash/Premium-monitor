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

HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CN_TZ=pytz.timezone("Asia/Shanghai")

# ================= pingzhongdata缓存 =================
PING_CACHE={}

# ================= 安全请求 =================
def safe_get(url):
    try:
        r=requests.get(url,headers=HEADERS,timeout=10)
        if r.status_code==200:
            return r.text
    except:
        pass
    return None

# ================= ping数据缓存 =================
def get_ping_data(code):
    if code in PING_CACHE:
        return PING_CACHE[code]
    txt=safe_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")
    if not txt:
        return None
    PING_CACHE[code]=txt
    return txt

# ================= 市场涨跌 =================
def get_market_change(ticker):
    try:
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        r=requests.get(url,headers=HEADERS,timeout=10)
        data=r.json()["chart"]["result"][0]["meta"]
        price=data["regularMarketPrice"]
        prev=data["previousClose"]
        return (price/prev)-1
    except:
        return 0.0

# ================= 汇率 =================
def get_fx():
    return get_market_change("CNH=F")

# ================= 天天基金估值 =================
def get_fund_estimate(code):
    txt=safe_get(f"http://fundgz.1234567.com.cn/js/{code}.js")
    if not txt:
        return None,None
    try:
        data=json.loads(re.search(r"jsonpgz\((.*?)\);",txt).group(1))
        dwjz=float(data["dwjz"])
        gsz=float(data["gsz"])
        return dwjz,gsz
    except:
        return None,None

# ================= 东方财富NAV =================
def get_em_nav(code):
    txt=get_ping_data(code)
    if not txt:
        return None
    try:
        match=re.search(r"Data_netWorthTrend = (.*?);",txt)
        data=json.loads(match.group(1))
        return float(data[-1]["y"])
    except:
        return None

# ================= 实时价格 =================
def get_price(code):
    if code.startswith("5"):
        txt=safe_get(f"http://qt.gtimg.cn/q=sh{code}")
    else:
        txt=safe_get(f"http://qt.gtimg.cn/q=sz{code}")
    if not txt:
        return None
    try:
        price=float(txt.split("~")[3])
        if price==0:
            return None
        return price
    except:
        return None

# ================= 类型识别 =================
def detect_type(dwjz,gsz):
    if gsz and abs(gsz-dwjz)>0.005:
        return "QDII_LOF"
    return "NORMAL"

# ================= 【独立模块】申购状态接口（天天基金网稳定源） =================
def get_purchase_status(code):
    """
    独立封装的申购状态获取函数，返回 (状态字符串, 限购额度元)
    不影响任何其他模块逻辑
    """
    try:
        # 天天基金网基金公告接口，包含最新申购状态和限购信息
        url = f"https://fund.1234567.com.cn/data/1234567/f10/jjgg/{code}.js"
        txt = safe_get(url)
        if not txt:
            return "接口失败", None
        
        # 解析JSONP格式
        jsonp_match = re.search(r"jQuery\d+_\d+\((.*?)\);", txt)
        if not jsonp_match:
            return "解析失败", None
        
        data = json.loads(jsonp_match.group(1))
        
        status = "开放申购"
        limit = None
        
        # 遍历公告，找到最新的申购相关公告
        for item in data.get("Data", []):
            title = item.get("title", "").strip()
            if "暂停申购" in title:
                status = "暂停申购"
                break
            elif "限制申购" in title or "限购" in title:
                status = "限制申购"
                # 提取限购金额，单位元
                limit_match = re.search(r'(\d+(?:\.\d+)?)(?:万元|元)', title)
                if limit_match:
                    num = float(limit_match.group(1))
                    if "万元" in title:
                        limit = num * 10000  # 转换为元
                    else:
                        limit = num
                break
        
        return status, limit
    except Exception as e:
        print(f"⚠️  获取申购状态异常 {code}: {str(e)}")
        return "异常", None

# ================= 格式化申购状态（原逻辑完全不动） =================
def format_purchase_status(status,limit):
    if status=="暂停申购":
        return "暂停申购"
    if limit:
        if limit>=10000:
            return f"{int(limit/10000)}万元"
        else:
            return f"{int(limit)}元"
    return "不限购"

# ================= 主程序（仅添加申购状态打印，核心逻辑完全不变） =================
def run():
    now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    fx_change=get_fx()
    results=[]

    for code,info in FUND_CONFIG.items():
        try:
            price=get_price(code)
            if not price:
                print(f"SKIP {code} price error")
                continue

            dwjz,gsz=get_fund_estimate(code)
            if not dwjz:
                dwjz=get_em_nav(code)
            if not dwjz:
                print(f"SKIP {code} nav error")
                continue

            ftype=detect_type(dwjz,gsz)
            ticker=info["ticker"]

            if ticker:
                asset_change=get_market_change(ticker)
                fx=1+fx_change if ticker!="GC=F" else 1
            else:
                asset_change=0
                fx=1

            est_nav=dwjz*(1+asset_change*info["w"])*fx
            if ftype=="QDII_LOF" and gsz:
                est_nav=gsz

            p1=(price-dwjz)/dwjz
            p2=(price-est_nav)/est_nav
            
            # 获取并打印申购状态，和P1/P2一起显示
            status, limit = get_purchase_status(code)
            print(f"CHECK {code} {info['name']} -> P1:{p1:.2%} P2:{p2:.2%} 申购状态: {status} 限购额度: {limit}元")

            premium=(p1+p2)/2
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

            purchase=format_purchase_status(status,limit)

            results.append({
                "code":code,
                "name":info["name"],
                "premium":premium,
                "signal":signal,
                "color":color,
                "purchase":purchase
            })
        except Exception as e:
            print(f"ERROR {code}: {str(e)}")

    results.sort(key=lambda x:x["premium"],reverse=True)
    rows=""
    for i in results:
        rows+=f'''
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

    html=f"""
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
    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)

if __name__=="__main__":
    run()
