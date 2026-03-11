import akshare as ak
import os
import requests
from datetime import datetime

# ================= 配置区 =================
# 你可以同时监控多个基金，格式：["代码1", "代码2"]
# 建议先填入一两个你最关心的，比如华宝油气(162411)或纳指LOF
MONITOR_LIST = ["162411", "161129"] 

# 预警阈值：0.015 代表 1.5%
THRESHOLD = 0.015 

# 飞书机器人设置的关键词（必须和你飞书机器人设置的一致）
KEYWORD = "预警" 
# ==========================================

def run_monitor():
    # 从 GitHub Secrets 中安全获取飞书 Webhook 地址
    webhook_url = os.getenv('FEISHU_URL')
    
    if not webhook_url:
        print("❌ 错误：未在 GitHub Secrets 中找到 FEISHU_URL，请检查设置。")
        return

    print(f"开始执行监控任务... 当前时间: {datetime.now()}")
    
    try:
        # 获取全量实时行情
        df = ak.fund_lof_spot_em()
        
        for code in MONITOR_LIST:
            # 筛选出目标基金
            fund_row = df[df['代码'] == code]
            
            if fund_row.empty:
                print(f"未找到基金代码: {code}")
                continue
            
            fund = fund_row.iloc[0]
            name = fund['名称']
            price = float(fund['最新价'])
            iopv = float(fund['参考净值'])
            premium = (price - iopv) / iopv
            
            print(f"检查中: {name} | 溢价率: {premium:.2%}")

            # 触发预警逻辑
            if premium > THRESHOLD:
                send_msg(webhook_url, name, code, premium, price, iopv)
                
    except Exception as e:
        print(f"监控运行出错: {e}")

def send_msg(url, name, code, premium, price, iopv):
    message = (
        f"🚨 {KEYWORD}\n"
        f"基金：{name} ({code})\n"
        f"当前溢价率：{premium:.2%}\n"
        f"场内价格：{price}\n"
        f"实时净值：{iopv}\n"
        f"推送时间：{datetime.now().strftime('%H:%M:%S')}"
    )
    
    payload = {
        "msg_type": "text",
        "content": {"text": message}
    }
    
    res = requests.post(url, json=payload)
    if res.status_code == 200:
        print(f"✅ {name} 预警已发送至飞书")
    else:
        print(f"❌ 飞书发送失败: {res.text}")

if __name__ == "__main__":
    run_monitor()
