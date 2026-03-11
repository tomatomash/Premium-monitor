import os
import requests
from datetime import datetime
import pytz

# ==================== 监控池：全量套利标的 ====================
# 格式: "国内代码": ["海外代码", "简称"]
FUND_CONFIG = {
    # --- 油气与资源类 ---
    "162411": ["XOP",  "华宝油气"],
    "160216": ["USO",  "原油LOF"],
    "162719": ["XOP",  "广发油气"],
    "160416": ["XLE",  "南方原油"],
    
    # --- 科技、芯片与医药 ---
    "501225": ["SOXX", "全球芯片"],
    "161128": ["XLK",  "标普科技"],
    "161129": ["XBI",  "生物科技"],
    "159509": ["NVDA", "纳指科技"], # 增加热门标的
    "164906": ["KWEB", "中概互联"],
    
    # --- 核心指数类 ---
    "161125": ["IVV",  "标普500"],
    "513500": ["IVV",  "标普500ETF"],
    "160644": ["KWEB", "港美互联"],
    "161127": ["QQQ",  "纳指100"],
    "513100": ["QQQ",  "纳指ETF"],
    "159941": ["QQQ",  "纳指LOF"],
    
    # --- 恒生与黄金 ---
    "164701": ["700.HK", "添富恒生"], # 港股对标
    "160717": ["HSI",    "嘉实恒生"],
    "164703": ["GLD",    "添富黄金"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 # 2% 溢价预警线
# ===============================================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    # 消息头部
    report = [
        "📊 **【Alpha 套利实时全景图】**",
        f"⏰ 抓取时刻: {now.strftime('%H:%M:%S')}",
        "💡 *计算依据: 场内现价 vs 海外 T-0 实时波动*",
        "---"
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name = info
        try:
            # 1. 国内实时价 (新浪接口)
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            p_data = res_p.text.split(',')
            price, p_time = float(p_data[3]), p_data[31]

            # 2. 海外实时波动 (Yahoo Finance)
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 视觉逻辑
            is_hot = abs(ovs_change) >= THRESHOLD
            alert_icon = "🚨" if is_hot else "🔹"
            
            line = (
                f"{alert_icon} **{name} ({code})**\n"
                f" ├ 海外波动: {ovs_change:+.2%} (T-0 04:00)\n"
                f" ├ 场内现价: {price} ({p_time})\n"
                f" └ 状态: {'🔥溢价显著' if is_hot else '波澜不惊'}"
            )
            report.append(line)
            
        except Exception:
            report.append(f"❌ {name} ({code}) 数据获取超时")

    # 合并为一条消息推送至机器人
    requests.post(WEBHOOK_URL, json={
        "msg_type": "text", 
        "content": {"text": "\n".join(report)}
    })

if __name__ == "__main__":
    run_task()
