import os
import requests

def test_push():
    url = os.getenv('FEISHU_URL')
    print(f"正在尝试推送至 URL: {url[:30]}...") # 只打印前30位保护隐私
    
    payload = {
        "msg_type": "text",
        "content": {"text": "GitHub Actions 通路测试：如果你看到这条消息，说明配置成功！"}
    }
    
    response = requests.post(url, json=payload)
    print(f"返回状态码: {response.status_code}")
    print(f"返回内容: {response.text}")

if __name__ == "__main__":
    test_push()
