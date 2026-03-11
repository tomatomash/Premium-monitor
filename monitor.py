import akshare as ak
import os
import requests
from datetime import datetime

MONITOR_LIST = ["162411", "161129"] 
THRESHOLD = 0.015 
KEYWORD = "预警" 

def run_monitor():
    webhook_url = os.getenv('FEISHU_URL')
    if not webhook_url:
        print("❌ 错误：未设置 FEISHU_URL")
        return

    try:
        # 尝试获取数据
        df = ak.fund_lof_spot_em()
        
        # 自动识别“参考净值”所在的列（兼容不同平台的叫法）
        # 有些叫 '参考净值', 有些叫 'IOPV', 有些叫 '实时估值'
        possible_cols = ['参考净值', 'IOPV', '实时估值', '净值']
        val_col = next((c for c in possible_cols if c in df.columns), None)
        
        if not val_col:
            print(f"❌ 错误：找不到净值列。当前可选列有: {list(df.columns)}")
            return

        for code in MONITOR_LIST:
            fund_row = df[df['代码'] == code]
            if fund_row.empty:
                print(f"未找到代码: {code}")
                continue
            
            fund = fund_row.iloc[0]
            name = fund['名称']
            price = float(fund['最新价'])
            iopv = float(fund[val_col]) # 使用自动识别的列名
            
            if iopv == 0 or iopv is None:
                print(f"⚠️ {name} 净值为0，跳过计算")
                continue
                
            premium = (price - iopv) / iopv
            print(f"检查: {name} | 溢价率: {premium:.2%}")

            # 发送逻辑（即便没达标，你也可以先改成 > -1 来测试飞书是否通畅）
            if premium > THRESHOLD:
                send_msg(webhook_url, name, code, premium, price, iopv)
                
    except Exception as e:
        print(f"监控运行异常: {str(e)}")

def send_msg(url, name, code, premium, price, iopv):
    message = f"🚨 {KEYWORD}\n基金：{name} ({code})\n溢价率：{premium:.2%}\n现价：{price}\n参考值：{iopv}"
    payload = {"msg_type": "text", "content": {"text": message}}
    requests.post(url, json=payload)

if __name__ == "__main__":
    run_monitor()
