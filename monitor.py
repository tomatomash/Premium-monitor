import os
import requests
import json
from datetime import datetime
import pytz

# ==================== 配置区 ====================
FUND_MAP = {
    "162411": ["XOP", "OilGas"], 
    "161129": ["XBI", "BioTech"],
    "160216": ["USO", "CrudeOil"],
}

# 这里填你那个确认开启了分享的表单链接
FORM_URL = "https://my.feishu.cn/share/base/form/shrcnaa8FdSQQvGYSKTeEhzXAlb"
WEBHOOK_URL = os.getenv('FEISHU_URL') # 你的群机器人链接
# ===============================================

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    print(f"🚀 开始任务: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 【核心修复】构造飞书表单的真实提交接口
    form_token = FORM_URL.split('/')[-1]
    submit_api = f"https://my.feishu.cn/share/base/query/form/api/submit/{form_token}"
    
    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 1. 获取国内现价
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            price = float(res_p.text.split(',')[3])
            
            # 2. 获取海外实时波动
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 构造填表数据 (必须匹配你表单里的字段名)
            # 注意：飞书表单提交的 payload 格式非常严苛
            payload = {
                "field_value_list": [
                    {"field_id": "Clock", "value": int(now.timestamp() * 1000)},
                    {"field_id": "Code", "value": code},
                    {"field_id": "Market", "value": str(price)},
                    {"field_id": "Value", "value": str(round(ovs_change * 100, 2))},
                    {"field_id": "Gap", "value": "0.02"} # 预设占位
                ]
            }

            # 4. 执行提交
            res = requests.post(submit_api, json=payload)
            
            if res.status_code == 200:
                print(f"✅ [{name}] 成功录入表格！海外涨跌: {ovs_change:.2%}")
            else:
                print(f"❌ [{name}] 失败: {res.status_code} - {res.text}")
                
        except Exception as e:
            print(f"💥 [{name}] 运行崩溃: {e}")

if __name__ == "__main__":
    run_task()
