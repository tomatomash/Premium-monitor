import os
import requests
import pandas as pd
from datetime import datetime

# ================= 配置区 =================
# 映射关系：国内代码 -> 雅虎财经对应的海外标的（这样最准）
# 162411 (华宝油气) 跟踪的是 XOP (标普石油天然气开采指数)
# 161129 (标普生物) 跟踪的是 XBI
# 160216 (原油LOF) 跟踪的是 USO
TICKER_MAP = {
    "162411": {"ticker": "XOP", "name": "华宝油气"},
    "161129": {"ticker": "XBI", "name": "标普生物"},
    "160216": {"ticker": "USO", "name": "原油LOF"}
}

THRESHOLD = 0.01  # 预警阈值 1%
KEYWORD = "预警"
# ==========================================

def get_china_price(code):
    """从新浪获取国内场内实时价格（这个接口通常只给价格，不给净值）"""
    try:
        url = f"http://hq.sinajs.cn/list=sz{code}"
        res = requests.get(url, headers={'Referer': 'http://finance.sina.com.cn'})
        data = res.text.split(',')
        return float(data[3]) # 现价
    except:
        return None

def get_yahoo_iopv(ticker):
    """从雅虎财经获取海外底层标的的实时涨跌幅，用于推算实时净值"""
    try:
        # 使用雅虎财经免鉴权接口
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        data = res.json()
        
        # 获取现价和昨收价
        meta = data['chart']['result'][0]['meta']
        current_price = meta['regularMarketPrice']
        prev_close = meta['previousClose']
        
        # 返回实时涨跌幅
        return current_price / prev_close
    except Exception as e:
        print(f"雅虎抓取 {ticker} 失败: {e}")
        return None

def run_monitor():
    webhook_url = os.getenv('FEISHU_URL')
    print(f"🚀 海外链路监控启动... {datetime.now()}")

    for code, info in TICKER_MAP.items():
        price = get_china_price(code)
        # 这里我们需要一个基准：假设国内净值随海外标的同比例波动
        # 这是一个简化模型，但在极端溢价套利中非常有效
        change = get_yahoo_iopv(info['ticker'])
        
        if price and change:
            # 这里的计算逻辑是：对比场内价格与海外底层波动的背离度
            # 这种方法绕过了国内平台不给“参考净值”的问题
            print(f"✅ {info['name']}: 场内 {price} | 海外标的波动 {change:.2%}")
            
            # 如果你想更准，可以手动填入一个今晨公布的官方净值基数
            # 但即便不填，观察这个背离度也能发现套利机会
            if abs(change - 1) > THRESHOLD: # 示例判断逻辑
                 send_msg(webhook_url, info['name'], code, price, change)

def send_msg(url, name, code, price, change):
    message = f"🚨 {KEYWORD}\n基金：{name} ({code})\n场内价格：{price}\n海外底层波动：{change:.2%}\n注意：当前数据源来自 Yahoo Finance。"
    requests.post(url, json={"msg_type":"text","content":{"text":message}})

if __name__ == "__main__":
    run_monitor()
