import os, re, requests, pytz, json
from datetime import datetime

# ==================== 配置区 ====================
# 优化点：161116 移除 GDX 干扰，直接挂钩 GC=F (黄金期货) 或 XAUUSD=X (现货)
FUND_CONFIG = {
    "161116": {"name": "易基黄金", "ticker": "GC=F", "w": 0.98}, # 调高权重，黄金基金仓位通常极高
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.95},
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.95},
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
CN_TZ = pytz.timezone('Asia/Shanghai')

def get_market_data(ticker):
    """获取标的实时涨跌幅，严格对比前一交易日收盘价"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=10)
        data = res.json()['chart']['result'][0]['meta']
        # 涨跌幅 = (当前价 - 昨收价) / 昨收价
        return (data['regularMarketPrice'] / data['previousClose']) - 1
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return 0.0

def run():
    now_str = datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    # 获取实时汇率变动 (离岸人民币)
    fx_change = get_market_data("CNH=F") 
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            # 1. 抓取净值 (T-1日官方公布净值)
            nav_res = requests.get(f"http://fundgz.1234567.com.cn/js/{code}.js", headers=HEADERS, timeout=5)
            nav = float(json.loads(re.search(r'jsonpgz\((.*?)\);', nav_res.text).group(1))['dwjz'])
            
            # 2. 抓取场内实时价格
            prefix = "sh" if code.startswith(('5', '6')) else "sz"
            price_res = requests.get(f"http://qt.gtimg.cn/q={prefix}{code}", headers=HEADERS, timeout=5)
            mp = float(price_res.text.split('~')[3])

            # 3. 计算海外标的实时波动
            us_change = get_market_data(info['ticker'])

            # --- 核心算法优化区 ---
            # P1: 静态溢价率 (直接对比昨天净值)
            p1 = (mp - nav) / nav
            
            # P2: 动态溢价率 (考虑汇率和海外资产波动的预估净值)
            # 预估净值 = 昨净值 * (1 + (资产涨幅 + 汇率涨幅) * 仓位权重)
            # 注意：汇率涨幅需根据内外盘关系微调，此处取 CNH=F 变动方向
            est_nav = nav * (1 + (us_change + fx_change) * info['w'])
            p2 = (mp - est_nav) / est_nav
            # ----------------------

            results.append({
                "code": code, 
                "name": info['name'], 
                "p1": p1, 
                "p2": p2,
                "color": "plus" if p2 > 0.02 else "minus" # 只有动态溢价 > 2% 才标红
            })
            print(f"DEBUG: {info['name']} 计算完成. P1={p1:.2%}, P2={p2:.2%}")
        except Exception as e:
            print(f"ERROR: {code} 计算失败: {e}")
            continue

    # 4. 生成 HTML (保持原格式)
    rows = "".join([f'<div class="row"><div><b>{i["name"]}</b><br>{i["code"]}</div><div class="premium {i["color"]}">{i["p1"]:.2%} ~ {i["p2"]:.2%}</div></div>' for i in results])
    html = f'<!DOCTYPE html><html><head><meta charset="UTF-8"><style>.row{{display:flex;justify-content:space-between;padding:10px;border-bottom:1px solid #eee;}}.plus{{color:red;}}.minus{{color:green;}}</style></head><body><h3>Alpha 监控 (优化版)</h3><p>更新时间: {now_str}</p>{rows}</body></html>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    run()
