from flask import Blueprint, request, jsonify
import random
import json
import os
import re
from datetime import datetime, timedelta

public_api = Blueprint('public_api', __name__)

API_KEYS = {
    "lingzhishangren_agent_key": "your_secure_secret_key_here_2024",
    "Lingzhishangren_agent_key": "your_secure_secret_key_here_2024",
    "LINGZHISHANGREN_AGENT_KEY": "your_secure_secret_key_here_2024"
}

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
            "options": [
                "A. 1倍",
                "B. 2倍",
                "C. 4倍",
                "D. 10倍"
            ],
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
            "options": [
                "A. 信号功率减去噪声功率",
                "B. 信号功率与噪声功率的比值",
                "C. 噪声功率与信号功率的比值",
                "D. 信号幅度与噪声幅度的比值"
            ],
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
            "options": [
                "A. 用数字信号控制载波的频率",
                "B. 用数字信号控制载波的幅度",
                "C. 用数字信号控制载波的相位",
                "D. 用数字信号控制载波的功率"
            ],
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
            "options": [
                "A. 使用不同的载波频率",
                "B. 使用不同的调制方式",
                "C. 使用不同的传输介质",
                "D. 使用不同的编码方式"
            ],
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
            "options": [
                "A. 幅度和频率",
                "B. 幅度和相位",
                "C. 频率和相位",
                "D. 幅度、频率和相位"
            ],
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
            "options": [
                "A. 正交频分复用",
                "B. 正交幅度调制",
                "C. 正交相移键控",
                "D. 正交码分多址"
            ],
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
            "options": [
                "A. 信号放大",
                "B. 信号滤波",
                "C. 信号编码",
                "D. 信号压缩"
            ],
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
            "options": [
                "A. 更换所有设备",
                "B. 收集故障信息",
                "C. 重启系统",
                "D. 联系供应商"
            ],
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
            "options": [
                "A. 计算设备成本",
                "B. 评估通信链路的可靠性",
                "C. 设计网络拓扑",
                "D. 优化系统功耗"
            ],
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

KNOWLEDGE_GRAPH = {
    "傅里叶变换": {"category": "理论基础", "difficulty": 3},
    "奈奎斯特采样定理": {"category": "理论基础", "difficulty": 2},
    "信噪比SNR": {"category": "理论基础", "difficulty": 2},
    "2ASK调制": {"category": "调制技术", "difficulty": 2},
    "2FSK调制": {"category": "调制技术", "difficulty": 2},
    "QAM调制": {"category": "调制技术", "difficulty": 3},
    "OFDM": {"category": "调制技术", "difficulty": 4},
    "卷积": {"category": "理论基础", "difficulty": 3},
    "故障排查": {"category": "工程实践", "difficulty": 3},
    "链路预算": {"category": "工程实践", "difficulty": 4}
}

WRONG_QUESTIONS_FILE = "wrong_questions_agent.json"

def authenticate_api_key():
    api_key = (
        request.headers.get('X-API-Key') or
        request.headers.get('X_API_Key') or
        request.headers.get('x-api-key') or
        request.headers.get('x_api_key') or
        request.args.get('api_key') or
        request.args.get('apiKey') or
        request.args.get('X_API_Key')
    )
    if not api_key or api_key not in API_KEYS:
        return False, jsonify({'error': '无效的API Key', 'success': False}), 401
    return True, None, None

def load_wrong_questions():
    if os.path.exists(WRONG_QUESTIONS_FILE):
        with open(WRONG_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_wrong_questions(questions):
    with open(WRONG_QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

@public_api.route('/v1/knowledge-points', methods=['GET'])
def get_knowledge_points():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    result = []
    for point in EXERCISE_BANK.keys():
        kg_info = KNOWLEDGE_GRAPH.get(point, {})
        exercise_count = len(EXERCISE_BANK.get(point, []))
        result.append({
            'name': point,
            'category': kg_info.get('category', ''),
            'difficulty': kg_info.get('difficulty', 0),
            'exercise_count': exercise_count
        })
    
    return jsonify({
        'success': True,
        'knowledge_points': result,
        'total': len(result)
    })

@public_api.route('/v1/exercises/generate', methods=['POST'])
def api_generate_exercises():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    data = request.json
    knowledge_point = data.get('knowledge_point', '')
    count = int(data.get('count', 3))
    
    if not knowledge_point:
        return jsonify({'success': False, 'error': '请指定知识点'}), 400
    
    exercises = EXERCISE_BANK.get(knowledge_point, [])
    if not exercises:
        return jsonify({'success': False, 'error': f'知识点 "{knowledge_point}" 暂无练习题'}), 404
    
    count = min(count, len(exercises))
    selected = random.sample(exercises, count)
    
    return jsonify({
        'success': True,
        'knowledge_point': knowledge_point,
        'exercises': selected,
        'count': len(selected)
    })

@public_api.route('/v1/exercises/submit', methods=['POST'])
def api_submit_answer():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    data = request.json
    question_id = data.get('question_id', '')
    student_answer = data.get('student_answer', '')
    student_name = data.get('student_name', '')
    
    if not question_id:
        return jsonify({'success': False, 'error': '请指定题目ID'}), 400
    
    correct_answer = None
    analysis = None
    question_text = None
    knowledge_point = None
    exercise_type = None
    
    for kp, exercises in EXERCISE_BANK.items():
        for ex in exercises:
            if ex['id'] == question_id:
                correct_answer = ex['answer']
                analysis = ex['analysis']
                question_text = ex['question']
                knowledge_point = kp
                exercise_type = ex['type']
                break
        if correct_answer:
            break
    
    if not correct_answer:
        return jsonify({'success': False, 'error': '题目不存在'}), 404
    
    is_correct = False
    if exercise_type == 'choice':
        is_correct = student_answer.strip().upper() == correct_answer.strip().upper()
    elif exercise_type == 'fill':
        is_correct = student_answer.strip().lower() == correct_answer.strip().lower()
    else:
        is_correct = len(student_answer.strip()) >= len(correct_answer) * 0.6
    
    if not is_correct and student_name:
        wrong_questions = load_wrong_questions()
        new_question = {
            "id": f"wq_{len(wrong_questions) + 1}",
            "student_name": student_name,
            "question": question_text,
            "category": "练习题",
            "knowledge_point": knowledge_point,
            "student_answer": student_answer,
            "correct_answer": correct_answer,
            "timestamp": datetime.now().isoformat(),
            "mastered": False
        }
        wrong_questions.append(new_question)
        save_wrong_questions(wrong_questions)
    
    return jsonify({
        'success': True,
        'is_correct': is_correct,
        'correct_answer': correct_answer,
        'analysis': analysis,
        'knowledge_point': knowledge_point
    })

@public_api.route('/v1/wrong-questions', methods=['GET'])
def api_get_wrong_questions():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    student_name = request.args.get('student_name', '')
    wrong_questions = load_wrong_questions()
    
    if student_name:
        wrong_questions = [q for q in wrong_questions if q.get('student_name') == student_name]
    
    return jsonify({
        'success': True,
        'wrong_questions': wrong_questions,
        'count': len(wrong_questions)
    })

@public_api.route('/v1/wrong-questions', methods=['POST'])
def api_add_wrong_question():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    data = request.json
    student_name = data.get('student_name', '')
    question = data.get('question', '')
    knowledge_point = data.get('knowledge_point', '')
    student_answer = data.get('student_answer', '')
    correct_answer = data.get('correct_answer', '')
    
    if not all([student_name, question, knowledge_point]):
        return jsonify({'success': False, 'error': '缺少必要参数'}), 400
    
    wrong_questions = load_wrong_questions()
    new_question = {
        "id": f"wq_{len(wrong_questions) + 1}",
        "student_name": student_name,
        "question": question,
        "category": "练习题",
        "knowledge_point": knowledge_point,
        "student_answer": student_answer,
        "correct_answer": correct_answer,
        "timestamp": datetime.now().isoformat(),
        "mastered": False
    }
    wrong_questions.append(new_question)
    save_wrong_questions(wrong_questions)
    
    return jsonify({'success': True, 'message': '错题已添加'})

@public_api.route('/v1/wrong-questions/<question_id>/master', methods=['POST'])
def api_mark_mastered(question_id):
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    wrong_questions = load_wrong_questions()
    
    for q in wrong_questions:
        if q['id'] == question_id:
            q['mastered'] = True
            q['mastered_time'] = datetime.now().isoformat()
            save_wrong_questions(wrong_questions)
            return jsonify({'success': True, 'message': '已标记为掌握'})
    
    return jsonify({'success': False, 'error': '错题不存在'}), 404

COMPETENCE_AREAS = [
    {"id": "ft", "name": "傅里叶变换", "category": "理论基础", "weight": 1.0},
    {"id": "ns", "name": "奈奎斯特采样定理", "category": "理论基础", "weight": 0.8},
    {"id": "snr", "name": "信噪比SNR", "category": "理论基础", "weight": 0.8},
    {"id": "ask", "name": "2ASK调制", "category": "调制技术", "weight": 0.7},
    {"id": "fsk", "name": "2FSK调制", "category": "调制技术", "weight": 0.7},
    {"id": "qam", "name": "QAM调制", "category": "调制技术", "weight": 0.9},
    {"id": "ofdm", "name": "OFDM", "category": "调制技术", "weight": 1.0},
    {"id": "conv", "name": "卷积", "category": "理论基础", "weight": 0.8},
    {"id": "fault", "name": "故障排查", "category": "工程实践", "weight": 0.9},
    {"id": "lb", "name": "链路预算", "category": "工程实践", "weight": 1.0},
    {"id": "sys", "name": "系统设计", "category": "工程实践", "weight": 1.0},
    {"id": "proto", "name": "协议理解", "category": "理论基础", "weight": 0.9}
]

JOB_REQUIREMENTS = {
    "通信工程师": {
        "傅里叶变换": 0.8, "奈奎斯特采样定理": 0.7, "信噪比SNR": 0.8,
        "QAM调制": 0.9, "OFDM": 1.0, "故障排查": 0.8, "链路预算": 0.9
    },
    "网络工程师": {
        "OFDM": 0.7, "故障排查": 1.0, "链路预算": 0.8,
        "协议理解": 1.0, "系统设计": 0.9
    },
    "信号处理工程师": {
        "傅里叶变换": 1.0, "卷积": 1.0, "奈奎斯特采样定理": 0.9,
        "信噪比SNR": 0.8, "QAM调制": 0.7
    },
    "嵌入式开发工程师": {
        "2ASK调制": 0.6, "2FSK调制": 0.6, "系统设计": 0.9,
        "故障排查": 0.8, "协议理解": 0.7
    }
}

LEARNING_RECORDS_FILE = "learning_records_agent.json"

def load_learning_records():
    if os.path.exists(LEARNING_RECORDS_FILE):
        with open(LEARNING_RECORDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_learning_records(records):
    with open(LEARNING_RECORDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def calculate_job_match_score(student_scores, job_name):
    requirements = JOB_REQUIREMENTS.get(job_name, {})
    if not requirements:
        return {'match_rate': 0, 'gaps': [], 'strengths': []}
    
    total_weight = sum(requirements.values())
    match_score = 0
    
    gaps = []
    strengths = []
    
    for skill, weight in requirements.items():
        student_score = student_scores.get(skill, 0)
        match_score += student_score * weight
        
        if student_score < 0.6:
            gaps.append({'skill': skill, 'required': round(weight * 100), 'current': round(student_score * 100)})
        elif student_score >= 0.8:
            strengths.append({'skill': skill, 'score': round(student_score * 100)})
    
    match_rate = round((match_score / total_weight) * 100, 1)
    
    return {'match_rate': match_rate, 'gaps': gaps, 'strengths': strengths}

@public_api.route('/v1/learning-curve', methods=['GET'])
def api_learning_curve():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    student_name = request.args.get('student_name', '')
    days = int(request.args.get('days', 30))
    
    records = load_learning_records()
    student_records = records.get(student_name, [])
    
    from collections import defaultdict
    daily_data = defaultdict(lambda: {'questions': 0, 'wrong': 0, 'mastered': 0, 'scores': []})
    
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    for rec in student_records:
        if rec['date'] >= cutoff_date:
            date = rec['date']
            daily_data[date]['questions'] += 1
            if rec['activity_type'] == 'wrong_question':
                daily_data[date]['wrong'] += 1
            elif rec['activity_type'] == 'mastered':
                daily_data[date]['mastered'] += 1
            if rec.get('score') is not None:
                daily_data[date]['scores'].append(rec['score'])
    
    curve = []
    for date in sorted(daily_data.keys()):
        data = daily_data[date]
        avg_score = sum(data['scores']) / len(data['scores']) if data['scores'] else 0
        accuracy = (1 - data['wrong'] / data['questions']) * 100 if data['questions'] > 0 else 0
        curve.append({
            'date': date,
            'questions': data['questions'],
            'wrong': data['wrong'],
            'mastered': data['mastered'],
            'avg_score': round(avg_score, 1),
            'accuracy': round(accuracy, 1)
        })
    
    return jsonify({
        'success': True,
        'curve': curve,
        'total_records': len(student_records),
        'student_name': student_name
    })

@public_api.route('/v1/job-match', methods=['GET'])
def api_job_match():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    student_name = request.args.get('student_name', '')
    job_name = request.args.get('job_name', '通信工程师')
    
    records = load_learning_records()
    student_records = records.get(student_name, [])
    
    student_scores = {}
    for rec in student_records:
        if 'knowledge_point' in rec:
            kp = rec['knowledge_point']
            if kp not in student_scores:
                student_scores[kp] = {'total': 0, 'correct': 0}
            student_scores[kp]['total'] += 1
            if rec.get('is_correct', False):
                student_scores[kp]['correct'] += 1
    
    normalized_scores = {}
    for kp, data in student_scores.items():
        normalized_scores[kp] = data['correct'] / data['total'] if data['total'] > 0 else 0
    
    match_result = calculate_job_match_score(normalized_scores, job_name)
    
    all_jobs = {}
    for job in JOB_REQUIREMENTS.keys():
        all_jobs[job] = calculate_job_match_score(normalized_scores, job)['match_rate']
    
    return jsonify({
        'success': True,
        'student_name': student_name,
        'job_name': job_name,
        'match_rate': match_result['match_rate'],
        'gaps': match_result['gaps'],
        'strengths': match_result['strengths'],
        'all_jobs': all_jobs,
        'available_jobs': list(JOB_REQUIREMENTS.keys())
    })

@public_api.route('/v1/competence-radar', methods=['GET'])
def api_competence_radar():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    student_name = request.args.get('student_name', '')
    
    records = load_learning_records()
    student_records = records.get(student_name, [])
    
    student_scores = {}
    for rec in student_records:
        if 'knowledge_point' in rec:
            kp = rec['knowledge_point']
            if kp not in student_scores:
                student_scores[kp] = {'total': 0, 'correct': 0}
            student_scores[kp]['total'] += 1
            if rec.get('is_correct', False):
                student_scores[kp]['correct'] += 1
    
    radar_data = []
    category_summary = {}
    
    for area in COMPETENCE_AREAS:
        area_name = area['name']
        score_data = student_scores.get(area_name, {'total': 0, 'correct': 0})
        score = score_data['correct'] / score_data['total'] if score_data['total'] > 0 else 0
        count = score_data['total']
        
        score_pct = round(score * 100, 1)
        radar_data.append({
            'id': area['id'],
            'name': area['name'],
            'category': area['category'],
            'score': score_pct,
            'count': count,
            'weight': area['weight']
        })
        
        cat = area['category']
        if cat not in category_summary:
            category_summary[cat] = {'total_score': 0, 'count': 0, 'max': 0}
        category_summary[cat]['total_score'] += score_pct * area['weight']
        category_summary[cat]['count'] += 1
        category_summary[cat]['max'] += 100 * area['weight']
    
    for cat in category_summary:
        if category_summary[cat]['max'] > 0:
            category_summary[cat]['average'] = round(category_summary[cat]['total_score'] / category_summary[cat]['max'] * 100, 1)
    
    return jsonify({
        'success': True,
        'student_name': student_name,
        'radar_data': radar_data,
        'category_summary': category_summary
    })

@public_api.route('/v1/knowledge-graph', methods=['GET'])
def api_knowledge_graph():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    keyword = request.args.get('keyword', '')
    
    if keyword:
        results = {}
        for kp, info in KNOWLEDGE_GRAPH.items():
            if keyword in kp:
                results[kp] = info
        return jsonify({'success': True, 'graph': results, 'keyword': keyword})
    
    return jsonify({
        'success': True,
        'graph': KNOWLEDGE_GRAPH,
        'total_concepts': len(KNOWLEDGE_GRAPH)
    })

@public_api.route('/v1/review/recommend', methods=['GET'])
def api_recommend_review():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    student_name = request.args.get('student_name', '')
    limit = int(request.args.get('limit', 5))
    
    wrong_questions = load_wrong_questions()
    
    if student_name:
        wrong_questions = [q for q in wrong_questions if q.get('student_name') == student_name]
    
    unmastered = [q for q in wrong_questions if not q.get('mastered', False)]
    
    recommendations = []
    for wq in unmastered[:limit]:
        recommendations.append({
            'question': wq['question'],
            'knowledge_point': wq['knowledge_point'],
            'student_answer': wq['student_answer'],
            'correct_answer': wq['correct_answer'],
            'timestamp': wq['timestamp']
        })
    
    if not recommendations:
        recommendations = [{'message': '暂无错题，继续保持！'}]
    
    return jsonify({
        'success': True,
        'recommendations': recommendations,
        'total_unmastered': len(unmastered),
        'student_name': student_name
    })

@public_api.route('/v1/health', methods=['GET'])
def health_check():
    return jsonify({'success': True, 'message': '灵智尚人API服务正常运行', 'version': '1.0.0'})

# ====================== 智能问答 API ======================
import requests
import sys as _sys


def _load_siliconflow_key():
    """密钥读取优先级：环境变量 SILICONFLOW_API_KEY > api_key.local 文件。

    api_key.local 不随源码提交（已加入 .gitignore），打包 exe 时放在 exe 同级目录。
    """
    key = os.environ.get('SILICONFLOW_API_KEY', '').strip()
    if key:
        return key
    if getattr(_sys, 'frozen', False):
        key_file = os.path.join(os.path.dirname(_sys.executable), 'api_key.local')
    else:
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_key.local')
    try:
        with open(key_file, 'r', encoding='utf-8') as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    return ''


API_KEY = _load_siliconflow_key()
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_NAME = "Pro/moonshotai/Kimi-K2.6"

INTENT_PATTERNS = [
    {'intent': 'concept_understanding', 'name': '概念理解', 'patterns': [
        r'什么是(.+)', r'.+是什么', r'.+的定义', r'.+的概念', r'.+的含义', r'.+是什么意思', r'.+指的是什么'
    ]},
    {'intent': 'principle_analysis', 'name': '原理分析', 'patterns': [
        r'.+的原理', r'.+的工作原理', r'.+为什么', r'.+背后的原理', r'.+的机制', r'.+是如何工作的', r'.+的数学原理', r'.+公式推导'
    ]},
    {'intent': 'method_steps', 'name': '方法步骤', 'patterns': [
        r'.+的步骤', r'.+的方法', r'.+怎么做', r'.+如何操作', r'.+的流程', r'.+的过程', r'.+的步骤是什么'
    ]},
    {'intent': 'comparison_analysis', 'name': '对比分析', 'patterns': [
        r'.+和.+的区别', r'.+与.+对比', r'.+和.+哪个好', r'.+和.+的异同', r'.+对比.+', r'.+vs.+', r'.+与.+的差异'
    ]},
    {'intent': 'problem_solving', 'name': '问题解决', 'patterns': [
        r'.+故障', r'.+问题', r'.+怎么解决', r'.+如何处理', r'.+怎么办', r'.+出错', r'.+报错', r'.+异常'
    ]},
    {'intent': 'application_scenario', 'name': '应用场景', 'patterns': [
        r'.+的应用', r'.+的用途', r'.+在什么情况下使用', r'.+的使用场景', r'.+应用实例', r'.+实际应用'
    ]},
    {'intent': 'knowledge_review', 'name': '知识复习', 'patterns': [
        r'.+复习', r'.+总结', r'.+重点', r'.+考点', r'.+知识点', r'.+归纳'
    ]}
]

KNOWLEDGE_GRAPH_FULL = {
    "傅里叶变换": {
        "category": "理论基础", "difficulty": 3,
        "prerequisites": ["时域频域概念"],
        "related": ["拉普拉斯变换", "Z变换", "FFT", "频谱分析"],
        "applications": ["信号分析", "滤波器设计", "调制解调"],
        "description": "傅里叶变换是将时域信号转换为频域表示的数学工具，揭示了信号的频率成分。",
        "key_points": ["正变换公式", "逆变换公式", "时域连续→频域连续", "线性、时移、频移、卷积性质"],
        "formula": "X(ω) = ∫x(t)·e^(-jωt) dt"
    },
    "奈奎斯特采样定理": {
        "category": "理论基础", "difficulty": 2,
        "prerequisites": ["时域频域概念"],
        "related": ["采样率", "混叠", "抗混叠滤波器"],
        "applications": ["ADC设计", "音频处理"],
        "description": "奈奎斯特采样定理由奈奎斯特和香农提出，指出采样频率必须大于信号最高频率的两倍。",
        "key_points": ["fs > 2fmax", "采样不足会产生混叠", "实际取fs=2.5~3倍fmax"],
        "formula": "f_s > 2·f_{max}"
    },
    "信噪比SNR": {
        "category": "理论基础", "difficulty": 2,
        "prerequisites": ["信号功率", "噪声功率"],
        "related": ["误码率", "信道容量", "香农公式"],
        "applications": ["通信系统设计", "链路预算"],
        "description": "信噪比是信号功率与噪声功率的比值，是衡量通信系统质量的重要指标。",
        "key_points": ["SNR = P_signal / P_noise", "常用分贝表示", "影响误码率"],
        "formula": "SNR_{dB} = 10·log_{10}(P_{signal}/P_{noise})"
    },
    "2ASK调制": {
        "category": "调制技术", "difficulty": 2,
        "prerequisites": ["载波", "基带信号"],
        "related": ["2FSK", "2PSK", "BPSK"],
        "applications": ["低速数据传输", "遥控系统"],
        "description": "2ASK通过改变载波幅度传输二进制数据，载波存在表示'1'，不存在表示'0'。",
        "key_points": ["实现简单", "抗噪声性能差", "适合低速通信"],
        "formula": "s(t) = A·cos(ω_c t) 或 0"
    },
    "2FSK调制": {
        "category": "调制技术", "difficulty": 2,
        "prerequisites": ["载波", "频率切换"],
        "related": ["2ASK", "2PSK", "GFSK"],
        "applications": ["无线传感网", "RFID"],
        "description": "2FSK通过改变载波频率传输二进制数据，两种频率分别表示'0'和'1'。",
        "key_points": ["抗噪声优于2ASK", "实现简单", "带宽利用率低"],
        "formula": "s(t) = A·cos(ω_1 t) 或 A·cos(ω_2 t)"
    },
    "QAM调制": {
        "category": "调制技术", "difficulty": 3,
        "prerequisites": ["PSK", "ASK", "星座图"],
        "related": ["16QAM", "64QAM", "256QAM"],
        "applications": ["4G/5G通信", "WiFi", "数字电视"],
        "description": "QAM同时利用幅度和相位传输信息，具有很高的频谱效率。",
        "key_points": ["高阶QAM频谱效率高", "对信噪比要求高", "星座图展示"],
        "formula": "s(t) = A_I·cos(ω_c t) - A_Q·sin(ω_c t)"
    },
    "OFDM": {
        "category": "调制技术", "difficulty": 4,
        "prerequisites": ["FFT", "多载波", "循环前缀"],
        "related": ["MIMO", "信道估计"],
        "applications": ["4G LTE", "5G NR", "WiFi6"],
        "description": "OFDM将高速数据流分解为多个低速子流，在正交子载波上并行传输。",
        "key_points": ["抗多径衰落能力强", "频谱效率高", "FFT实现", "循环前缀对抗干扰"],
        "formula": "s(t) = ΣX_k·e^(j2πkt/T)"
    },
    "卷积": {
        "category": "理论基础", "difficulty": 3,
        "prerequisites": ["线性时不变系统"],
        "related": ["系统响应", "滤波器"],
        "applications": ["信号处理", "系统分析"],
        "description": "卷积描述线性时不变系统输入输出关系，输出等于输入与冲激响应的卷积。",
        "key_points": ["y(t) = x(t) * h(t)", "时域卷积↔频域相乘", "滤波器设计核心"],
        "formula": "y(t) = ∫x(τ)·h(t-τ) dτ"
    },
    "故障排查": {
        "category": "工程实践", "difficulty": 3,
        "prerequisites": ["通信原理", "设备操作"],
        "related": ["告警分析", "性能监控", "日志分析"],
        "applications": ["网络优化", "设备维护"],
        "description": "故障排查是通信工程师的核心技能，通过系统性方法分析解决网络故障。",
        "key_points": ["告警分级处理", "性能监控", "分层排查法", "故障复盘"],
        "formula": "MTTR = Σ故障恢复时间/故障次数"
    },
    "链路预算": {
        "category": "工程实践", "difficulty": 4,
        "prerequisites": ["路径损耗", "天线增益", "发射功率"],
        "related": ["覆盖规划", "容量规划"],
        "applications": ["基站规划", "网络设计"],
        "description": "链路预算计算通信链路中所有增益和损耗，评估链路可靠性。",
        "key_points": ["接收功率计算", "考虑衰落余量", "上下行平衡"],
        "formula": "P_r = P_t + G_t + G_r - L_p - L_{other}"
    }
}

SCENARIOS = [
    {
        "id": 1,
        "title": "新入职通信工程师",
        "description": "你刚从大学毕业，进入一家通信设备公司担任初级工程师，需要在一周内熟悉5G基站的安装调试工作。",
        "difficulty": "简单",
        "tasks": ["学习5G基站的基本组成和工作原理", "完成一次基站安装的模拟操作", "处理一个常见的基站连接故障"]
    },
    {
        "id": 2,
        "title": "网络故障排查工程师",
        "description": "你负责城市通信网络的监控和维护，突然接到报告说某大型商场的WiFi信号大面积断网。",
        "difficulty": "中等",
        "tasks": ["使用网络诊断工具定位故障点", "制定并执行故障排除方案", "记录故障原因和解决方案"]
    },
    {
        "id": 3,
        "title": "通信系统优化工程师",
        "description": "你被派往一个新建成的工业园区，需要优化园区内的通信网络以满足智能工厂的需求。",
        "difficulty": "较难",
        "tasks": ["进行信号覆盖测试", "分析网络瓶颈并提出优化方案", "实施优化方案并验证效果"]
    }
]

def identify_intent(query):
    query_lower = query.lower()
    for intent_info in INTENT_PATTERNS:
        for pattern in intent_info['patterns']:
            if re.search(pattern, query_lower):
                return {'intent': intent_info['intent'], 'name': intent_info['name'], 'confidence': 0.85}
    return {'intent': 'general_question', 'name': '一般问题', 'confidence': 0.5}

def search_knowledge_graph_full(query):
    query_lower = query.lower()
    results = {}
    for concept, info in KNOWLEDGE_GRAPH_FULL.items():
        if query_lower in concept.lower() or concept.lower() in query_lower:
            results[concept] = info
        else:
            for kw in info.get('related', []) + info.get('applications', []) + info.get('prerequisites', []):
                if query_lower in kw.lower():
                    results[concept] = info
                    break
    return results

def generate_system_prompt(query, mode='fast'):
    kg_results = search_knowledge_graph_full(query)
    intent = identify_intent(query)
    
    kg_context = ""
    if kg_results:
        kg_context = "\n【相关知识点】\n"
        for concept, info in kg_results.items():
            kg_context += f"- **{concept}**（难度: {'⭐' * info.get('difficulty', 0)}）\n"
            if info.get('prerequisites'):
                kg_context += f"  前置知识: {', '.join(info['prerequisites'])}\n"
            if info.get('related'):
                kg_context += f"  相关知识: {', '.join(info['related'])}\n"
            if info.get('applications'):
                kg_context += f"  应用场景: {', '.join(info['applications'])}\n"
            if info.get('description'):
                kg_context += f"  描述: {info['description']}\n"
        kg_context += "\n"
    
    intent_instructions = {
        'concept_understanding': '请清晰定义概念，给出核心特点和实际例子，帮助学生理解基本概念。',
        'principle_analysis': '请深入解释背后的原理，包括数学公式和物理意义，给出推导过程。',
        'method_steps': '请提供详细的操作步骤，分点说明，便于学生按步骤学习和实践。',
        'comparison_analysis': '请列出异同点，使用对比表形式，帮助学生区分相似概念。',
        'problem_solving': '请分析问题原因，提供多种解决方案，并说明每种方案的适用场景。',
        'application_scenario': '请列举实际应用场景，说明该知识点在工程实践中的具体用途。',
        'knowledge_review': '请总结该知识点的重点内容，列出关键考点和复习建议。',
        'general_question': '请根据问题内容灵活回答，保持专业性和准确性。'
    }
    
    base_prompt = f"""
你是灵智尚人，通信工程专家助手。

【用户意图】
类型：{intent['name']}（置信度: {intent['confidence']}）
{intent_instructions.get(intent['intent'], intent_instructions['general_question'])}

【知识图谱上下文】
{kg_context}

要求：
1. 优先使用知识图谱中的信息回答
2. 回答要专业、准确，符合通信工程领域规范
3. 如果涉及多个知识点，说明它们之间的关联关系
"""
    
    if mode == 'deep':
        base_prompt += """
4. 深入分析问题，给出多个角度的解释
5. 如果需要，分点说明
6. 提供实用的建议或解决方案
"""
    else:
        base_prompt += """
4. 回答要简洁明了
5. 控制回答长度在300字以内
"""
    
    return base_prompt

@public_api.route('/v1/ask', methods=['POST'])
def api_ask():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    data = request.json
    question = data.get('question', '')
    mode = data.get('mode', 'fast')
    conversation_history = data.get('history', [])
    
    if not question:
        return jsonify({'success': False, 'error': '请输入问题'}), 400
    
    system_prompt = generate_system_prompt(question, mode)
    temperature = 0.85 if mode == 'deep' else 0.6
    max_tokens = 4000 if mode == 'deep' else 2000
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        if msg.get('role') == 'user':
            messages.append({"role": "user", "content": msg.get('content', '')})
        elif msg.get('role') == 'assistant':
            messages.append({"role": "assistant", "content": msg.get('content', '')})
    messages.append({"role": "user", "content": question})
    
    payload = {"model": MODEL_NAME, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False}
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and result["choices"]:
                answer = result["choices"][0]["message"]["content"].strip()
                answer = re.sub(r'\n{3,}', '\n\n', answer)
                return jsonify({'success': True, 'answer': answer, 'mode': mode, 'intent': identify_intent(question)})
            else:
                return jsonify({'success': False, 'error': 'API返回格式错误'}), 500
        else:
            return jsonify({'success': False, 'error': f'API请求失败: {response.status_code}'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': '请求超时'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'请求出错: {str(e)}'}), 500

@public_api.route('/v1/knowledge-detail', methods=['GET'])
def api_knowledge_detail():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    keyword = request.args.get('keyword', '')
    
    if not keyword:
        return jsonify({'success': False, 'error': '请指定关键词'}), 400
    
    results = search_knowledge_graph_full(keyword)
    
    return jsonify({'success': True, 'results': results, 'total': len(results)})

@public_api.route('/v1/scenarios', methods=['GET'])
def api_get_scenarios():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    return jsonify({'success': True, 'scenarios': SCENARIOS, 'total': len(SCENARIOS)})

@public_api.route('/v1/scenarios/<int:scenario_id>', methods=['GET'])
def api_get_scenario(scenario_id):
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    scenario = next((s for s in SCENARIOS if s['id'] == scenario_id), None)
    
    if not scenario:
        return jsonify({'success': False, 'error': '场景不存在'}), 404
    
    return jsonify({'success': True, 'scenario': scenario})

@public_api.route('/v1/scenarios/chat', methods=['POST'])
def api_scenario_chat():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    data = request.json
    scenario_id = data.get('scenario_id', 1)
    message = data.get('message', '')
    conversation_history = data.get('history', [])
    
    if not message:
        return jsonify({'success': False, 'error': '请输入消息'}), 400
    
    scenario = next((s for s in SCENARIOS if s['id'] == scenario_id), None)
    if not scenario:
        return jsonify({'success': False, 'error': '场景不存在'}), 404
    
    scenario_context = f"""
【当前剧情场景】
场景名称：{scenario['title']}
场景描述：{scenario['description']}
难度：{scenario['difficulty']}

目标任务：
"""
    for i, task in enumerate(scenario['tasks'], 1):
        scenario_context += f"{i}. {task}\n"
    
    system_prompt = f"""
你是灵智尚人，通信工程专业的职业导师。现在正在进行剧情演绎，帮助学生模拟未来的工作场景。

你的角色是：
- 引导学生完成剧情任务
- 在学生遇到困难时提供专业指导
- 对学生的解决方案给出客观评价
- 结合实际工作场景给出建议

{scenario_context}

要求：
1. 引导式教学，不要直接给出答案
2. 结合通信工程专业知识
3. 保持对话的连贯性和代入感
4. 鼓励学生独立思考和动手实践
"""
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history:
        if msg.get('role') == 'user':
            messages.append({"role": "user", "content": msg.get('content', '')})
        elif msg.get('role') == 'assistant':
            messages.append({"role": "assistant", "content": msg.get('content', '')})
    messages.append({"role": "user", "content": message})
    
    payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.8, "max_tokens": 4000, "stream": False}
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and result["choices"]:
                answer = result["choices"][0]["message"]["content"].strip()
                answer = re.sub(r'\n{3,}', '\n\n', answer)
                return jsonify({'success': True, 'answer': answer, 'scenario': scenario['title']})
            else:
                return jsonify({'success': False, 'error': 'API返回格式错误'}), 500
        else:
            return jsonify({'success': False, 'error': f'API请求失败: {response.status_code}'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': '请求超时'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'请求出错: {str(e)}'}), 500

@public_api.route('/v1/learning-records', methods=['POST'])
def api_add_learning_record():
    success, error_response, status = authenticate_api_key()
    if not success:
        return error_response, status
    
    data = request.json
    student_name = data.get('student_name', '')
    activity_type = data.get('activity_type', '')
    knowledge_point = data.get('knowledge_point', '')
    score = data.get('score')
    is_correct = data.get('is_correct', False)
    
    if not all([student_name, activity_type]):
        return jsonify({'success': False, 'error': '缺少必要参数'}), 400
    
    records = load_learning_records()
    if student_name not in records:
        records[student_name] = []
    
    records[student_name].append({
        'activity_type': activity_type,
        'knowledge_point': knowledge_point,
        'score': score,
        'is_correct': is_correct,
        'timestamp': datetime.now().isoformat(),
        'date': datetime.now().strftime('%Y-%m-%d')
    })
    
    if len(records[student_name]) > 1000:
        records[student_name] = records[student_name][-1000:]
    
    save_learning_records(records)
    
    return jsonify({'success': True, 'message': '学习记录已添加'})