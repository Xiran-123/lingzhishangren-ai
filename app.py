from flask import Flask, render_template, request, jsonify, Response, session
import requests
import base64
import re
import json
import os
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # 安全密钥

# ====================== SiliconFlow API 配置 ======================
API_KEY = "sk-sdfaoxkrbsmmnueekypiqjgxtcrscmrmajrzvtdjkgnjieyi"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_NAME = "Pro/moonshotai/Kimi-K2.6"

# ====================== 访问密码配置 ======================
ACCESS_PASSWORD = "tongxin2024"  # 可以改成你想要的密码

# ====================== 知识库配置 ======================
KNOWLEDGE_FILE = "knowledge.txt"

def load_knowledge():
    """加载知识库内容"""
    try:
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                return f.read()
        else:
            return ""
    except Exception as e:
        print(f"知识库加载失败: {e}")
        return ""

# 加载知识库
knowledge_content = load_knowledge()

# ====================== 提示词配置 ======================
SYSTEM_PROMPT_FAST = f"""
你是灵智尚人，通信工程专家助手，请结合知识库快速、简洁地回答问题。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 如果知识库中有相关内容，优先使用知识库回答
2. 直接给出答案，不要啰嗦
3. 用简洁的语言表达
4. 控制回答长度
"""

SYSTEM_PROMPT_DEEP = f"""
你是灵智尚人，通信工程专家助手，请结合知识库深入、详细地回答问题。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 如果知识库中有相关内容，优先基于知识库详细回答
2. 详细分析问题，给出多个角度的解释
3. 如果需要，分点说明
4. 提供实用的建议或解决方案
5. 代码要加详细注释
6. 可以引用知识库中的具体案例
"""

# ====================== 路由 ======================
@app.route('/')
def index():
    # 检查是否已验证
    if session.get('authenticated'):
        return render_template('index.html')
    else:
        return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    password = data.get('password', '')
    
    if password == ACCESS_PASSWORD:
        session['authenticated'] = True
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': '密码错误'})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('authenticated', None)
    return jsonify({'success': True})

@app.route('/chat', methods=['POST'])
def chat_endpoint():
    # 检查是否已验证
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        image_data = data.get('image', '')
        mode = data.get('mode', 'fast')  # 'fast' 或 'deep'
        stream = data.get('stream', True)
        
        # 选择提示词
        system_prompt = SYSTEM_PROMPT_DEEP if mode == 'deep' else SYSTEM_PROMPT_FAST
        temperature = 0.85 if mode == 'deep' else 0.6
        max_tokens = 4000 if mode == 'deep' else 2000
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        # 处理图片
        if image_data:
            content = [
                {"type": "text", "text": user_message or "请描述这张图片的内容"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
            ]
        else:
            content = user_message
        
        if stream:
            # 流式输出
            return Response(
                stream_generator(headers, system_prompt, content, temperature, max_tokens),
                content_type='text/event-stream',
                headers={'Cache-Control': 'no-cache'}
            )
        else:
            # 非流式输出
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
            
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if "choices" in result and result["choices"]:
                    answer = result["choices"][0]["message"]["content"].strip()
                    answer = re.sub(r'\n{3,}', '\n\n', answer)
                    return jsonify({'response': answer})
                else:
                    return jsonify({'error': 'API返回格式错误'}), 500
            else:
                return jsonify({'error': f'API请求失败: {response.status_code} - {response.text}'}), 500
        
    except requests.exceptions.Timeout:
        return jsonify({'error': '请求超时，请稍后重试'}), 500
    except Exception as e:
        return jsonify({'error': f'请求出错: {str(e)}'}), 500

def stream_generator(headers, system_prompt, content, temperature, max_tokens):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=60)
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        json_data = json.loads(data)
                        if 'choices' in json_data and len(json_data['choices']) > 0:
                            delta = json_data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                    except:
                        pass
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@app.route('/reload-knowledge', methods=['POST'])
def reload_knowledge():
    """重新加载知识库"""
    global knowledge_content, SYSTEM_PROMPT_FAST, SYSTEM_PROMPT_DEEP
    knowledge_content = load_knowledge()
    
    # 更新提示词
    SYSTEM_PROMPT_FAST = f"""
你是通信工程专家助手，请结合知识库快速、简洁地回答问题。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 如果知识库中有相关内容，优先使用知识库回答
2. 直接给出答案，不要啰嗦
3. 用简洁的语言表达
4. 控制回答长度
"""

    SYSTEM_PROMPT_DEEP = f"""
你是通信工程专家助手，请结合知识库深入、详细地回答问题。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 如果知识库中有相关内容，优先基于知识库详细回答
2. 详细分析问题，给出多个角度的解释
3. 如果需要，分点说明
4. 提供实用的建议或解决方案
5. 代码要加详细注释
6. 可以引用知识库中的具体案例
"""
    
    return jsonify({'status': 'success', 'message': '知识库已重新加载'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
