import os, re, requests, pytz, json
from datetime import datetime

# ==================== 固化参数区 ====================
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.99},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
    "501018": {"name": "南方原油LOF", "ticker": "CL=F", "w": 0.95},
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
            # =========================================================
            # 轨道 A：深市 (16/15等) - 物理封箱，绝对不动
            # =========================================================
            if not code.startswith('5'):
                # 净值：天天基金接口（深市专用）
                nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
                nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
                # 价格：腾讯行情（深市专用）
                p_res = requests.get(f"http://qt.gtimg.cn/q=sz{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                # 计算
                asset_change = get_market_data(info['ticker'])
                est_nav = nav * (1 + asset_change * info['w']) * (1 + fx_change * 0.95)
                p1, p2 = (mp - nav) / nav, (mp - est_nav) / est_nav

            # =========================================================
            # 轨道 B：沪市 (5开头) - 绝对分离，彻底换新源
            # =========================================================
            else:
                nav = None
                # 尝试1：九方智投基金接口（沪市专用，Actions下更稳定）
                try:
                    url = f"https://fund.9fzt.com/api/fund/nav?code={code}"
                    res = requests.get(url, headers=HEADERS, timeout=10)
                    data = res.json()
                    nav = float(data['nav'])
                    print(f"【沪市净值成功】{code} -> 九方智投: {nav}")
                except Exception as e:
                    print(f"【沪市净值失败1】{code}: {e}")

                # 尝试2：金融界基金接口（沪市专用）
                if nav is None:
                    try:
                        url = f"https://fund.jrj.com.cn/archives/{code}.shtml"
                        res = requests.get(url, headers=HEADERS, timeout=10)
                        match = re.search(r'单位净值.*?([0-9.]+)元', res.text)
                        if match:
                            nav = float(match.group(1))
                            print(f"【沪市净值成功】{code} -> 金融界: {nav}")
                    except Exception as e:
                        print(f"【沪市净值失败2】{code}: {e}")

                # 尝试3：天天基金备用接口（沪市专用，换路径）
                if nav is None:
                    try:
                        url = f"https://fund.1234567.com.cn/f10/{code}.html"
                        res = requests.get(url, headers=HEADERS, timeout=10)
                        match = re.search(r'单位净值.*?([0-9.]+)元', res.text)
                        if match:
                            nav = float(match.group(1))
                            print(f"【沪市净值成功】{code} -> 天天基金备用: {nav}")
                    except Exception as e:
                        print(f"【沪市净值失败3】{code}: {e}")

                # 如果所有尝试都失败，直接抛出错误，不使用保底值
                if nav is None:
                    raise ValueError(f"无法获取{code}的净值，跳过计算")

                # 价格：沪市专用腾讯行情
                p_res = requests.get(f"http://qt.gtimg.cn/q=sh{code}", headers=HEADERS, timeout=5)
                mp = float(p_res.text.split('~')[3])
                print(f"【沪市价格】{code} -> {mp}")

                # 计算：沪市独立公式，和深市对齐但代码分离
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
