import akshare as ak
import os
import requests
import pandas as pd
from datetime import datetime

# ================= 配置区 =================
MONITOR_LIST = ["162411", "161129"] # 华宝油气, 标普生物
THRESHOLD = 0.01                # 调低到1%进行测试，确保能收到消息
KEYWORD = "预警" 
# ==========================================

def run_monitor():
    webhook_url = os.getenv('FEISHU_URL')
    if not webhook_url:
        print("❌ 错误：未设置 FEISHU_URL")
        return

    print(f"🚀 开始执行离线监控... 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # 使用 ak.fund_lof_spot_em() 的备选逻辑，显式指定字段
        # 如果这个接口在海外依然缺字段，代码会报错并进入 except 捕获
        df = ak.fund_lof_spot_em()
        
        # 如果 df 中没有“参考净值”，我们手动通过另一个接口补齐
        for code in MONITOR_LIST:
            fund_row = df[df['代码'] == code]
            if fund_row.empty: continue
            
            fund = fund_row.iloc[0]
            name = fund['名称']
            price = float(fund['最新价'])
            
            # 【关键优化】：如果东财没净值，尝试从新浪单独抓取该代码的实时 IOPV
            iopv = 0
            if '参考净值' in fund and fund['参考净值'] and float(fund['参考净值']) > 0:
                iopv = float(fund['参考净值'])
            else:
                # 备用方案：直接调用新浪的单个基金实时接口（含IOPV）
                try:
                    # 模拟新浪的单个查询请求
                    url = f"http://hq.sinajs.cn/list=sz{code}"
                    res = requests.get(url, headers={'Referer': 'http://finance.sina.com.cn'})
                    data = res.text.split(',')
                    # 新浪 SZ 类型接口：第 31 位通常是 IOPV
                    if len(data) > 31:
                        iopv = float(data[31])
                except:
                    print(f"⚠️ {name} 备用接口也失效")

            if iopv > 0:
                premium = (price - iopv) / iopv
                print(f"📊 {name}: 现价 {price} | 净值 {iopv} | 溢价 {premium:.2%}")
                
                if premium > THRESHOLD:
                    send_msg(webhook_url, name, code, premium, price, iopv)
            else:
                print(f"❌ {name} 无法获取有效净值数据")

    except Exception as e:
        print(f"🔥 监控运行异常: {str(e)}")

def send_msg(url, name, code, premium, price, iopv):
    message = (
        f"🚨 {KEYWORD}\n"
        f"基金：{name} ({code})\n"
        f"实时溢价：{premium:.2%}\n"
        f"现价：{price} | 净值：{iopv}\n"
        f"推送时间：{datetime.now().strftime('%H:%M:%S')}"
    )
    payload = {"msg_type": "text", "content": {"text": message}}
    requests.post(url, json=payload)

if __name__ == "__main__":
    run_monitor()
