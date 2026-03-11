import os
import requests
from datetime import datetime
import pytz

# ==================== 监控池：纯净标的配置 ====================
# 格式: "国内代码": ["海外代码", "简称"]
FUND_CONFIG = {
    # 资源与油气
    "162411": ["XOP",  "华宝油气"],
    "160216": ["USO",  "原油LOF"],
    "160416": ["XLE",  "南方原油"],
    
    # 科技、芯片与纳指
    "159509": ["NVDA", "纳指科技"],
    "501225": ["SOXX", "全球芯片"],
    "161128": ["XLK",  "标普科技"],
    "161129": ["XBI",  "生物科技"],
    "164906": ["KWEB", "中概互联"],
    
    # 核心指数
    "161125": ["IVV",  "标普500"],
    "513500": ["IVV",  "标普500ETF"],
    "161127": ["QQQ",  "纳指100"],
    "513100": ["QQQ",  "纳指ETF"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 # 2% 溢价预警线
# =============================================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    # 必须包含关键词“通知”以通过飞书安全校验
    report = [
        "通知：📊 **【Alpha 套利实时监控】**",
        f"⏰ 抓取时刻: {now.strftime('%H:%M:%S')}",
        "💡 *计算依据: 场内现价 vs 海外 T-0 实时波动*",
        "---"
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name = info
        try:
            # 1. 国内实时价 (新浪接口)
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", 
                                 headers={'Referer': 'http://finance.sina.com.cn'},
                                 timeout=10)
            p_data = res_p.text.split(',')
            # 获取当前价
            price = float(p_data[3])
            
            # 2. 海外实时波动 (Yahoo Finance)
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", 
                                 headers={'User-Agent': 'Mozilla/5.0'},
                                 timeout=10)
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 预警图标逻辑
            is_hot = abs(ovs_change) >= THRESHOLD
            icon = "🚨" if is_hot else "✅"
            
            line = (
                f"{icon} **{name} ({code})**\n"
                f" ├ 海外波动: {ovs_change:+.2%}\n"
                f" ├ 场内现价: {price}\n"
                f" └ 状态: {'🔥溢价显著' if is_hot else '波动平稳'}"
            )
            report.append(line)
            
        except Exception as e:
            # 即使单条失败也不中断整体推送
            report.append(f"❌ {name} ({code}) 数据获取失败")

    # 最终汇总推送
    if WEBHOOK_URL:
        resp = requests.post(WEBHOOK_URL, json={
            "msg_type": "text", 
            "content": {"text": "\n".join(report)}
        })
        print(f"推送完成，飞书返回: {resp.text}")
    else:
        print("错误: 未找到 FEISHU_URL 环境变量")

if __name__ == "__main__":
    run_task()
