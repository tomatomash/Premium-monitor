import os
import requests
from datetime import datetime
import pytz

# ==================== 监控配置中心 ====================
FUND_CONFIG = {
    "162411": ["XOP",  "华宝油气"],
    "160216": ["USO",  "原油LOF"],
    "159509": ["NVDA", "纳指科技"],
    "501225": ["SOXX", "全球芯片"],
    "161129": ["XBI",  "生物科技"],
    "164906": ["KWEB", "中概互联"],
    "161125": ["IVV",  "标普500"],
    "513500": ["IVV",  "标普500ETF"],
    "161127": ["QQQ",  "纳指100"],
    "513100": ["QQQ",  "纳指ETF"],
    # --- 预留位：只要左边代码是 00000x，新逻辑会瞬间将其抹除 ---
    #"000001": ["SPY",  "预留01"],
    #"000010": ["ASML", "预留10"], 
    # 格式：国内基金代码 | 海外对标代码 | 自定义名称
    # 比如想看道指，把 000002 改成对应 LOF 代码
}

WEBHOOK_URL = os.getenv('FEISHU_URL')

def generate_html(data_list, update_time):
    """生成极简风格的仪表盘网页"""
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Alpha 溢价看板</title>
        <style>
            body {{ font-family: sans-serif; background: #f4f7f9; color: #333; display: flex; justify-content: center; padding: 20px; }}
            .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: 100%; max-width: 400px; }}
            h2 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; font-size: 18px; color: #007aff; }}
            .time {{ font-size: 12px; color: #888; margin-bottom: 15px; }}
            .item {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f9f9f9; }}
            .name {{ font-weight: 500; }}
            .change {{ font-family: monospace; font-weight: bold; }}
            .plus {{ color: #d20f39; }} .minus {{ color: #008000; }}
        </style>
        <meta http-equiv="refresh" content="60"> </head>
    <body>
        <div class="card">
            <h2>📊 Alpha 实时监控看板</h2>
            <div class="time">最后更新日期: {update_time}</div>
            {"".join(data_list)}
        </div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    now_str = now.strftime('%H:%M:%S')
    
    feishu_report = [f"通知：Alpha 溢价监控 ({now_str})", "---"]
    html_items = []
    
    for code, info in FUND_CONFIG.items():
        ticker, name = info
        try:
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", timeout=10)
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 格式化数据
            change_str = f"{ovs_change:+.2%}"
            color_class = "plus" if ovs_change >= 0 else "minus"
            
            # 存入飞书列表
            feishu_report.append(f"• {name} ({code}): {change_str}")
            # 存入HTML列表
            html_items.append(f'<div class="item"><span class="name">{name}</span><span class="change {color_class}">{change_str}</span></div>')
        except:
            feishu_report.append(f"• {name} ({code}): 获取失败")

    # 1. 发送飞书
    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={"msg_type": "text", "content": {"text": "\n".join(feishu_report)}})
    
    # 2. 生成本地 HTML 文件
    generate_html(html_items, now_str)

if __name__ == "__main__":
    run_task()
