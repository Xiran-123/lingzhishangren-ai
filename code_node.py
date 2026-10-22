#!/usr/bin/env python3
"""
灵智尚人 - 练习题系统代码节点
适用于讯飞星辰 Agent 平台工作流
"""

import sys
import json

try:
    import requests
except ImportError:
    print("需要安装 requests 库")
    sys.exit(1)

BASE_URL = "http://你的服务器IP:5000/api"
API_KEY = "lingzhishangren_agent_key"

headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

EXERCISE_BANK = {
    "傅里叶变换": [
        {
            "id": "ft_001",
            "type": "choice",
            "difficulty": 2,
            "question": "傅里叶变换的主要作用是什么？",
            "options": [
                "A. 将时域信号转换为频域表示",
                "B. 将模拟信号转换为数字信号",
                "C. 放大信号幅度",
                "D. 压缩数据"
            ],
            "answer": "A",
            "analysis": "傅里叶变换的核心作用是将时域信号转换为频域表示，揭示信号的频率成分和频谱特性。"
        },
        {
            "id": "ft_002",
            "type": "choice",
            "difficulty": 3,
            "question": "以下关于傅里叶变换性质的描述，哪一项是正确的？",
            "options": [
                "A. 时域卷积对应频域卷积",
                "B. 时域平移对应频域相位变化",
                "C. 时域微分对应频域微分",
                "D. 时域缩放不影响频域"
            ],
            "answer": "B",
            "analysis": "傅里叶变换的时移性质表明：时域中的平移对应频域中的相位变化，这是傅里叶变换最重要的性质之一。"
        },
        {
            "id": "ft_003",
            "type": "fill",
            "difficulty": 3,
            "question": "傅里叶变换的逆变换公式为：x(t) = ______",
            "options": [],
            "answer": "(1/2π)∫X(ω)e^(jωt)dω",
            "analysis": "傅里叶逆变换公式：x(t) = (1/2π)∫X(ω)e^(jωt)dω，用于将频域信号转换回时域。"
        },
        {
            "id": "ft_004",
            "type": "short",
            "difficulty": 4,
            "question": "请简述傅里叶变换在通信系统中的三个主要应用场景。",
            "options": [],
            "answer": "1. 频谱分析：分析信号的频率成分；2. 滤波设计：设计滤波器去除噪声；3. 调制解调：实现信号的调制和解调过程。",
            "analysis": "傅里叶变换在通信系统中应用广泛，包括频谱分析、滤波器设计、调制解调、信道估计等多个领域。"
        }
    ],
    "奈奎斯特采样定理": [
        {
            "id": "ns_001",
            "type": "choice",
            "difficulty": 2,
            "question": "奈奎斯特采样定理要求采样频率至少是信号最高频率的多少倍？",
            "options": ["A. 1倍", "B. 2倍", "C. 4倍", "D. 10倍"],
            "answer": "B",
            "analysis": "奈奎斯特采样定理指出：为了能够从采样后的离散信号中无失真地恢复原始连续信号，采样频率必须至少是信号最高频率的2倍。"
        },
        {
            "id": "ns_002",
            "type": "fill",
            "difficulty": 3,
            "question": "当采样频率低于奈奎斯特频率时，会产生______现象。",
            "options": [],
            "answer": "混叠",
            "analysis": "混叠（Aliasing）是指当采样频率低于奈奎斯特频率时，高频信号会被错误地识别为低频信号的现象。"
        },
        {
            "id": "ns_003",
            "type": "short",
            "difficulty": 4,
            "question": "请解释为什么在采样前需要使用抗混叠滤波器？",
            "options": [],
            "answer": "抗混叠滤波器用于在采样前滤除高于奈奎斯特频率的高频成分，防止这些高频信号在采样后产生混叠，从而保证采样信号的质量。",
            "analysis": "抗混叠滤波器是采样系统中必不可少的组成部分，它通过低通滤波限制信号带宽，确保采样过程满足奈奎斯特条件。"
        }
    ],
    "信噪比SNR": [
        {
            "id": "snr_001",
            "type": "choice",
            "difficulty": 2,
            "question": "信噪比（SNR）的定义是什么？",
            "options": ["A. 信号功率减去噪声功率", "B. 信号功率与噪声功率的比值", "C. 噪声功率与信号功率的比值", "D. 信号幅度与噪声幅度的比值"],
            "answer": "B",
            "analysis": "信噪比（Signal-to-Noise Ratio，SNR）定义为信号功率与噪声功率的比值，通常以分贝（dB）为单位表示。"
        },
        {
            "id": "snr_002",
            "type": "fill",
            "difficulty": 3,
            "question": "SNR = 20dB 表示信号功率是噪声功率的______倍。",
            "options": [],
            "answer": "100",
            "analysis": "SNR(dB) = 10log10(信号功率/噪声功率)，所以20dB = 10log10(100)，即信号功率是噪声功率的100倍。"
        },
        {
            "id": "snr_003",
            "type": "short",
            "difficulty": 4,
            "question": "请说明信噪比对通信系统性能的影响。",
            "options": [],
            "answer": "信噪比直接影响误码率：SNR越高，误码率越低，通信质量越好；SNR越低，误码率越高，通信质量越差。当SNR低于某个门限时，通信系统将无法正常工作。",
            "analysis": "信噪比是衡量通信系统性能的重要指标，它直接决定了系统的误码率和可靠性。"
        }
    ],
    "2ASK调制": [
        {
            "id": "ask_001",
            "type": "choice",
            "difficulty": 2,
            "question": "2ASK调制的基本原理是什么？",
            "options": ["A. 用数字信号控制载波的频率", "B. 用数字信号控制载波的幅度", "C. 用数字信号控制载波的相位", "D. 用数字信号控制载波的功率"],
            "answer": "B",
            "analysis": "2ASK（二进制幅度键控）调制通过用数字信号控制载波的幅度来传输信息：发送'1'时发送载波，发送'0'时不发送载波。"
        },
        {
            "id": "ask_002",
            "type": "fill",
            "difficulty": 3,
            "question": "2ASK信号的带宽是基带信号带宽的______倍。",
            "options": [],
            "answer": "2",
            "analysis": "2ASK信号的频谱宽度是基带信号带宽的2倍，这是所有线性调制方式的共同特点。"
        }
    ],
    "2FSK调制": [
        {
            "id": "fsk_001",
            "type": "choice",
            "difficulty": 2,
            "question": "2FSK调制与2ASK调制的主要区别是什么？",
            "options": ["A. 使用不同的载波频率", "B. 使用不同的调制方式", "C. 使用不同的传输介质", "D. 使用不同的编码方式"],
            "answer": "A",
            "analysis": "2FSK（二进制频移键控）通过改变载波频率来传输信息，而2ASK通过改变载波幅度。在2FSK中，'0'和'1'分别对应两个不同的载波频率。"
        },
        {
            "id": "fsk_002",
            "type": "fill",
            "difficulty": 3,
            "question": "2FSK信号的最小频率间隔应大于等于______。",
            "options": [],
            "answer": "基带信号带宽",
            "analysis": "为了保证2FSK信号的正交性，两个载波频率之间的最小间隔应大于等于基带信号的带宽。"
        }
    ],
    "QAM调制": [
        {
            "id": "qam_001",
            "type": "choice",
            "difficulty": 3,
            "question": "QAM调制同时利用了载波的哪些特性来传输信息？",
            "options": ["A. 幅度和频率", "B. 幅度和相位", "C. 频率和相位", "D. 幅度、频率和相位"],
            "answer": "B",
            "analysis": "QAM（正交幅度调制）同时利用载波的幅度和相位两个维度来传输信息，因此在相同带宽下可以传输更多的数据。"
        },
        {
            "id": "qam_002",
            "type": "fill",
            "difficulty": 4,
            "question": "16QAM信号在一个符号周期内可以传输______比特信息。",
            "options": [],
            "answer": "4",
            "analysis": "16QAM有16个星座点，每个星座点对应4比特（2^4=16），因此每个符号可以传输4比特信息。"
        },
        {
            "id": "qam_003",
            "type": "short",
            "difficulty": 4,
            "question": "请简述QAM调制的优缺点。",
            "options": [],
            "answer": "优点：频谱效率高，在相同带宽下可以传输更多数据；缺点：对噪声和信道失真敏感，需要更复杂的均衡和纠错技术。",
            "analysis": "QAM是现代通信系统中广泛使用的调制方式，其主要优势在于高频谱效率。"
        }
    ],
    "OFDM": [
        {
            "id": "ofdm_001",
            "type": "choice",
            "difficulty": 3,
            "question": "OFDM的中文全称是什么？",
            "options": ["A. 正交频分复用", "B. 正交幅度调制", "C. 正交相移键控", "D. 正交码分多址"],
            "answer": "A",
            "analysis": "OFDM（Orthogonal Frequency Division Multiplexing）即正交频分复用，是一种将信道分成多个正交子信道的调制技术。"
        },
        {
            "id": "ofdm_002",
            "type": "fill",
            "difficulty": 4,
            "question": "OFDM通过______技术实现子载波之间的正交性。",
            "options": [],
            "answer": "循环前缀",
            "analysis": "循环前缀（Cyclic Prefix）是OFDM实现正交性的关键技术，它通过在每个OFDM符号前添加前缀，消除符号间干扰和子载波间干扰。"
        },
        {
            "id": "ofdm_003",
            "type": "short",
            "difficulty": 5,
            "question": "请说明OFDM技术在4G/5G通信中的应用。",
            "options": [],
            "answer": "OFDM是4G LTE和5G NR的核心调制技术，它通过将宽带信道分成多个窄带子信道，有效对抗多径衰落，提高频谱效率，支持高速数据传输。",
            "analysis": "OFDM是现代移动通信系统的基础技术，广泛应用于4G、5G、WiFi等系统中。"
        }
    ],
    "卷积": [
        {
            "id": "conv_001",
            "type": "choice",
            "difficulty": 2,
            "question": "卷积运算在信号处理中的主要作用是什么？",
            "options": ["A. 信号放大", "B. 信号滤波", "C. 信号编码", "D. 信号压缩"],
            "answer": "B",
            "analysis": "卷积是信号处理中最基本的运算之一，主要用于实现线性时不变系统的滤波操作，即通过卷积核对输入信号进行变换。"
        },
        {
            "id": "conv_002",
            "type": "fill",
            "difficulty": 3,
            "question": "两个序列x(n)和h(n)的卷积结果长度为______。",
            "options": [],
            "answer": "N+M-1",
            "analysis": "若x(n)长度为N，h(n)长度为M，则卷积结果长度为N+M-1。这是卷积运算的基本性质。"
        }
    ],
    "故障排查": [
        {
            "id": "fault_001",
            "type": "choice",
            "difficulty": 3,
            "question": "在通信系统故障排查中，首先应该做什么？",
            "options": ["A. 更换所有设备", "B. 收集故障信息", "C. 重启系统", "D. 联系供应商"],
            "answer": "B",
            "analysis": "故障排查的第一步是收集完整的故障信息，包括故障现象、发生时间、影响范围等，这是准确定位问题的基础。"
        },
        {
            "id": "fault_002",
            "type": "short",
            "difficulty": 4,
            "question": "请简述通信系统故障排查的一般流程。",
            "options": [],
            "answer": "1. 收集故障信息；2. 分析故障现象；3. 定位故障点；4. 实施修复；5. 验证修复效果；6. 记录故障报告。",
            "analysis": "系统化的故障排查流程可以提高问题解决效率，减少故障恢复时间。"
        }
    ],
    "链路预算": [
        {
            "id": "lb_001",
            "type": "choice",
            "difficulty": 3,
            "question": "链路预算的主要目的是什么？",
            "options": ["A. 计算设备成本", "B. 评估通信链路的可靠性", "C. 设计网络拓扑", "D. 优化系统功耗"],
            "answer": "B",
            "analysis": "链路预算通过计算发射功率、路径损耗、接收灵敏度等参数，评估通信链路在各种条件下的可靠性，确保系统满足通信要求。"
        },
        {
            "id": "lb_002",
            "type": "fill",
            "difficulty": 4,
            "question": "链路预算中，______表示实际接收功率与接收灵敏度之间的差值。",
            "options": [],
            "answer": "链路余量",
            "analysis": "链路余量（Link Margin）是链路预算中的关键指标，它表示系统在恶劣条件下仍能正常工作的能力。"
        },
        {
            "id": "lb_003",
            "type": "short",
            "difficulty": 5,
            "question": "请说明链路预算中主要包含哪些参数。",
            "options": [],
            "answer": "主要参数包括：发射功率、天线增益、路径损耗、阴影衰落、多径衰落、接收天线增益、接收灵敏度、链路余量等。",
            "analysis": "完整的链路预算需要考虑所有影响信号传输的因素，确保系统在各种环境条件下都能正常工作。"
        }
    ]
}

def get_knowledge_points():
    """获取知识点列表"""
    result = []
    for point in EXERCISE_BANK.keys():
        result.append({
            'name': point,
            'exercise_count': len(EXERCISE_BANK.get(point, []))
        })
    return {'success': True, 'knowledge_points': result, 'total': len(result)}

def generate_exercises(knowledge_point, count=3):
    """根据知识点生成练习题"""
    import random
    exercises = EXERCISE_BANK.get(knowledge_point, [])
    if not exercises:
        return {'success': False, 'error': f'知识点 "{knowledge_point}" 暂无练习题'}
    
    count = min(count, len(exercises))
    selected = random.sample(exercises, count)
    return {'success': True, 'knowledge_point': knowledge_point, 'exercises': selected, 'count': len(selected)}

def grade_answer(question_id, student_answer):
    """批改答案"""
    correct_answer = None
    analysis = None
    knowledge_point = None
    exercise_type = None
    
    for kp, exercises in EXERCISE_BANK.items():
        for ex in exercises:
            if ex['id'] == question_id:
                correct_answer = ex['answer']
                analysis = ex['analysis']
                knowledge_point = kp
                exercise_type = ex['type']
                break
        if correct_answer:
            break
    
    if not correct_answer:
        return {'success': False, 'error': '题目不存在'}
    
    is_correct = False
    if exercise_type == 'choice':
        is_correct = student_answer.strip().upper() == correct_answer.strip().upper()
    elif exercise_type == 'fill':
        is_correct = student_answer.strip().lower() == correct_answer.strip().lower()
    else:
        is_correct = len(student_answer.strip()) >= len(correct_answer) * 0.6
    
    return {'success': True, 'is_correct': is_correct, 'correct_answer': correct_answer, 'analysis': analysis, 'knowledge_point': knowledge_point}

def main():
    """主函数 - 根据输入参数执行相应操作"""
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    if not args:
        print(json.dumps({'success': False, 'error': '请提供操作类型'}))
        return
    
    action = args[0]
    
    if action == 'get_knowledge_points':
        result = get_knowledge_points()
    elif action == 'generate_exercises':
        knowledge_point = args[1] if len(args) > 1 else ''
        count = int(args[2]) if len(args) > 2 else 3
        result = generate_exercises(knowledge_point, count)
    elif action == 'grade_answer':
        question_id = args[1] if len(args) > 1 else ''
        student_answer = args[2] if len(args) > 2 else ''
        result = grade_answer(question_id, student_answer)
    else:
        result = {'success': False, 'error': f'未知操作: {action}'}
    
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()