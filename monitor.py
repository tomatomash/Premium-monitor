import os
import requests
from datetime import datetime
import pytz

# ==================== 配置区 ====================
# 监控标的：{"国内代码": ["海外代码", "简称"]}
FUND_MAP = {
    "162411": ["XOP", "OilGas"], 
    "161129": ["XBI", "BioTech"],
    "160216": ["USO", "CrudeOil"],
}

# 粘贴你确认开启分享的表单链接
FORM_URL = "https://my.feishu.cn/share/base/form/shrcnaa8FdSQQvGYSKTeEhzXAlb"
WEBHOOK_URL = os.getenv('FEISHU_URL')
# ===============================================

def run_task():
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    print(f"🚀 开始执行任务... 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    form_api = FORM_URL.replace("/share/base/form/", "/share/base/query/form/api/submit/")
    
    for code, info in FUND_MAP.items():
        ticker, name = info[0], info[1]
        try:
            # 1. 获取国内场内价格
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            price = float(res_p.text.split(',')[3])
            
            # 2. 获取海外实时波动 (Change %)
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            # 计算海外标的相对于昨日收盘的涨跌幅
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 构造推送数据
            # 注意：这里的 field_id 必须与你多维表格中的列名完全一致
            payload = {
                "field_value_list": [
                    {"field_id": "Clock", "value": int(now.timestamp() * 1000)},
                    {"field_id": "Code", "value": code},
                    {"field_id": "Market", "value": price},
                    {"field_id": "Value", "value": round(ovs_change * 100, 2)}, # 这里存入海外波动的百分比
                    {"field_id": "Gap", "value": 0.02} # 预留位置
                ]
            }

            # 4. 提交数据
            sub_res = requests.post(form_api, json=payload)
            if sub_res.status_code == 200:
                print(f"✅ [{name}] 成功录入表格!")
            else:
                print(f"❌ [{name}] 录入失败: {sub_res.text}")
                
        except Exception as e:
            print(f"⚠️ [{name}] 处理出错: {e}")

if __name__ == "__main__":
    run_task()
