import os
import requests
import json
from datetime import datetime, time
import pytz

# ==================== 配置区 ====================
FUND_MAP = {
    "162411": ["XOP", "OilGas"], 
    "161129": ["XBI", "BioTech"],
    "160216": ["USO", "CrudeOil"],
}

# 粘贴你确认开启分享的表单链接
FORM_URL = "https://my.feishu.cn/share/base/form/shrcnaa8FdSQQvGYSKTeEhzXAlb"
WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 
# ===============================================

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    
    # 直接构建提交接口
    form_api = FORM_URL.replace("/share/base/form/", "/share/base/query/form/api/submit/")
    
    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 1. 抓取数据
            res_gz = requests.get(f"https://fundgz.1234567.com.cn/js/{code}.js")
            last_nav = float(json.loads(res_gz.text.split('(')[1].split(')')[0])['dwjz'])
            
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            price = float(res_p.text.split(',')[3])
            
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            change = res_y.json()['chart']['result'][0]['meta']['regularMarketPrice'] / res_y.json()['chart']['result'][0]['meta']['previousClose']
            
            est_nav = last_nav * change
            arb_gap = (price - est_nav) / est_nav
            
            # 2. 构造载荷（直接使用你的列名作为 field_id，这是飞书表单的备选匹配逻辑）
            payload = {
                "field_value_list": [
                    {"field_id": "Clock", "value": int(now.timestamp() * 1000)},
                    {"field_id": "Code", "value": code},
                    {"field_id": "Market", "value": price},
                    {"field_id": "Value", "value": round(est_nav, 4)},
                    {"field_id": "Gap", "value": arb_gap}
                ]
            }

            # 3. 提交数据
            sub_res = requests.post(form_api, json=payload)
            if sub_res.status_code == 200:
                print(f"✅ [{name}] 成功录入表格! Gap: {arb_gap:.2%}")
            else:
                # 如果还是不行，打印出飞书返回的具体错误，方便我定位
                print(f"❌ [{name}] 录入失败，状态码: {sub_res.status_code}, 返回: {sub_res.text}")

            # 4. 2% 溢价预警 (北京时间 14:00-15:05)
            if arb_gap > THRESHOLD and time(14, 0) <= now.time() <= time(15, 5):
                alert_msg = f"🚨 GAP ALERT\nS: {code}\nA: {arb_gap:.2%}"
                requests.post(WEBHOOK_URL, json={"msg_type":"text","content":{"text":alert_msg}})
                
        except Exception as e:
            print(f"💥 运行出错: {e}")

if __name__ == "__main__":
    run_task()
