
import re
import json
import requests
import pytz
from datetime import datetime

# ================= 基金配置 =================

FUND_CONFIG = {

    "161116": {"name":"易基黄金","ticker":"GC=F","w":0.99},
    "160416": {"name":"石油基金","ticker":"XOP","w":0.82},

    "501225": {"name":"全球芯片","ticker":"SOXX","w":0.88},
    "501018": {"name":"南方原油LOF","ticker":"CL=F","w":0.95},
}

HEADERS={"User-Agent":"Mozilla/5.0"}

CN_TZ=pytz.timezone("Asia/Shanghai")


# ================= 安全请求 =================

def safe_get(url):

    try:

        r=requests.get(url,headers=HEADERS,timeout=10)

        if r.status_code==200:
            return r.text

    except:
        pass

    return None


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

    txt=safe_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")

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
        return float(txt.split("~")[3])

    except:
        return None


# ================= 类型识别 =================

def detect_type(dwjz,gsz):

    if gsz and abs(gsz-dwjz)>0.005:
        return "QDII_LOF"

    return "NORMAL"


# ================= 主程序 =================

def run():

    now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    fx_change=get_fx()

    results=[]

    for code,info in FUND_CONFIG.items():

        try:

            price=get_price(code)

            if not price:
                print(f"ERROR price {code}")
                continue

            dwjz,gsz=get_fund_estimate(code)

            if not dwjz:
                dwjz=get_em_nav(code)

            if not dwjz:
                print(f"ERROR nav {code}")
                continue

            ftype=detect_type(dwjz,gsz)

            asset_change=get_market_change(info["ticker"])

            fx=1+fx_change if info["ticker"]!="GC=F" else 1

            est_nav=dwjz*(1+asset_change*info["w"])*fx

            if ftype=="QDII_LOF" and gsz:
                est_nav=gsz

            p1=(price-dwjz)/dwjz
            p2=(price-est_nav)/est_nav

            # ===== Debug 输出 =====

            print(f"CHECK {code} {info['name']} {ftype} -> P1:{p1:.2%} P2:{p2:.2%}")

            # ===== 网页使用平均值 =====

            premium=(p1+p2)/2

            color="plus" if premium>0.02 else "minus"

            results.append({

                "code":code,
                "name":info["name"],
                "premium":premium,
                "color":color

            })

        except Exception as e:

            print("ERROR",code,e)

    results.sort(key=lambda x:x["premium"],reverse=True)

    rows=""

    for i in results:

        rows+=f'''
<div class="row">
<div><b>{i["name"]}</b><br>{i["code"]}</div>
<div class="premium {i["color"]}">
{i["premium"]:.2%}
</div>
</div>
'''

    html=f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>

body{{font-family:sans-serif}}

.row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee}}

.plus{{color:#cf1322;font-weight:bold}}

.minus{{color:#389e0d}}

.premium{{text-align:right}}

</style>
</head>

<body>

<div style="max-width:480px;margin:auto">

<h3>溢价精算 Alpha</h3>

<p>更新时间: {now}</p>

{rows}

</div>

</body>
</html>
"""

    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)


if __name__=="__main__":

    run()
