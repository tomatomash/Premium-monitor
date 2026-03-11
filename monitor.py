import os
import requests
from datetime import datetime
import pytz

# ==================== 监控池：常用套利标的一览 ====================
# 格式: "国内代码": ["海外代码", "简称", "限额/状态", "方式"]
FUND_CONFIG = {
    # --- 油气与资源类 ---
    "162411": ["XOP",  "华宝油气", "暂停", "场内"],
    "160216": ["USO",  "原油LOF", "暂停", "场内"],
    "162719": ["XOP",  "广发油气", "2000元", "场外"],
    "160416": ["XLE",  "南方原油", "暂停", "场内"],
    
    # --- 科技与半导体 ---
    "501225": ["SOXX", "全球芯片", "暂停", "场内"],
    "161128": ["XLK",  "标普科技", "10元", "场内"],
    "161129": ["XBI",  "生物科技", "暂停", "场内"],
    "164906": ["CNCR", "中国互联", "暂停", "场内"],
    
    # --- 指数与互联网 ---
    "161125": ["IVV",  "标普500",  "10元", "场内"],
    "160644": ["KWEB", "港美互联", "10W", "场内"],
    "164701": ["HKB",  "添富恒生", "正常", "场内"],
    "160717": ["HSI",  "嘉实恒生", "正常", "场内"],
    "161127": ["QQQ",  "标普信息", "100元", "场内"],
    
    # --- 黄金与另类 ---
    "164703": ["GLD",  "添富黄金", "正常", "场内"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 # 2% 强提醒阈值
# ===============================================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    report = [
        "📊 **【Alpha 套利全景监控 - 旗舰版】**",
        f"⏰ 推送时刻: {now.strftime('%H:%M:%S')}",
        "💡 *波动说明: 美东收盘 T-0 数据 (凌晨04:00)*",
        "---"
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name, limit, method = info
        try:
            # 1. 抓取国内实时价
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            p_data = res_p.text.split(',')
            price, p_time = float(p_data[3]), p_data[31]

            # 2. 抓取海外实时波动
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 组装逻辑
            alert = "🚨" if abs(ovs_change) >= THRESHOLD else "🔹"
            
            line = (
                f"{alert} **{name} ({code})**\n"
                f" ├ 溢价估算: {ovs_change:+.2%} | 限额: {limit}\n"
                f" ├ 场内现价: {price} ({p_time})\n"
                f" └ 方式: {method} | 建议: {'🔥机会' if abs(ovs_change) >= THRESHOLD else '观察'}"
            )
            report.append(line)
            
        except:
            report.append(f"❌ {name} ({code}) 接口超时")

    # 一次性推送全量信息
    requests.post(WEBHOOK_URL, json={
        "msg_type": "text", 
        "content": {"text": "\n".join(report)}
    })

if __name__ == "__main__":
    run_task()
