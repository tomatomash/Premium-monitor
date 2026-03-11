import os
import requests
from datetime import datetime
import pytz

# ==================== 配置区 ====================
# 填入你截图里那个 BOT 的 Webhook 地址
WEBHOOK_URL = os.getenv('FEISHU_URL') 

FUND_MAP = {
    "162411": ["XOP", "华宝油气"], 
    "161129": ["XBI", "生物科技"],
    "160216": ["USO", "原油LOF"],
}

# 触发预警的阈值（比如海外涨跌幅度超过 1.5% 时提醒）
ALERT_THRESHOLD = 0.015 
# ===============================================

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    print(f"🚀 监控启动: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 1. 获取国内场内价格 (来自新浪，非常稳定)
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            price = float(res_p.text.split(',')[3])
            
            # 2. 获取海外底层标的波动 (来自 Yahoo Finance)
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 预警逻辑：如果海外波动较大，发送群消息
            if abs(ovs_change) >= ALERT_THRESHOLD:
                msg = (
                    f"🚨 【套利预警】\n"
                    f"基金: {name} ({code})\n"
                    f"场内现价: {price}\n"
                    f"海外底层波动: {ovs_change:.2%}\n"
                    f"⏰ 时间: {now.strftime('%H:%M:%S')}"
                )
                requests.post(WEBHOOK_URL, json={"msg_type": "text", "content": {"text": msg}})
                print(f"✅ [{name}] 预警已发送至群聊")
            else:
                print(f"😴 [{name}] 波动较小 ({ovs_change:.2%})，保持静默")
                
        except Exception as e:
            print(f"⚠️ [{name}] 处理时出错: {e}")

if __name__ == "__main__":
    run_task()
