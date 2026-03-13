import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化参数区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        d = res.json()['chart']['result'][0]['meta']
        return (d['regularMarketPrice'] / d['previousClose']) - 1
    except:
        return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    fx_change = get_market_data("CNH=F")
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # ---------------------------------------------------------
            # 轨道 A：深市 (16/15等) - 物理封箱，绝对不动
            # ---------------------------------------------------------
            if not code.startswith('5'):
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                p_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + asset_change * info['w']) * (1 + fx_change * 0.95)
                p1, p2 = (mp - nav) / nav, (mp - est_nav) / est_nav

            # ---------------------------------------------------------
            # 轨道 B：沪市 (5开头) - 终极修复，使用天天基金PC端接口
            # ---------------------------------------------------------
            else:
                nav = None
                # 尝试1：天天基金PC端接口，对沪市基金更稳定
                try:
                    url = f"https://fund.eastmoney.com/{code}.html"
                    res = requests.get(url, headers=HEADERS, timeout=5)
                    # 用正则匹配净值，格式如：<span class="fundDetail-totalNet">1.2345</span>
                    match = re.search(r'<span class="fundDetail-totalNet">([0-9.]+)</span>', res.text)
                    if match:
                        nav = float(match.group(1))
                        print(f"【沪市净值成功】{code} -> 天天基金PC端: {nav}")
                except Exception as e:
                    print(f"【沪市净值失败1】{code}: {e}")

                # 尝试2：东方财富基金净值接口
                if nav is None:
                    try:
                        em_url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
                        res = requests.get(em_url, headers=HEADERS, timeout=5)
                        match = re.search(r'^var fS_jz\s*=\s*([0-9.]+);', res.text, re.M)
                        if match:
                            nav = float(match.group(1))
                            print(f"【沪市净值成功】{code} -> 东方财富: {nav}")
                    except Exception as e:
                        print(f"【沪市净值失败2】{code}: {e}")

                # 尝试3：腾讯基金接口
                if nav is None:
                    try:
                        t_url = f"https://proxy.finance.qq.com/fundapi/v1/fund/nav?code={code}"
                        t_res = requests.get(t_url, headers=HEADERS, timeout=5).json()
                        nav = float(t_res['data']['nav']['nav'])
                        print(f"【沪市净值成功】{code} -> 腾讯: {nav}")
                    except Exception as e:
                        print(f"【沪市净值失败3】{code}: {e}")

                # 如果所有尝试都失败，直接抛出错误，而不是用1.0保底
                if nav is None:
                    raise ValueError(f"无法获取{code}的净值，跳过计算")

                # 实时价格
                p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                print(f"【沪市价格】{code} -> {mp}")

                # 计算（和深市完全一样）
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + asset_change * info['w']) * (1 + fx_change * 0.95)
                p1, p2 = (mp - nav) / nav, (mp - est_nav) / est_nav

            # 颜色
            color = "plus" if p2 > 0.02 else "minus"
            results.append({
                "code": code, "name": info["name"],
                "p1": p1, "p2": p2, "color": color
            })
            print(f"CHECK: {code} {info['name']} -> P1:{p1:.2%}, P2:{p2:.2%}")

        except Exception as e:
            print(f"ERROR: {code} 计算出错: {e}")
            continue  # 出错就跳过，不影响其他基金

    # 生成网页
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        .row{{display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #eee;font-family:sans-serif;}}
        .plus{{color:#cf1322;font-weight:bold;}}
        .minus{{color:#389e0d;}}
        .premium{{text-align:right;}}
    </style>
</head>
<body>
    <div style="max-width:480px;margin:auto;">
        <h3>溢价精算 Alpha</h3>
        <p>更新时间: {now_str}</p>
        {rows}
    </div>
</body>
</html>'''

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
