import requests
import re
import time
import os
import sys
from typing import List, Dict, Tuple

# ====================== 配置区 ======================
API_KEY = "sk-sdfaoxkrbsmmnueekypiqjgxtcrscmrmajrzvtdjkgnjieyi"
MODEL_LIST = [
    "Pro/moonshotai/Kimi-K2.6",  # 首选模型
    "Qwen/Qwen2.5-14B-Instruct",  # 备选模型，风格一致
]
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
KNOWLEDGE_FILE = r"D:\PythonProject3\knowledge.txt"


# ====================== 修复终端输入回显 ======================
def fix_terminal_echo():
    try:
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-10)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004 | 0x0002)
        else:
            os.system("stty echo")
    except:
        pass


# ====================== 精简高效的提示词 ======================
SYSTEM_PROMPT = """
你是通信工程专家助手，请遵守以下核心原则：

【回答策略】
1. 用户问题第一：优先准确回答用户的直接问题
2. 知识库仅为参考：仅在相关知识时使用，绝不机械照搬
3. 回答必须实用：给出具体、可操作、有深度的解决方案

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


# ====================== 智能知识库检索 ======================
def load_knowledge() -> List[str]:
    """加载知识库"""
    if not os.path.exists(KNOWLEDGE_FILE):
        return []
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []


def should_use_knowledge(question: str) -> Tuple[bool, List[str]]:
    """
    智能判断是否使用知识库
    返回：(是否使用, 相关知识点列表)
    """
    knowledge = load_knowledge()
    if not knowledge:
        return False, []

    # 扩展的专业关键词（更全面）
    pro_keywords = [
        # 核心通信概念
        "通信", "网络", "信号", "无线", "有线", "移动", "电信", "联通",
        # 网络技术
        "路由器", "交换机", "防火墙", "网关", "DNS", "DHCP", "IP", "MAC",
        "子网", "掩码", "VLAN", "VPN", "WAN", "LAN", "WLAN", "WiFi", "Wi-Fi",
        # 无线通信
        "基站", "天线", "频段", "频率", "信道", "带宽", "速率", "吞吐量",
        "延时", "延迟", "丢包", "抖动", "信号强度", "覆盖", "干扰",
        "2G", "3G", "4G", "5G", "LTE", "NR", "GSM", "CDMA", "WCDMA",
        # 光纤传输
        "光纤", "光缆", "光猫", "光衰", "光功率", "分光器", "OLT", "ONU",
        "PON", "EPON", "GPON", "光模块", "SFP", "单模", "多模",
        # 通信协议
        "TCP", "UDP", "HTTP", "HTTPS", "FTP", "SSH", "Telnet", "SNMP",
        "ICMP", "ARP", "RIP", "OSPF", "BGP", "MPLS", "QoS",
        # 性能指标
        "速率", "带宽", "时延", "抖动", "丢包率", "可用性", "可靠性",
        "吞吐量", "误码率", "信噪比", "SINR", "RSRP", "RSRQ", "CQI",
        # 故障排查
        "故障", "问题", "错误", "异常", "排查", "诊断", "修复", "解决",
        "不通", "断开", "连接失败", "无法上网", "慢", "卡顿", "掉线",
        # 实训实操
        "实训", "实验", "实操", "操作", "配置", "调试", "设置", "安装",
        "接线", "焊接", "测量", "测试", "验证", "验收", "报告",
        # 计算题
        "计算", "公式", "定理", "定律", "原理", "香农", "奈奎斯特", "傅里叶",
        "调制", "解调", "编码", "解码", "压缩", "加密", "解密",
        # 行业术语
        "核心网", "接入网", "承载网", "传输网", "数据网", "语音网", "视频网",
        "物联网", "工业互联网", "车联网", "智慧城市", "云计算", "边缘计算",
        "切片", "虚拟化", "NFV", "SDN", "云网", "算力网络",
        # 设备厂商
        "华为", "中兴", "烽火", "新华三", "思科", "爱立信", "诺基亚",
        # 岗位相关
        "网优", "网规", "运维", "工程", "施工", "监理", "设计", "规划"
    ]

    # 排除的关键词（这些不触发知识库）
    exclude_keywords = [
        "你好", "谢谢", "再见", "退出", "help", "帮助", "介绍", "谁",
        "天气", "时间", "日期", "笑话", "故事", "闲聊", "聊天"
    ]

    question_lower = question.lower()

    # 检查排除关键词
    for word in exclude_keywords:
        if word in question_lower:
            return False, []

    # 检查是否包含专业关键词
    pro_match_count = 0
    for keyword in pro_keywords:
        if keyword.lower() in question_lower:
            pro_match_count += 1
            if pro_match_count >= 1:  # 至少匹配1个就认为是专业问题
                # 检索相关知识
                related = []
                for line in knowledge:
                    line_lower = line.lower()
                    # 计算相似度：共享关键词数量
                    shared_words = 0
                    for kw in pro_keywords:
                        if kw.lower() in line_lower and kw.lower() in question_lower:
                            shared_words += 1
                    if shared_words > 0:
                        related.append(line)

                # 如果没有找到相关，但确实是专业问题，就返回全部知识库用于参考
                if not related and pro_match_count >= 2:
                    return True, knowledge[:5]  # 返回前5条

                return True, related[:3]  # 最多返回3条

    return False, []


# ====================== 优化的回答生成 ======================
def generate_answer(user_question: str, use_knowledge: bool, knowledge_refs: List[str]) -> str:
    """
    生成更好的回答
    """
    messages = []

    if use_knowledge and knowledge_refs:
        # 使用知识库的专业回答
        knowledge_text = "\n".join([f"{i + 1}. {ref}" for i, ref in enumerate(knowledge_refs)])
        system_content = f"""{SYSTEM_PROMPT}

【当前问题】{user_question}

【相关知识点参考】
{knowledge_text}

请基于以上知识点，但不要照搬原文，用自己的话深入浅出地回答问题。
如果知识点不相关或不完整，请基于你的专业知识回答。"""
    else:
        # 不使用知识库的通用回答
        system_content = f"""{SYSTEM_PROMPT}

【当前问题】{user_question}

请基于你的专业知识和技术经验，给出具体、实用的回答。"""

    messages.append({"role": "system", "content": system_content})
    messages.append({"role": "user", "content": user_question})

    return messages


# ====================== 动态调整模型参数 ======================
def get_model_params(question: str) -> Dict:
    """根据问题类型动态调整参数"""
    # 检测问题复杂度
    question_lower = question.lower()

    # 复杂问题（长问题、多关键词、需要详细解释）
    is_complex = (
            len(question) > 50 or
            any(word in question_lower for word in ["如何", "怎么", "为什么", "原因", "步骤", "方法"]) or
            question_lower.count('?') + question_lower.count('？') > 1
    )

    # 技术问题
    is_technical = any(word in question_lower for word in ["代码", "python", "调试", "报错", "安装", "配置"])

    if is_complex:
        return {
            "temperature": 0.7,  # 中等温度，平衡创造性和准确性
            "max_tokens": 4000,
            "top_p": 0.9,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1
        }
    elif is_technical:
        return {
            "temperature": 0.8,  # 稍高温度，代码生成需要创造性
            "max_tokens": 3000,
            "top_p": 0.95,
            "presence_penalty": 0,
            "frequency_penalty": 0
        }
    else:
        return {
            "temperature": 0.9,  # 高温度，对话更自然
            "max_tokens": 2000,
            "top_p": 1.0,
            "presence_penalty": 0,
            "frequency_penalty": 0
        }


# ====================== 主对话函数 ======================
def chat():
    fix_terminal_echo()

    print("=" * 60)
    print("🤖 智能通信助手（增强版）")
    print("📌 支持：通信工程 | 网络技术 | 代码调试 | 日常问题")
    print("💡 提示：输入「知识库」查看内容，输入「帮助」获取使用指南")
    print("=" * 60)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    # 存储对话历史（但限制长度）
    conversation_history = []
    MAX_HISTORY = 6  # 最多保存3轮对话（6条消息）

    while True:
        try:
            print("\n" + "─" * 40)
            user_input = input("您：").strip()

            if not user_input:
                continue

            # 退出命令
            if user_input.lower() in ["exit", "退出", "quit", "bye", "再见"]:
                print("\n✅ 对话结束，再见！")
                break

            # 特殊命令
            if user_input.lower() in ["知识库", "查看知识库", "显示知识库"]:
                knowledge = load_knowledge()
                if knowledge:
                    print(f"\n📚 知识库内容（共{len(knowledge)}条）：")
                    print("=" * 60)
                    for i, item in enumerate(knowledge[:20], 1):  # 只显示前20条
                        print(f"{i:2d}. {item}")
                    if len(knowledge) > 20:
                        print(f"... 还有{len(knowledge) - 20}条未显示")
                else:
                    print("❌ 知识库为空或加载失败")
                continue

            if user_input.lower() in ["帮助", "help", "指南"]:
                print("""
🔧 使用指南：
1. 通信问题：直接描述您的问题，如「WiFi信号弱怎么办」
2. 代码调试：直接粘贴代码或描述错误
3. 知识查询：输入「什么是5G技术」
4. 故障排查：描述现象，如「手机上不了网」
5. 计算题：直接给出题目
6. 实训指导：描述实训内容和问题
                """)
                continue

            if user_input.lower() in ["清空", "重置", "重新开始"]:
                conversation_history = []
                print("✅ 对话历史已清空")
                continue

            # 判断是否使用知识库
            use_knowledge, knowledge_refs = should_use_knowledge(user_input)

            if use_knowledge and knowledge_refs:
                print(f"🔍 检索到{len(knowledge_refs)}条相关知识")

            # 生成消息
            messages = generate_answer(user_input, use_knowledge, knowledge_refs)

            # 添加上下文历史（最近的几轮对话）
            if conversation_history:
                # 只保留最近的历史
                recent_history = conversation_history[-MAX_HISTORY:]
                # 合并消息
                messages = [messages[0]] + recent_history + [messages[1]]
            else:
                messages = messages

            # 获取动态参数
            params = get_model_params(user_input)

            # 尝试多个模型
            success = False
            for model_idx, model in enumerate(MODEL_LIST):
                try:
                    print(f"🤔 思考中... (使用模型: {model.split('/')[-1]})")

                    payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": params["temperature"],
                        "max_tokens": params["max_tokens"],
                        "top_p": params["top_p"],
                        "presence_penalty": params["presence_penalty"],
                        "frequency_penalty": params["frequency_penalty"],
                        "stream": False
                    }

                    response = requests.post(API_URL, headers=headers, json=payload, timeout=30)

                    if response.status_code == 200:
                        result = response.json()
                        if "choices" in result and result["choices"]:
                            answer = result["choices"][0]["message"]["content"].strip()

                            # 清理回答
                            answer = re.sub(r'\n{3,}', '\n\n', answer)  # 去除多余空行

                            # 打印回答
                            print(f"\n🤖 助手：")
                            print("=" * 60)
                            print(answer)
                            print("=" * 60)

                            # 保存到历史
                            conversation_history.append({"role": "user", "content": user_input})
                            conversation_history.append({"role": "assistant", "content": answer})

                            # 限制历史长度
                            if len(conversation_history) > MAX_HISTORY:
                                conversation_history = conversation_history[-MAX_HISTORY:]

                            success = True
                            break

                    print(f"⚠️ 模型 {model} 响应异常，状态码: {response.status_code}")

                except requests.exceptions.Timeout:
                    print(f"⏰ 模型 {model} 响应超时，尝试下一个...")
                except Exception as e:
                    print(f"⚠️ 模型 {model} 错误: {str(e)[:50]}...，尝试下一个...")

                time.sleep(1)  # 短暂延迟

            if not success:
                print("""
❌ 所有模型请求失败，建议：
1. 检查网络连接
2. 确认API Key有效
3. 稍后重试
                """)

        except KeyboardInterrupt:
            print("\n\n⏹️ 程序被中断")
            break
        except Exception as e:
            print(f"\n⚠️ 发生错误: {str(e)}")
            print("💡 请重新输入您的问题")


# ====================== 启动程序 ======================
if __name__ == "__main__":
    chat()