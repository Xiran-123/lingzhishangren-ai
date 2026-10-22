import openai
from openai import OpenAI
from sympy import content
from torch.cpu import stream

API_KEY = "sk-qhsbsheiyrcvstiubovgpqecodjzayszeenfthehdaeekgbh"
client = OpenAI(
api_key=API_KEY,
base_url="https://api.siliconflow.cn/v1"
 )
# 新增：加载本地知识库
def get_kb():
    try:
        with open("knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "暂无知识库内容"
kb_content = get_kb()
SYSTEM_PROMPT = f"""
你是通信工程专家助手，请遵守以下核心原则：
【回答策略】
1. 用户问题第一：优先准确回答用户的直接问题
2. 知识库仅为参考：仅在相关知识时使用，绝不机械照搬
3. 回答必须实用：给出具体、可操作、有深度的解决方案
4.请合理运用知识库{kb_content}进行更加合理的回复

【专业范围】
1. 通信工程：网络、无线、光纤、基站、协议、故障排查
2. 代码调试：Python、网络配置、API、终端问题
3. 日常问题：电脑、手机、网络等常见问题

【回答格式】
- 复杂问题分步骤
- 关键点用🔹标记
- 代码用```包裹
- 保持自然对话感
"""
def chat_with_openai(use_input):
    try:
        response = client.chat.completions.create(
        model="Pro/zai-org/GLM-4.7",
        messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"参考知识库：{kb_content}\n用户问题：{use_input}"},
        ]
        )
        return (response.choices[0].message.content)
    except Exception as e:
        return f"请求出错{str(e)}"
if __name__ == "__main__":
        print("AI助手已经启动，输入exit退出对话")
        while True:
            word=input("You: ")
            if word.lower() == "exit":
                print("The dialogue was over")
                break
            result=chat_with_openai(word)
            print(f"AI: {result}")
