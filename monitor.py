import os
import requests
from datetime import datetime
import pytz

# ==================== 标的配置中心 ====================
# 格式: "国内代码": ["海外代码", "简称", "限额", "申购方式"]
FUND_CONFIG = {
    "162411": ["XOP",  "华宝油气", "暂停", "场内"],
    "161129": ["XBI",  "生物科技", "暂停", "场内"],
    "160216": ["USO",  "原油LOF", "暂停", "场内"],
    "501225": ["SOXX", "全球芯片", "暂停", "场内"],
    "160644": ["KWEB", "港美互联", "10W", "场内"],
    "161128": ["XLK",  "标普科技", "10元", "场内"],
    "161125": ["IVV",  "标普500", "10元", "场内"],
}

WEBHOOK_URL = os.getenv('FEISHU_URL')
THRESHOLD = 0.02 # 2% 预警线
# =====================================================

def run_task():
    sh_tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(sh_tz)
    
    report_lines = [
        "📊 **【Alpha 溢价全景监控】**",
        f"⏰ 推送时刻: {now.strftime('%H:%M:%S')}",
        "💡 *海外波动基于美东时间 (T-0 04:00 = 北京凌晨)*",
        ""
    ]
    
    for code, info in FUND_CONFIG.items():
        ticker, name, limit, method = info
        try:
            # 1. 国内实时价 (T-0)
            res_p = requests.get(f"http://hq.sinajs.cn/list=sz{code}", headers={'Referer': 'http://finance.sina.com.cn'})
            p_data = res_p.text.split(',')
            price, p_time = float(p_data[3]), p_data[31]

            # 2. 海外实时波动 (T-0)
            res_y = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", headers={'User-Agent': 'Mozilla/5.0'})
            meta = res_y.json()['chart']['result'][0]['meta']
            ovs_change = (meta['regularMarketPrice'] / meta['previousClose']) - 1
            
            # 3. 格式化输出
            alert_tag = "🚨" if abs(ovs_change) >= THRESHOLD else "✅"
            
            line = (
                f"{alert_tag} **{name} ({code})**\n"
                f" ├ 溢价估算: {ovs_change:+.2%} (参考限额: {limit})\n"
                f" ├ 场内现价: {price} (实时 {p_time})\n"
                f" └ 方式: {method}申购 | 状态: {'⚠️偏高' if abs(ovs_change) >= THRESHOLD else '正常'}"
            )
            report_lines.append(line)
            
        except Exception as e:
            report_lines.append(f"❌ {name} ({code}) 数据获取异常")

    # 推送
    requests.post(WEBHOOK_URL, json={
        "msg_type": "text", 
        "content": {"text": "\n".join(report_lines)}
    })

if __name__ == "__main__":
    run_task()
