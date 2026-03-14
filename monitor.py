```python
import os
import re
import json
import requests
import pytz
from datetime import datetime

# ==================== 固化参数区 ====================

FUND_CONFIG = {

    # 深交所基金
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99, "fx": False},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82, "fx": True},

    # 沪交所 LOF
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88, "fx": True},
    "501018": {"name": "南方原油LOF", "ticker": "CL=F", "w": 0.95, "fx": False},

}

HEADERS = {
    'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
}

CN_TZ = pytz.timezone('Asia/Shanghai')


# ==================== 外盘资产涨跌 ====================

def get_market_data(ticker):

    try:

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"

        res = requests.get(url, headers=HEADERS, timeout=10)

        data = res.json()['chart']['result'][0]['meta']

        price = data['regularMarketPrice']
        prev = data['previousClose']

        return (price / prev) - 1

    except:

        return 0.0


# ==================== 汇率变化 ====================

def get_fx_change():

    try:

        return get_market_data("CNH=F")

    except:

        return 0.0


# ==================== 主程序 ====================

def run():

    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')

    fx_change = get_fx_change()

    results = []


    for code, info in FUND_CONFIG.items():

        try:

            # =========================================================
            # 轨道 A：深市基金 (16xxxx)
            # =========================================================

            if not code.startswith('5'):

                # ---------- 净值 ----------
                nav_res = requests.get(
                    f"http://fundgz.1234567.com.cn/js/{code}.js",
                    headers=HEADERS,
                    timeout=5
                )

                nav = float(
                    json.loads(
                        re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1)
                    )['dwjz']
                )

                # ---------- 实时价格 ----------
                p_res = requests.get(
                    f"http://qt.gtimg.cn/q=sz{code}",
                    headers=HEADERS,
                    timeout=5
                )

                mp = float(p_res.text.split('~')[3])

                # ---------- 外盘变化 ----------
                asset_change = get_market_data(info['ticker'])

                # ---------- 估算净值 ----------
                if info["fx"]:
                    est_nav = nav * (1 + asset_change * info['w']) * (1 + fx_change)
                else:
                    est_nav = nav * (1 + asset_change * info['w'])

                # ---------- 溢价计算 ----------
                p1 = (mp - nav) / nav
                p2 = (mp - est_nav) / est_nav

                print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")


            # =========================================================
            # 轨道 B：沪市 LOF (5xxxx)
            # =========================================================

            else:

                nav = None

                # ---------- 尝试1：东方财富真实净值 ----------

                try:

                    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"

                    res = requests.get(url, headers=HEADERS, timeout=10)

                    match = re.search(r'Data_netWorthTrend = (.*?);', res.text)

                    if match:

                        data = json.loads(match.group(1))

                        nav = float(data[-1]['y'])

                        print(f"【沪市净值成功】{code} 东方财富 -> {nav}")

                except Exception as e:

                    print(f"【沪市净值失败1】{code} {e}")


                # ---------- 尝试2：天天基金 ----------

                if nav is None:

                    try:

                        url = f"http://fundgz.1234567.com.cn/js/{code}.js"

                        res = requests.get(url, headers=HEADERS, timeout=10)

                        match = re.search(r'jsonpgz\((.*?)\);', res.text)

                        if match:

                            nav = float(json.loads(match.group(1))['dwjz'])

                            print(f"【沪市净值成功】{code} 天天基金 -> {nav}")

                    except Exception as e:

                        print(f"【沪市净值失败2】{code} {e}")


                if nav is None:

                    raise ValueError(f"{code} 无法获取净值")


                # ---------- 获取沪市实时价格 ----------

                p_res = requests.get(
                    f"http://qt.gtimg.cn/q=sh{code}",
                    headers=HEADERS,
                    timeout=5
                )

                mp = float(p_res.text.split('~')[3])

                print(f"【沪市价格】{code} -> {mp}")


                # ---------- 外盘变化 ----------

                asset_change = get_market_data(info['ticker'])

                # ---------- 估算净值 ----------

                if info["fx"]:
                    est_nav = nav * (1 + asset_change * info['w']) * (1 + fx_change)
                else:
                    est_nav = nav * (1 + asset_change * info['w'])


                # ---------- 溢价计算 ----------

                p1 = (mp - nav) / nav
                p2 = (mp - est_nav) / est_nav

                print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")


            # ==================== 排序数据 ====================

            p_min = min(p1, p2)
            p_max = max(p1, p2)

            color = "plus" if p2 > 0.02 else "minus"

            results.append({

                "code": code,
                "name": info["name"],
                "p_min": p_min,
                "p_max": p_max,
                "p2": p2,
                "color": color

            })


        except Exception as e:

            print(f"ERROR: {code} 计算出错: {e}")

            continue


    # ==================== 排序 ====================

    results.sort(key=lambda x: x['p2'], reverse=True)


    # ==================== 生成网页 ====================

    rows = ""

    for i in results:

        rows += f'''
<div class="row">
<div>
<b>{i["name"]}</b><br>{i["code"]}
</div>
<div class="premium {i["color"]}">
{i["p_min"]:.2%} ~ {i["p_max"]:.2%}
</div>
</div>
'''


    html = f'''
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<style>

body {{
font-family:sans-serif;
}}

.row {{
display:flex;
justify-content:space-between;
padding:12px;
border-bottom:1px solid #eee;
}}

.plus {{
color:#cf1322;
font-weight:bold;
}}

.minus {{
color:#389e0d;
}}

.premium {{
text-align:right;
}}

</style>

</head>

<body>

<div style="max-width:480px;margin:auto;">

<h3>溢价精算 Alpha</h3>

<p>更新时间: {now_str}</p>

{rows}

</div>

</body>

</html>
'''

    with open("index.html", "w", encoding="utf-8") as f:

        f.write(html)


if __name__ == "__main__":

    run()
```
