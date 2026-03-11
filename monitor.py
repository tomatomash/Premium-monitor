import os
import requests
import json
from datetime import datetime
import pytz

# ==================== 配置区 ====================
WEBHOOK_URL = os.getenv('FEISHU_URL')

# 监控配置：{"国内代码": ["海外代码", "简称"]}
FUND_MAP = {
    "162411": ["XOP", "华宝油气"], 
    "161129": ["XBI", "生物科技"],
    "160216": ["USO", "原油LOF"],
}

THRESHOLD = 0.02  # 2% 阈值标记
# ===============================================

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    
    report_lines = [f"📊 【Alpha 监控报告】", f"⏰ 推送时间: {now.strftime('%H:%M:%S')}", ""]
    
    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 1. 获取国内 T-0 实时场内价格 (Sina)
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            p_data = res_p.text.split(',')
            price = float(p_data[3])
            p_time = p_data[31] # 国内实时行情时间

            # 2. 获取海外最新波动 (Yahoo Finance)
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            y_json = res_y.json()['chart']['result'][0]
            meta = y_json['meta']
            
            # 计算海外相对于昨日收盘的波动 (T-0 实时波动)
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            ovs_time = datetime.fromtimestamp(meta['regularMarketTime'], tz).strftime('%H:%M')

            # 3. 计算估算溢价率 (简易模型：假设国内收盘已反映 T-1 净值，此波动为 T-0 增量)
            # 注意：此溢价率指示场内价格相对于海外实时波动的偏差
            est_gap = (price / (1 + ovs_change)) / price - 1 # 简易逻辑示意
            # 更直观的显示：直接显示场内价格与海外实时表现的背离度
            
            status_icon = "🚨" if abs(ovs_change) >= THRESHOLD else "✅"
            
            line = (
                f"{status_icon} **{name} ({code})**\n"
                f" ├ 场内现价: {price} (T-0 {p_time})\n"
                f" ├ 海外波动: {ovs_change:+.2%} (T-0 {ovs_time})\n"
                f" └ 溢价预警: {'超过2%!' if abs(ovs_change) >= THRESHOLD else '正常'}"
            )
            report_lines.append(line)
            
        except Exception as e:
            report_lines.append(f"❌ {name} 数据获取失败: {e}")

    # 合并成一条消息发送
    full_message = "\n".join(report_lines)
    requests.post(WEBHOOK_URL, json={"msg_type": "text", "content": {"text": full_message}})
    print("✅ 全景报告已发送")

if __name__ == "__main__":
    run_task()
