import os
import requests
from datetime import datetime, time
import pytz

# ==================== 自动化配置数据库 ====================
# 格式: "国内代码": ["海外标的Ticker", "英文简称"]
FUND_MAP = {
    "162411": ["XOP", "OilGas"], 
    "161129": ["XBI", "BioTech"],
    "160216": ["USO", "CrudeOil"],
}

# 粘贴你刚创建好的【表单分享链接】
FORM_URL = "https://my.feishu.cn/share/base/form/shrcnaa8FdSQQvGYSKTeEhzXAlb"
WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 
# =======================================================

def get_last_nav(code):
    """自动获取该基金最新的官方净值数据"""
    try:
        url = f"https://fundgz.1234567.com.cn/js/{code}.js"
        res = requests.get(url)
        # 解析返回的 jsonp 数据
        import json
        content = res.text.split('(')[1].split(')')[0]
        data = json.loads(content)
        return float(data['dwjz']) # 返回单位净值
    except:
        return None

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    
    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 1. 自动抓取昨日官方净值
            last_nav = get_last_nav(code)
            if not last_nav: continue
            
            # 2. 获取实时行情
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            price = float(res_p.text.split(',')[3])
            
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            change = meta['regularMarketPrice'] / meta['previousClose']
            
            # 3. 计算
            est_nav = last_nav * change
            arb_gap = (price - est_nav) / est_nav
            
            # 4. 自动填表 (向表单提交数据)
            form_api = FORM_URL.replace("/share/base/form/", "/share/base/query/form/api/submit/")
            payload = {
                "field_value_list": [
                    {"field_id": "Clock", "value": now.timestamp() * 1000},
                    {"field_id": "Code", "value": code},
                    {"field_id": "Market", "value": price},
                    {"field_id": "Value", "value": round(est_nav, 4)},
                    {"field_id": "Gap", "value": arb_gap}
                ]
            }
            requests.post(form_api, json=payload)
            print(f"[{name}] 数据已录入表格")

            # 5. 下午收盘前一小时 + 溢价 > 2% 触发飞书通知
            if arb_gap > THRESHOLD and time(14, 0) <= now.time() <= time(15, 5):
                alert_msg = f"🚨 GAP ALERT\nS: {code}\nA: {arb_gap:.2%}\nCheck Alpha_Log Now."
                requests.post(WEBHOOK_URL, json={"msg_type":"text","content":{"text":alert_msg}})
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_task()
