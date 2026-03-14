import re, json, requests, pytz
from datetime import datetime

# ================= 完整基金配置 =================
FUND_CONFIG = {
    "501225": {"name": "全球芯片", "ticker": "SOXX", "w": 0.88},
    "160416": {"name": "石油基金", "ticker": "XOP", "w": 0.82},
    "161129": {"name": "原油基金", "ticker": "CL=F", "w": 0.95},
    "501018": {"name": "南方原油", "ticker": "CL=F", "w": 0.95},
    "160723": {"name": "嘉实原油", "ticker": "CL=F", "w": 0.90},
    "160644": {"name": "港美互联", "ticker": "KWEB", "w": 0.95},
    "161125": {"name": "标普500", "ticker": "SPY", "w": 0.98},
    "161128": {"name": "标普科技", "ticker": "XLK", "w": 0.98},
    "161116": {"name": "黄金主题", "ticker": "GC=F", "w": 0.99},
    "161126": {"name": "标普医疗", "ticker": "XLV", "w": 0.98},
    "161226": {"name": "白银基金", "ticker": "SLV", "w": 0.95},
    "501227": {"name": "弘德红利", "ticker": "SPY", "w": 0.90},
    "501099": {"name": "平安新兴", "ticker": "QQQ", "w": 0.90},
    "501082": {"name": "科创投资", "ticker": "QQQ", "w": 0.85},
    "501188": {"name": "添富核心", "ticker": "SPY", "w": 0.85},
    "501076": {"name": "创新动力", "ticker": "QQQ", "w": 0.85},
    "501096": {"name": "国联安科", "ticker": "QQQ", "w": 0.85},
    "501015": {"name": "财通升级", "ticker": "QQQ", "w": 0.85},
    "501022": {"name": "银华鑫盛", "ticker": "QQQ", "w": 0.85},
    "501001": {"name": "财通精选", "ticker": "QQQ", "w": 0.85},
}

# (此处保留你原有的 safe_get, get_market_change, get_fx, get_fund_estimate, get_em_nav, get_price, detect_type 函数不变)

def run():
    now = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    fx_change = get_fx()
    results = []

    for code, info in FUND_CONFIG.items():
        try:
            price = get_price(code)
            if not price: continue
            
            dwjz, gsz = get_fund_estimate(code)
            if not dwjz: dwjz = get_em_nav(code)
            if not dwjz: continue

            ftype = detect_type(dwjz, gsz)
            asset_change = get_market_change(info["ticker"])
            fx = 1 + fx_change if info["ticker"] != "GC=F" else 1
            
            est_nav = dwjz * (1 + asset_change * info["w"]) * fx
            if ftype == "QDII_LOF" and gsz: est_nav = gsz

            p1 = (price - dwjz) / dwjz
            p2 = (price - est_nav) / est_nav
            premium = (p1 + p2) / 2
            
            results.append({
                "code": code,
                "name": info["name"],
                "premium": premium,
                "color": "plus" if premium > 0.02 else "minus"
            })
        except Exception as e:
            print("ERROR", code, e)

    # 渲染部分保持不变...
