import re
import json
import requests
import pytz
from datetime import datetime

# ================= 基金配置 =================

FUND_CONFIG = {

    "161116": {"name":"易基黄金","ticker":"GC=F","w":0.99,"fx":False},
    "160416": {"name":"石油基金","ticker":"XOP","w":0.82,"fx":True},

    "501225": {"name":"全球芯片","ticker":"SOXX","w":0.88,"fx":True},
    "501018": {"name":"南方原油LOF","ticker":"CL=F","w":0.95,"fx":False},
}

HEADERS = {"User-Agent":"Mozilla/5.0"}

CN_TZ = pytz.timezone("Asia/Shanghai")


# ================= 外盘涨跌 =================

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


# ================= 实时估值接口 =================

def get_estimate_nav(code):

    try:

        url=f"http://fundgz.1234567.com.cn/js/{code}.js"

        r=requests.get(url,headers=HEADERS,timeout=10)

        match=re.search(r"jsonpgz\((.*?)\);",r.text)

        if match:

            data=json.loads(match.group(1))

            dwjz=float(data["dwjz"])
            gsz=float(data["gsz"])

            return dwjz,gsz

    except:

        pass

    return None,None


# ================= 东方财富历史净值 =================

def get_em_nav(code):

    try:

        url=f"https://fund.eastmoney.com/pingzhongdata/{code}.js"

        r=requests.get(url,headers=HEADERS,timeout=10)

        match=re.search(r"Data_netWorthTrend = (.*?);",r.text)

        data=json.loads(match.group(1))

        t1=float(data[-2]["y"])
        today=float(data[-1]["y"])

        return t1,today

    except:

        return None,None


# ================= 价格 =================

def get_price(code):

    try:

        if code.startswith("5"):

            r=requests.get(f"http://qt.gtimg.cn/q=sh{code}",headers=HEADERS,timeout=10)

        else:

            r=requests.get(f"http://qt.gtimg.cn/q=sz{code}",headers=HEADERS,timeout=10)

        return float(r.text.split("~")[3])

    except:

        return None


# ================= 主程序 =================

def run():

    now=datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    fx_change=get_fx()

    results=[]

    for code,info in FUND_CONFIG.items():

        try:

            price=get_price(code)

            dwjz,gsz=get_estimate_nav(code)

            # ================= 类型1：QDII LOF =================
            if gsz and abs(gsz-dwjz)>0.005:

                nav=gsz

                p1=(price-dwjz)/dwjz
                p2=(price-gsz)/gsz

                print(f"CHECK: {code} {info['name']} -> QDII_LOF  P1:{p1:.2%}, P2:{p2:.2%}")

            # ================= 类型2：普通基金 =================
            else:

                nav=dwjz

                asset_change=get_market_change(info["ticker"])

                if info["fx"]:

                    est_nav=nav*(1+asset_change*info["w"])*(1+fx_change)

                else:

                    est_nav=nav*(1+asset_change*info["w"])

                p1=(price-nav)/nav
                p2=(price-est_nav)/est_nav

                print(f"CHECK: {code} {info['name']} -> NORMAL  P1:{p1:.2%}, P2:{p2:.2%}")

            p_min=min(p1,p2)
            p_max=max(p1,p2)

            color="plus" if p2>0.02 else "minus"

            results.append({

                "code":code,
                "name":info["name"],
                "p_min":p_min,
                "p_max":p_max,
                "p2":p2,
                "color":color

            })

        except Exception as e:

            print(f"ERROR: {code} -> {e}")

    results.sort(key=lambda x:x["p2"],reverse=True)

    rows=""

    for i in results:

        rows+=f'''
<div class="row">
<div><b>{i["name"]}</b><br>{i["code"]}</div>
<div class="premium {i["color"]}">
{i["p_min"]:.2%} ~ {i["p_max"]:.2%}
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
