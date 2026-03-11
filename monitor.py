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

FORM_URL = "https://my.feishu.cn/share/base/form/shrcnaa8FdSQQvGYSKTeEhzXAlb"
WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 
# ===============================================

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    
    # 1. 自动转换 API 链接
    form_api = FORM_URL.replace("/share/base/form/", "/share/base/query/form/api/submit/")
    # 获取表单元数据以匹配 ID
    meta_api = FORM_URL.replace("/share/base/form/", "/share/base/query/form/api/get/")
    
    try:
        meta_res = requests.get(meta_api).json()
        fields = meta_res['data']['form']['field_list']
        # 建立 名字 -> ID 的映射
        name_to_id = {f['title']: f['field_id'] for f in fields}
        print(f"✅ 成功匹配表单字段: {name_to_id}")
    except Exception as e:
        print(f"❌ 无法获取表单字段 ID: {e}")
        return

    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 抓取数据逻辑
            res_gz = requests.get(f"https://fundgz.1234567.com.cn/js/{code}.js")
            last_nav = float(json.loads(res_gz.text.split('(')[1].split(')')[0])['dwjz'])
            
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            price = float(res_p.text.split(',')[3])
            
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            change = res_y.json()['chart']['result'][0]['meta']['regularMarketPrice'] / res_y.json()['chart']['result'][0]['meta']['previousClose']
            
            est_nav = last_nav * change
            arb_gap = (price - est_nav) / est_nav
            
            # 2. 构造动态提交载荷
            payload = {"field_value_list": []}
            data_map = {
                "Clock": now.timestamp() * 1000,
                "Code": code,
                "Market": price,
                "Value": round(est_nav, 4),
                "Gap": arb_gap
            }
            
            for key, val in data_map.items():
                if key in name_to_id:
                    payload["field_value_list"].append({"field_id": name_to_id[key], "value": val})

            # 3. 提交
            sub_res = requests.post(form_api, json=payload)
            if sub_res.status_code == 200:
                print(f"🚀 [{name}] 录入成功！Gap: {arb_gap:.2%}")
            else:
                print(f"⚠️ [{name}] 录入失败: {sub_res.text}")

            # 4. 紧急预警
            if arb_gap > THRESHOLD and time(14, 0) <= now.time() <= time(15, 5):
                alert_msg = f"🚨 GAP ALERT\nS: {code}\nA: {arb_gap:.2%}\nCheck Alpha_Log."
                requests.post(WEBHOOK_URL, json={"msg_type":"text","content":{"text":alert_msg}})
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_task()
