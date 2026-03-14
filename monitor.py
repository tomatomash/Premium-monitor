import requests
import re
import json
import datetime
import math

HEADERS={
"User-Agent":"Mozilla/5.0"
}

# ================= 基金配置 =================

FUND_CONFIG = {

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

# ================= HTTP =================

def safe_get(url):

    try:

        r=requests.get(url,headers=HEADERS,timeout=10)

        if r.status_code==200:

            return r.text

    except:

        return None

# ================= 实时价格 =================

def get_price(code):

    url=f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{code}&fields=f43"

    txt=safe_get(url)

    if not txt:
        return None

    try:

        data=json.loads(txt)

        return data["data"]["f43"]/1000

    except:

        return None

# ================= NAV =================

PING_CACHE={}

def get_ping_data(code):

    if code in PING_CACHE:

        return PING_CACHE[code]

    txt=safe_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")

    if txt:

        PING_CACHE[code]=txt

    return txt

def get_nav(code):

    txt=get_ping_data(code)

    if not txt:
        return None

    try:

        match=re.search(r"Data_netWorthTrend = (.*?);",txt)

        data=json.loads(match.group(1))

        return float(data[-1]["y"])

    except:

        return None

# ================= 申购状态接口1 =================

def purchase_api1(code):

    try:

        url=f"https://fundmobapi.eastmoney.com/FundMNewApi/FundBaseInfo?FCODE={code}"

        r=requests.get(url,headers=HEADERS,timeout=10)

        j=r.json()

        status=j["Datas"].get("SGZT")

        limit=j["Datas"].get("SGJE")

        return status,limit

    except:

        return None,None

# ================= 申购状态接口2 (备用) =================

def purchase_api2(code):

    try:

        url=f"https://fund.eastmoney.com/{code}.html"

        html=safe_get(url)

        if not html:
            return None,None

        if "暂停申购" in html:

            return "暂停申购",None

        if "限大额" in html:

            return "限购",None

        return "开放",None

    except:

        return None,None

# ================= 获取申购状态 =================

def get_purchase_status(code):

    status,limit=purchase_api1(code)

    if status:

        return status,limit

    status,limit=purchase_api2(code)

    if status:

        return status,limit

    return "未知",None

# ================= 海外资产涨跌 =================

def get_market_change(ticker):

    if ticker=="":
        return 0

    try:

        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

        r=requests.get(url,headers=HEADERS,timeout=10)

        j=r.json()

        close=j["chart"]["result"][0]["meta"]["regularMarketPrice"]

        prev=j["chart"]["result"][0]["meta"]["chartPreviousClose"]

        return (close-prev)/prev

    except:

        return 0

# ================= 主程序 =================

results=[]

for code,info in FUND_CONFIG.items():

    name=info["name"]
    ticker=info["ticker"]
    w=info["w"]

    price=get_price(code)

    nav=get_nav(code)

    change=get_market_change(ticker)

    if price and nav:

        p1=(price-nav)/nav*100
        p2=(price-(nav*(1+change*w)))/(nav*(1+change*w))*100

    else:

        p1=0
        p2=0

    avg=(p1+p2)/2

    # 申购状态
    status,limit=get_purchase_status(code)

    print(f"CHECK {code} {name} -> P1:{p1:.2f}% P2:{p2:.2f}% 申购:{status} 限额:{limit}")

    results.append({

        "code":code,
        "name":name,
        "premium":round(avg,2),
        "purchase":status

    })

# ================= HTML =================

results.sort(key=lambda x:x["premium"],reverse=True)

html=""

for i in results:

    p=i["premium"]

    if p>5:

        color="red"
        tag="套利"

    elif p>3:

        color="orange"
        tag="关注"

    else:

        color="gray"
        tag="正常"

    html+=f"""
<div>
<b>{i['name']}</b><br>
{i['code']}<br>
申购:{i['purchase']}<br>
<span style='color:{color};font-size:20px'>{p}%</span> {tag}
</div>
<hr>
"""

page=f"""
<html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<h2>套利溢价率</h2>
更新时间 {datetime.datetime.now()}
{html}
</html>
"""

open("index.html","w",encoding="utf8").write(page)
