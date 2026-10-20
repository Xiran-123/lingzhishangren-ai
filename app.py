from flask import Flask, render_template, request, jsonify, Response, session, send_from_directory, redirect, url_for
import requests
import base64
import re
import json
import os
import secrets
import uuid
import sys
import time
import random
import threading
import hashlib
import difflib
from datetime import datetime, timedelta
from typing import Dict, List
from werkzeug.utils import secure_filename

# Windows 控制台 GBK 编码打印 emoji 会崩（UnicodeEncodeError），统一改为 UTF-8 并替换不可编码字符
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pptx import Presentation
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

app = Flask(__name__)
# 优先使用环境变量（docker-compose 已配置），其次使用固定默认值，避免多 worker 间 session 签名不一致
app.secret_key = os.environ.get('SECRET_KEY', 'lingzhishangren-fixed-secret-key-2024')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# ====================== SiliconFlow API 配置 ======================
def _load_siliconflow_key():
    """密钥读取优先级：环境变量 SILICONFLOW_API_KEY > api_key.local 文件 > 硬编码默认值。"""
    key = os.environ.get('SILICONFLOW_API_KEY', '').strip()
    if key:
        return key
    if getattr(sys, 'frozen', False):
        key_file = os.path.join(os.path.dirname(sys.executable), 'api_key.local')
    else:
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_key.local')
    try:
        with open(key_file, 'r', encoding='utf-8') as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    # 硬编码默认密钥（比赛演示用）
    return 'sk-sdfaoxkrbsmmnueekypiqjgxtcrscmrmajrzvtdjkgnjieyi'

API_KEY = _load_siliconflow_key()
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_KIMI  = "Pro/moonshotai/Kimi-K2.6"
MODEL_FLASH = "deepseek-ai/DeepSeek-V4.1-Flash"
MODEL_NAME  = MODEL_FLASH  # 默认走 Flash，只有剧情 AI 对话 (is_scenario=True) 保留 Kimi

# ====================== 访问密码配置 ======================
ACCESS_PASSWORD = "tongxin2024"  # 可以改成你想要的密码

# ====================== 老师账号配置 ======================
# 允许登录的老师账号列表（用户名: 密码）
TEACHER_ACCOUNTS = {
    "teacher1": "123456",
    "teacher2": "123456",
    "teacher3": "123456",
    "teacher4": "123456"
}

# ====================== 知识库配置 ======================
KNOWLEDGE_FILE = "knowledge.txt"
SEARCH_LOG_FILE = "data/search_logs.json"
STUDENTS_FILE = "data/students.json"  # 持久化到挂载的data目录（容器重建/重新部署不丢）
CLASSES_FILE = "data/classes.json"
NOTIFICATIONS_FILE = "data/notifications.json"
UPLOAD_HISTORY_FILE = "data/upload_history.json"
WRONG_QUESTIONS_FILE = "data/wrong_questions.json"
LEARNING_RECORDS_FILE = "data/learning_records.json"
PPT_METADATA_FILE = "data/ppt_metadata.json"  # PPT课件元数据（持久化到挂载的data目录）
HOMEWORK_FILE = "data/homework.json"  # 教师发布的作业
HOMEWORK_SUBMISSIONS_FILE = "data/homework_submissions.json"  # 学生作业提交记录
SELF_ASSESSMENT_FILE = "data/student_self_assessment.json"  # 学生自评画像
INTERVIEW_CASES_FILE = "data/interview_cases.json"  # 面试案例知识库
INTERVIEW_RECORDS_FILE = "data/interview_records.json"  # 模拟面试记录
AVATAR_DIR = "data/avatars"  # 用户头像（持久化到挂载的data目录）
ALLOWED_AVATAR_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# ====================== 文件上传配置 ======================
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'bmp',  # 图片
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt',  # 文档
    'mp4', 'avi', 'mov', 'mkv', 'webm',  # 视频
    'zip', 'rar', '7z'  # 压缩包
}

# 确保上传文件夹和持久化数据目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)


def _migrate_to_data_dir(data_path: str):
    """启动时将镜像根目录下的旧数据迁移到持久化的 data/ 目录（容器重建不丢失）"""
    legacy_path = os.path.basename(data_path)
    if not os.path.exists(data_path) and os.path.exists(legacy_path):
        try:
            import shutil
            shutil.move(legacy_path, data_path)
            print(f"已迁移历史数据: {legacy_path} -> {data_path}")
        except Exception as e:
            print(f"迁移 {legacy_path} 失败: {e}")


_migrate_to_data_dir(UPLOAD_HISTORY_FILE)
_migrate_to_data_dir(PPT_METADATA_FILE)
_migrate_to_data_dir(STUDENTS_FILE)
_migrate_to_data_dir(CLASSES_FILE)
_migrate_to_data_dir(NOTIFICATIONS_FILE)
_migrate_to_data_dir(WRONG_QUESTIONS_FILE)
_migrate_to_data_dir(LEARNING_RECORDS_FILE)
_migrate_to_data_dir(SEARCH_LOG_FILE)

# ====================== 能力评估指标 ======================
# 12维能力维度配置（对应岗位能力雷达图）
COMPETENCE_AREAS = [
    {"id": "signal_system", "name": "信号与系统", "weight": 0.10, "category": "理论基础"},
    {"id": "communication_principle", "name": "通信原理", "weight": 0.12, "category": "理论基础"},
    {"id": "digital_signal", "name": "数字信号处理", "weight": 0.10, "category": "理论基础"},
    {"id": "network_protocol", "name": "网络协议", "weight": 0.08, "category": "理论基础"},
    {"id": "modulation", "name": "调制技术", "weight": 0.08, "category": "专业核心"},
    {"id": "rf_engineering", "name": "射频工程", "weight": 0.08, "category": "专业核心"},
    {"id": "antenna_design", "name": "天线设计", "weight": 0.06, "category": "专业核心"},
    {"id": "troubleshooting", "name": "故障排查", "weight": 0.10, "category": "工程实践"},
    {"id": "equipment_operation", "name": "设备操作", "weight": 0.08, "category": "工程实践"},
    {"id": "safety_awareness", "name": "安全意识", "weight": 0.08, "category": "工程伦理"},
    {"id": "innovation", "name": "创新思维", "weight": 0.06, "category": "综合素质"},
    {"id": "teamwork", "name": "团队协作", "weight": 0.06, "category": "综合素质"}
]

# 关键词匹配（用于分析学生提问）
COMPETENCE_KEYWORDS = {
    "signal_system": ["傅里叶", "拉普拉斯", "卷积", "时域", "频域", "Z变换", "差分方程", "系统响应"],
    "communication_principle": ["香农", "信道容量", "编码", "译码", "误码率", "信噪比", "信道", "带宽"],
    "digital_signal": ["采样", "量化", "编码", "滤波器", "FFT", "频谱", "噪声", "失真"],
    "network_protocol": ["TCP", "IP", "UDP", "HTTP", "协议", "路由", "交换机", "路由器"],
    "modulation": ["ASK", "FSK", "PSK", "QAM", "调制", "解调", "星座图", "相位"],
    "rf_engineering": ["射频", "功率", "增益", "衰减", "阻抗", "匹配", "电磁波", "传播"],
    "antenna_design": ["天线", "方向图", "极化", "波束", "阵列", "MIMO", "波束赋形"],
    "troubleshooting": ["故障", "排查", "问题", "解决", "调试", "修复", "错误", "异常"],
    "equipment_operation": ["设备", "仪器", "操作", "示波器", "频谱仪", "配置", "调试", "维护"],
    "safety_awareness": ["安全", "防护", "接地", "防雷", "高压", "规范", "标准", "应急"],
    "innovation": ["创新", "优化", "改进", "方案", "设计", "思路", "新方法"],
    "teamwork": ["协作", "沟通", "团队", "配合", "协调", "分享", "讨论"]
}

# ====================== 岗位胜任力指标体系 ======================
# 5大维度：技术能力、沟通协作、项目管理、安全伦理、创新思维
COMPETENCY_DIMENSIONS = {
    "technical": {
        "id": "technical",
        "name": "技术能力",
        "icon": "🔧",
        "color": "#52c41a",
        "description": "掌握通信工程核心技术，具备独立完成专业任务的能力",
        "weight": 0.30,
        "sub_dimensions": ["理论基础", "专业核心", "工程实践"],
        "mapped_areas": ["signal_system", "communication_principle", "digital_signal",
                         "network_protocol", "modulation", "rf_engineering",
                         "antenna_design", "equipment_operation"]
    },
    "communication": {
        "id": "communication",
        "name": "沟通协作",
        "icon": "💬",
        "color": "#1890ff",
        "description": "具备良好的团队沟通、跨部门协作和技术文档撰写能力",
        "weight": 0.15,
        "sub_dimensions": ["口头表达", "书面表达", "团队协作", "跨部门沟通"],
        "mapped_areas": ["teamwork"],
        "keywords": ["沟通", "表达", "协作", "汇报", "交流", "协调", "会议", "文档", "报告", "演示"]
    },
    "project_management": {
        "id": "project_management",
        "name": "项目管理",
        "icon": "📋",
        "color": "#fa8c16",
        "description": "具备工程项目规划、进度管控、资源协调和风险管理能力",
        "weight": 0.20,
        "sub_dimensions": ["需求分析", "进度规划", "资源管理", "风险管控", "质量保障"],
        "mapped_areas": ["troubleshooting", "equipment_operation"],
        "keywords": ["项目", "进度", "计划", "需求", "风险", "预算", "资源", "里程碑", "交付", "验收", "排期", "管控"]
    },
    "safety_ethics": {
        "id": "safety_ethics",
        "name": "安全伦理",
        "icon": "🛡️",
        "color": "#eb2f96",
        "description": "严格遵守安全规范和职业伦理，保障工程质量和人员安全",
        "weight": 0.20,
        "sub_dimensions": ["安全意识", "操作规范", "应急处置", "职业伦理"],
        "mapped_areas": ["safety_awareness"],
        "keywords": ["安全", "规范", "防护", "应急", "伦理", "合规", "责任", "风险", "检查", "预案"]
    },
    "innovation": {
        "id": "innovation",
        "name": "创新思维",
        "icon": "💡",
        "color": "#722ed1",
        "description": "具备问题分析、方案创新和持续优化的能力",
        "weight": 0.15,
        "sub_dimensions": ["问题分析", "方案设计", "技术创新", "持续改进"],
        "mapped_areas": ["innovation"],
        "keywords": ["创新", "优化", "改进", "设计", "方案", "思路", "分析", "提升", "突破", "新方法"]
    }
}

# 岗位-胜任力维度映射（不同岗位侧重不同维度）
POSITION_COMPETENCY_MAP = {
    "基站工程师": {
        "technical": 0.35, "safety_ethics": 0.25, "project_management": 0.15,
        "communication": 0.10, "innovation": 0.15
    },
    "网络优化工程师": {
        "technical": 0.35, "innovation": 0.20, "project_management": 0.20,
        "communication": 0.15, "safety_ethics": 0.10
    },
    "核心网工程师": {
        "technical": 0.30, "project_management": 0.25, "innovation": 0.20,
        "safety_ethics": 0.15, "communication": 0.10
    },
    "传输工程师": {
        "technical": 0.30, "safety_ethics": 0.25, "project_management": 0.20,
        "communication": 0.15, "innovation": 0.10
    },
    "网络安全工程师": {
        "safety_ethics": 0.30, "technical": 0.25, "innovation": 0.20,
        "project_management": 0.15, "communication": 0.10
    },
    "FPGA工程师": {
        "technical": 0.40, "innovation": 0.25, "project_management": 0.15,
        "safety_ethics": 0.10, "communication": 0.10
    }
}

# ====================== 知识图谱配置 ======================
# 知识点及其关联关系
KNOWLEDGE_GRAPH = {
    "傅里叶变换": {
        "category": "理论基础",
        "difficulty": 3,
        "prerequisites": ["时域频域概念"],
        "related": ["拉普拉斯变换", "Z变换", "FFT", "频谱分析"],
        "applications": ["信号分析", "滤波器设计", "调制解调"],
        "description": "傅里叶变换是将时域信号转换为频域表示的数学工具，揭示了信号的频率成分。它是信号处理和通信系统的核心数学基础。",
        "key_points": [
            "正变换：X(f) = ∫x(t)e^(-j2πft)dt",
            "逆变换：x(t) = ∫X(f)e^(j2πft)df",
            "时域连续→频域连续，时域离散→频域周期",
            "满足线性、时移、频移、卷积等性质"
        ],
        "formula": "X(ω) = ∫_{-∞}^{+∞} x(t)·e^{-jωt} dt"
    },
    "奈奎斯特采样定理": {
        "category": "理论基础",
        "difficulty": 2,
        "prerequisites": ["时域频域概念"],
        "related": ["采样率", "混叠", "抗混叠滤波器"],
        "applications": ["ADC设计", "音频处理"],
        "description": "奈奎斯特采样定理由奈奎斯特和香农提出，指出为了能够从采样信号中完美重建原始连续信号，采样频率必须大于信号最高频率的两倍。",
        "key_points": [
            "采样频率 fs > 2fmax（奈奎斯特率）",
            "采样不足会产生混叠（aliasing）",
            "实际应用中通常取 fs = 2.5~3 倍 fmax",
            "抗混叠滤波器用于限制信号带宽"
        ],
        "formula": "f_s > 2·f_{max}"
    },
    "卷积": {
        "category": "理论基础",
        "difficulty": 3,
        "prerequisites": ["线性时不变系统"],
        "related": ["系统响应", "滤波器"],
        "applications": ["信号处理", "系统分析"],
        "description": "卷积是描述线性时不变系统输入输出关系的数学运算。系统的输出等于输入信号与系统单位冲激响应的卷积。",
        "key_points": [
            "y(t) = x(t) * h(t) = ∫x(τ)h(t-τ)dτ",
            "时域卷积 ↔ 频域相乘",
            "卷积满足交换律、结合律、分配律",
            "是滤波器设计的核心数学工具"
        ],
        "formula": "y(t) = x(t) * h(t) = ∫_{-∞}^{+∞} x(τ)·h(t-τ) dτ"
    },
    "信噪比SNR": {
        "category": "理论基础",
        "difficulty": 2,
        "prerequisites": ["信号功率", "噪声功率"],
        "related": ["误码率", "信道容量", "香农公式"],
        "applications": ["通信系统设计", "链路预算"],
        "description": "信噪比（SNR）是信号功率与噪声功率的比值，是衡量通信系统质量的重要指标。信噪比越高，通信质量越好。",
        "key_points": [
            "SNR = P_signal / P_noise",
            "常用分贝表示：SNR(dB) = 10·log10(SNR)",
            "信噪比直接影响误码率",
            "是信道容量计算的核心参数"
        ],
        "formula": "SNR_{dB} = 10·log_{10}(\\frac{P_{signal}}{P_{noise}})"
    },
    "2ASK调制": {
        "category": "调制技术",
        "difficulty": 2,
        "prerequisites": ["载波", "基带信号"],
        "related": ["2FSK", "2PSK", "BPSK"],
        "applications": ["低速数据传输", "遥控系统"],
        "description": "2ASK（二进制幅移键控）是最简单的数字调制方式，通过改变载波的幅度来传输二进制数据。通常用载波存在表示'1'，载波不存在表示'0'。",
        "key_points": [
            "通过载波幅度变化传输数字信息",
            "实现简单，成本低",
            "抗噪声性能差，易受衰落影响",
            "频谱效率较低，适用于低速通信"
        ],
        "formula": "s(t) = \\begin{cases} A\\cos(\\omega_c t) & \\text{'1'码} \\\\ 0 & \\text{'0'码} \\end{cases}"
    },
    "2FSK调制": {
        "category": "调制技术",
        "difficulty": 2,
        "prerequisites": ["载波", "频率切换"],
        "related": ["2ASK", "2PSK", "GFSK"],
        "applications": ["无线传感网", "RFID"],
        "description": "2FSK（二进制频移键控）通过改变载波频率来传输二进制数据。用两种不同频率分别表示'0'和'1'，具有较好的抗噪声性能。",
        "key_points": [
            "通过载波频率变化传输数字信息",
            "抗噪声性能优于2ASK",
            "实现相对简单，成本适中",
            "带宽利用率较低，适合中低速通信"
        ],
        "formula": "s(t) = \\begin{cases} A\\cos(\\omega_1 t) & \\text{'1'码} \\\\ A\\cos(\\omega_2 t) & \\text{'0'码} \\end{cases}"
    },
    "QAM调制": {
        "category": "调制技术",
        "difficulty": 4,
        "prerequisites": ["PSK", "ASK", "星座图"],
        "related": ["16QAM", "64QAM", "256QAM"],
        "applications": ["4G/5G通信", "WiFi", "数字电视"],
        "description": "QAM（正交幅度调制）结合了幅度调制和相位调制，通过改变载波的幅度和相位来传输更多比特信息，具有很高的频谱效率。",
        "key_points": [
            "同时利用幅度和相位携带信息",
            "频谱效率高，适合高速通信",
            "星座图直观展示调制状态",
            "高阶QAM对信噪比要求更高"
        ],
        "formula": "s(t) = A_I\\cos(\\omega_c t) - A_Q\\sin(\\omega_c t)"
    },
    "OFDM": {
        "category": "调制技术",
        "difficulty": 5,
        "prerequisites": ["FFT", "多载波", "循环前缀"],
        "related": ["MIMO", "信道估计"],
        "applications": ["4G LTE", "5G NR", "WiFi6"],
        "description": "OFDM（正交频分复用）是一种多载波调制技术，将高速数据流分解为多个低速子流，在相互正交的子载波上并行传输，具有抗多径衰落能力强、频谱效率高等优点。",
        "key_points": [
            "多载波并行传输，子载波正交",
            "抗多径衰落能力强",
            "频谱效率高，节省带宽",
            "FFT/IFFT实现调制解调",
            "循环前缀（CP）对抗码间干扰"
        ],
        "formula": "s(t) = \\sum_{k=0}^{N-1} X_k \\cdot e^{j2\\pi \\frac{k}{T} t}"
    },
    "故障排查": {
        "category": "工程实践",
        "difficulty": 3,
        "prerequisites": ["通信原理", "设备操作"],
        "related": ["告警分析", "性能监控", "日志分析"],
        "applications": ["网络优化", "设备维护"],
        "description": "故障排查是通信工程师的核心技能，指通过系统性的方法分析和解决通信网络中的各种故障问题，包括告警分析、性能监控、日志分析等手段。",
        "key_points": [
            "告警分级与处理流程",
            "性能指标监控与基线对比",
            "日志分析与问题定位",
            "分层排查法：物理层→数据链路层→网络层→应用层",
            "故障复盘与知识库积累"
        ],
        "formula": "MTTR = \\frac{\\sum 故障恢复时间}{故障次数}"
    },
    "链路预算": {
        "category": "工程实践",
        "difficulty": 4,
        "prerequisites": ["路径损耗", "天线增益", "发射功率"],
        "related": ["覆盖规划", "容量规划"],
        "applications": ["基站规划", "网络设计"],
        "description": "链路预算是计算无线通信链路中所有增益和损耗的过程，用于确定接收端信号强度是否满足通信要求，是无线网络规划设计的核心工具。",
        "key_points": [
            "接收功率 = 发射功率 + 发射天线增益 + 接收天线增益 - 路径损耗 - 其他损耗",
            "需考虑衰落余量、穿透损耗、干扰余量",
            "上下行链路平衡设计",
            "边缘覆盖率与容量的权衡"
        ],
        "formula": "P_r = P_t + G_t + G_r - L_p - L_{other}"
    }
}

# ====================== 互动式练习题库 ======================
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
                "B. 时域平移对应频域平移",
                "C. 时域微分对应频域乘以jω",
                "D. 时域积分对应频域乘以jω"
            ],
            "answer": "C",
            "analysis": "傅里叶变换的微分性质：时域微分对应频域乘以jω。时域卷积对应频域相乘，时域平移对应频域相移。"
        },
        {
            "id": "ft_003",
            "type": "fill",
            "difficulty": 2,
            "question": "傅里叶变换的逆变换公式为：x(t) = ______",
            "answer": "∫X(f)e^(j2πft)df",
            "analysis": "傅里叶逆变换公式：x(t) = ∫_{-∞}^{+∞} X(f)·e^(j2πft) df"
        },
        {
            "id": "ft_004",
            "type": "short",
            "difficulty": 3,
            "question": "简述傅里叶变换在通信系统中的应用。",
            "answer": "傅里叶变换在通信系统中有广泛应用，包括：1) 频谱分析：分析信号的频率成分；2) 滤波器设计：设计低通、高通等滤波器；3) 调制解调：理解调制信号的频谱特性；4) 信道分析：分析信道对信号的影响。",
            "analysis": "傅里叶变换是信号处理和通信系统的数学基础，其核心应用包括频谱分析、滤波器设计、调制解调等。"
        }
    ],
    "奈奎斯特采样定理": [
        {
            "id": "nyq_001",
            "type": "choice",
            "difficulty": 1,
            "question": "奈奎斯特采样定理要求采样频率必须满足什么条件？",
            "options": [
                "A. fs > fmax",
                "B. fs > 2fmax",
                "C. fs = fmax",
                "D. fs < 2fmax"
            ],
            "answer": "B",
            "analysis": "奈奎斯特采样定理指出，为了能够从采样信号中完美重建原始信号，采样频率必须大于信号最高频率的两倍。"
        },
        {
            "id": "nyq_002",
            "type": "choice",
            "difficulty": 2,
            "question": "当采样频率不足时，会产生什么现象？",
            "options": [
                "A. 信号增强",
                "B. 混叠（aliasing）",
                "C. 信噪比提高",
                "D. 带宽扩展"
            ],
            "answer": "B",
            "analysis": "当采样频率低于奈奎斯特率时，高频成分会被错误地映射到低频区域，产生混叠现象。"
        },
        {
            "id": "nyq_003",
            "type": "fill",
            "difficulty": 2,
            "question": "若信号最高频率为10kHz，则最小采样频率应为______kHz。",
            "answer": "20",
            "analysis": "根据奈奎斯特采样定理，fs > 2fmax = 2 × 10kHz = 20kHz"
        }
    ],
    "信噪比SNR": [
        {
            "id": "snr_001",
            "type": "choice",
            "difficulty": 1,
            "question": "信噪比（SNR）的定义是什么？",
            "options": [
                "A. 信号频率与噪声频率之比",
                "B. 信号功率与噪声功率之比",
                "C. 信号幅度与噪声幅度之比",
                "D. 信号带宽与噪声带宽之比"
            ],
            "answer": "B",
            "analysis": "信噪比是信号功率与噪声功率的比值，是衡量通信质量的重要指标。"
        },
        {
            "id": "snr_002",
            "type": "choice",
            "difficulty": 2,
            "question": "信噪比用分贝表示的公式是？",
            "options": [
                "A. SNR(dB) = 20·log10(SNR)",
                "B. SNR(dB) = 10·log10(SNR)",
                "C. SNR(dB) = log2(SNR)",
                "D. SNR(dB) = log10(SNR)"
            ],
            "answer": "B",
            "analysis": "功率比值用分贝表示时使用10·log10，电压/幅度比值使用20·log10。"
        },
        {
            "id": "snr_003",
            "type": "fill",
            "difficulty": 2,
            "question": "若SNR=1000，则SNR(dB)=______dB。",
            "answer": "30",
            "analysis": "SNR(dB) = 10·log10(1000) = 10 × 3 = 30 dB"
        }
    ],
    "2ASK调制": [
        {
            "id": "ask_001",
            "type": "choice",
            "difficulty": 1,
            "question": "2ASK调制是通过什么方式传输数字信息的？",
            "options": [
                "A. 改变载波频率",
                "B. 改变载波幅度",
                "C. 改变载波相位",
                "D. 同时改变幅度和相位"
            ],
            "answer": "B",
            "analysis": "2ASK（二进制幅移键控）通过改变载波的幅度来传输二进制数据，通常用载波存在表示'1'，载波不存在表示'0'。"
        },
        {
            "id": "ask_002",
            "type": "choice",
            "difficulty": 2,
            "question": "以下关于2ASK调制的特点，哪一项是正确的？",
            "options": [
                "A. 抗噪声性能最好",
                "B. 实现简单，成本低",
                "C. 频谱效率最高",
                "D. 适合高速通信"
            ],
            "answer": "B",
            "analysis": "2ASK的主要优点是实现简单、成本低，但抗噪声性能较差，频谱效率较低，适合低速通信。"
        }
    ],
    "2FSK调制": [
        {
            "id": "fsk_001",
            "type": "choice",
            "difficulty": 1,
            "question": "2FSK调制是通过什么方式传输数字信息的？",
            "options": [
                "A. 改变载波频率",
                "B. 改变载波幅度",
                "C. 改变载波相位",
                "D. 同时改变幅度和相位"
            ],
            "answer": "A",
            "analysis": "2FSK（二进制频移键控）通过改变载波频率来传输二进制数据，用两种不同频率分别表示'0'和'1'。"
        },
        {
            "id": "fsk_002",
            "type": "choice",
            "difficulty": 2,
            "question": "2FSK与2ASK相比，主要优势是什么？",
            "options": [
                "A. 实现更简单",
                "B. 抗噪声性能更好",
                "C. 频谱效率更高",
                "D. 占用带宽更窄"
            ],
            "answer": "B",
            "analysis": "2FSK的抗噪声性能优于2ASK，因为频率变化比幅度变化更不容易受到噪声干扰。"
        }
    ],
    "QAM调制": [
        {
            "id": "qam_001",
            "type": "choice",
            "difficulty": 2,
            "question": "QAM调制结合了哪两种调制方式？",
            "options": [
                "A. ASK和FSK",
                "B. ASK和PSK",
                "C. FSK和PSK",
                "D. FDM和TDM"
            ],
            "answer": "B",
            "analysis": "QAM（正交幅度调制）结合了幅度调制（ASK）和相位调制（PSK），通过同时改变载波的幅度和相位来传输更多比特信息。"
        },
        {
            "id": "qam_002",
            "type": "choice",
            "difficulty": 3,
            "question": "以下哪种QAM调制方式的频谱效率最高？",
            "options": [
                "A. 4QAM",
                "B. 16QAM",
                "C. 64QAM",
                "D. 256QAM"
            ],
            "answer": "D",
            "analysis": "高阶QAM的频谱效率更高，256QAM每个符号携带8比特信息，比64QAM（6比特）、16QAM（4比特）、4QAM（2比特）都高。"
        }
    ],
    "OFDM": [
        {
            "id": "ofdm_001",
            "type": "choice",
            "difficulty": 3,
            "question": "OFDM的全称是什么？",
            "options": [
                "A. 正交频分复用",
                "B. 正交幅度调制",
                "C. 正交相位键控",
                "D. 正交码分多址"
            ],
            "answer": "A",
            "analysis": "OFDM（Orthogonal Frequency Division Multiplexing）即正交频分复用，是一种多载波调制技术。"
        },
        {
            "id": "ofdm_002",
            "type": "choice",
            "difficulty": 4,
            "question": "OFDM使用循环前缀（CP）的主要目的是什么？",
            "options": [
                "A. 提高频谱效率",
                "B. 对抗码间干扰和载波间干扰",
                "C. 降低峰均比",
                "D. 简化调制解调"
            ],
            "answer": "B",
            "analysis": "循环前缀的主要作用是对抗多径衰落引起的码间干扰（ISI）和载波间干扰（ICI）。"
        }
    ],
    "卷积": [
        {
            "id": "conv_001",
            "type": "choice",
            "difficulty": 2,
            "question": "线性时不变系统的输出与输入的关系是什么？",
            "options": [
                "A. 输出等于输入的导数",
                "B. 输出等于输入与系统冲激响应的卷积",
                "C. 输出等于输入的积分",
                "D. 输出等于输入乘以常数"
            ],
            "answer": "B",
            "analysis": "对于线性时不变系统，输出等于输入信号与系统单位冲激响应的卷积。"
        },
        {
            "id": "conv_002",
            "type": "choice",
            "difficulty": 3,
            "question": "时域卷积对应频域的什么运算？",
            "options": [
                "A. 卷积",
                "B. 相乘",
                "C. 相加",
                "D. 相除"
            ],
            "answer": "B",
            "analysis": "傅里叶变换的卷积定理：时域卷积对应频域相乘，时域相乘对应频域卷积。"
        }
    ],
    "故障排查": [
        {
            "id": "fault_001",
            "type": "choice",
            "difficulty": 2,
            "question": "故障排查的分层排查法通常按照什么顺序进行？",
            "options": [
                "A. 应用层→网络层→数据链路层→物理层",
                "B. 物理层→数据链路层→网络层→应用层",
                "C. 网络层→应用层→物理层→数据链路层",
                "D. 数据链路层→物理层→应用层→网络层"
            ],
            "answer": "B",
            "analysis": "分层排查法通常从底层到上层：物理层→数据链路层→网络层→应用层，这样可以快速定位问题所在层次。"
        },
        {
            "id": "fault_002",
            "type": "short",
            "difficulty": 3,
            "question": "简述通信网络故障排查的基本步骤。",
            "answer": "故障排查基本步骤：1) 收集信息：查看告警、性能指标、日志；2) 定位范围：确定故障影响范围和严重程度；3) 分层排查：从物理层到应用层逐步排查；4) 验证修复：实施解决方案并验证效果；5) 记录复盘：记录故障原因和解决方案。",
            "analysis": "系统性的故障排查流程包括信息收集、范围定位、分层排查、验证修复和记录复盘五个阶段。"
        }
    ],
    "链路预算": [
        {
            "id": "link_001",
            "type": "choice",
            "difficulty": 3,
            "question": "链路预算的主要目的是什么？",
            "options": [
                "A. 计算设备成本",
                "B. 确定接收端信号强度是否满足通信要求",
                "C. 优化网络拓扑",
                "D. 分配IP地址"
            ],
            "answer": "B",
            "analysis": "链路预算是计算无线通信链路中所有增益和损耗的过程，用于确定接收端信号强度是否满足通信要求。"
        },
        {
            "id": "link_002",
            "type": "fill",
            "difficulty": 3,
            "question": "链路预算的基本公式：接收功率 = 发射功率 + 发射天线增益 + 接收天线增益 - ______ - 其他损耗",
            "answer": "路径损耗",
            "analysis": "接收功率 = 发射功率 + 发射天线增益 + 接收天线增益 - 路径损耗 - 其他损耗"
        }
    ]
}

def get_exercises_by_knowledge(knowledge_point: str, count: int = 5) -> List[Dict]:
    """根据知识点获取练习题（含自定义题库）"""
    all_bank = get_all_exercises_with_custom()
    exercises = all_bank.get(knowledge_point, [])
    if count >= len(exercises):
        return exercises
    return random.sample(exercises, count)

def get_all_knowledge_points_with_exercises() -> List[str]:
    """获取有练习题的所有知识点（含自定义）"""
    all_bank = get_all_exercises_with_custom()
    return list(all_bank.keys())

# ====================== 知识图谱检索引擎 ======================
def build_knowledge_index():
    """构建知识图谱检索索引"""
    index = {
        'keyword_map': {},
        'category_map': {},
        'prerequisite_map': {},
        'related_map': {},
        'application_map': {}
    }
    
    for concept, info in KNOWLEDGE_GRAPH.items():
        keywords = [concept]
        keywords.extend(info.get('related', []))
        keywords.extend(info.get('applications', []))
        keywords.extend(info.get('prerequisites', []))
        
        for kw in keywords:
            if kw not in index['keyword_map']:
                index['keyword_map'][kw] = []
            index['keyword_map'][kw].append(concept)
        
        category = info.get('category', '未分类')
        if category not in index['category_map']:
            index['category_map'][category] = []
        index['category_map'][category].append(concept)
        
        for prereq in info.get('prerequisites', []):
            if prereq not in index['prerequisite_map']:
                index['prerequisite_map'][prereq] = []
            index['prerequisite_map'][prereq].append(concept)
        
        for related in info.get('related', []):
            if related not in index['related_map']:
                index['related_map'][related] = []
            index['related_map'][related].append(concept)
        
        for app in info.get('applications', []):
            if app not in index['application_map']:
                index['application_map'][app] = []
            index['application_map'][app].append(concept)
    
    return index

KNOWLEDGE_INDEX = build_knowledge_index()

def search_knowledge_graph(query: str) -> Dict:
    """搜索知识图谱，返回相关知识点及其关联"""
    query_lower = query.lower()
    results = {}
    matched_concepts = set()
    
    for keyword, concepts in KNOWLEDGE_INDEX['keyword_map'].items():
        if keyword.lower() in query_lower or query_lower in keyword.lower():
            for concept in concepts:
                matched_concepts.add(concept)
    
    if not matched_concepts:
        for concept in KNOWLEDGE_GRAPH:
            concept_lower = concept.lower()
            if query_lower in concept_lower or concept_lower in query_lower:
                matched_concepts.add(concept)
    
    if not matched_concepts:
        query_chars = list(query_lower)
        for concept in KNOWLEDGE_GRAPH:
            concept_lower = concept.lower()
            concept_chars = list(concept_lower)
            
            max_common = 0
            for i in range(len(query_chars) - 1):
                for j in range(len(concept_chars) - 1):
                    match_len = 0
                    while (i + match_len < len(query_chars) and 
                           j + match_len < len(concept_chars) and 
                           query_chars[i + match_len] == concept_chars[j + match_len]):
                        match_len += 1
                    max_common = max(max_common, match_len)
            
            if max_common >= 2:
                matched_concepts.add(concept)
    
    for concept in matched_concepts:
        info = KNOWLEDGE_GRAPH.get(concept, {})
        results[concept] = {
            'category': info.get('category', ''),
            'difficulty': info.get('difficulty', 0),
            'prerequisites': info.get('prerequisites', []),
            'related': info.get('related', []),
            'applications': info.get('applications', [])
        }
    
    return results

def get_related_knowledge(concept: str, depth: int = 2) -> Dict:
    """获取知识点的关联知识（递归查找）"""
    visited = set()
    result = {}
    
    def dfs(current_concept, current_depth):
        if current_depth > depth or current_concept in visited:
            return
        visited.add(current_concept)
        
        info = KNOWLEDGE_GRAPH.get(current_concept)
        if not info:
            return
        
        result[current_concept] = {
            'category': info.get('category', ''),
            'difficulty': info.get('difficulty', 0),
            'prerequisites': info.get('prerequisites', []),
            'related': info.get('related', []),
            'applications': info.get('applications', []),
            'depth': current_depth
        }
        
        for related in info.get('related', []):
            dfs(related, current_depth + 1)
        for prereq in info.get('prerequisites', []):
            dfs(prereq, current_depth + 1)
        for app in info.get('applications', []):
            dfs(app, current_depth + 1)
    
    dfs(concept, 0)
    return result

# 岗位能力要求模板
JOB_REQUIREMENTS = {
    "通信工程师": {
        "signal_system": 0.8, "communication_principle": 0.9, "digital_signal": 0.7,
        "network_protocol": 0.7, "modulation": 0.8, "rf_engineering": 0.7,
        "antenna_design": 0.6, "troubleshooting": 0.9, "equipment_operation": 0.8,
        "safety_awareness": 0.9, "innovation": 0.6, "teamwork": 0.7
    },
    "网络优化工程师": {
        "signal_system": 0.7, "communication_principle": 0.9, "digital_signal": 0.6,
        "network_protocol": 0.8, "modulation": 0.9, "rf_engineering": 0.8,
        "antenna_design": 0.7, "troubleshooting": 0.9, "equipment_operation": 0.7,
        "safety_awareness": 0.8, "innovation": 0.7, "teamwork": 0.7
    },
    "射频工程师": {
        "signal_system": 0.8, "communication_principle": 0.7, "digital_signal": 0.6,
        "network_protocol": 0.5, "modulation": 0.7, "rf_engineering": 0.95,
        "antenna_design": 0.9, "troubleshooting": 0.8, "equipment_operation": 0.8,
        "safety_awareness": 0.9, "innovation": 0.7, "teamwork": 0.6
    },
    "研发工程师": {
        "signal_system": 0.9, "communication_principle": 0.95, "digital_signal": 0.9,
        "network_protocol": 0.7, "modulation": 0.9, "rf_engineering": 0.7,
        "antenna_design": 0.6, "troubleshooting": 0.7, "equipment_operation": 0.6,
        "safety_awareness": 0.7, "innovation": 0.95, "teamwork": 0.7
    }
}

# ====================== 职业问卷配置 ======================
SURVEY_QUESTIONS = [
    {
        "id": "q1",
        "question": "你对以下哪个方向最感兴趣？",
        "type": "single",
        "options": [
            {"value": "rf", "label": "射频与天线设计", "icon": "📡", "weights": {"射频工程师": 3, "研发工程师": 1}},
            {"value": "network", "label": "网络规划与优化", "icon": "🌐", "weights": {"网络优化工程师": 3, "通信工程师": 1}},
            {"value": "algorithm", "label": "通信算法研发", "icon": "🔬", "weights": {"研发工程师": 3, "射频工程师": 1}},
            {"value": "field", "label": "现场工程与运维", "icon": "🔧", "weights": {"通信工程师": 3, "网络优化工程师": 1}}
        ]
    },
    {
        "id": "q2",
        "question": "你更喜欢哪类工作内容？",
        "type": "single",
        "options": [
            {"value": "hands_on", "label": "动手实操、调试设备", "icon": "🛠️", "weights": {"通信工程师": 3, "射频工程师": 2}},
            {"value": "analysis", "label": "数据分析与仿真", "icon": "📊", "weights": {"研发工程师": 3, "网络优化工程师": 2}},
            {"value": "design", "label": "系统方案设计", "icon": "📐", "weights": {"射频工程师": 2, "研发工程师": 2, "网络优化工程师": 1}},
            {"value": "maintenance", "label": "网络维护与排障", "icon": "🚨", "weights": {"网络优化工程师": 3, "通信工程师": 2}}
        ]
    },
    {
        "id": "q3",
        "question": "你觉得以下哪些课程对你来说比较轻松？（可多选）",
        "type": "multi",
        "options": [
            {"value": "signal", "label": "信号与系统", "icon": "📈", "weights": {"研发工程师": 2, "射频工程师": 1}},
            {"value": "em", "label": "电磁场与电磁波", "icon": "⚡", "weights": {"射频工程师": 3}},
            {"value": "network", "label": "计算机网络", "icon": "🔗", "weights": {"网络优化工程师": 3, "通信工程师": 1}},
            {"value": "dsp", "label": "数字信号处理", "icon": "🔢", "weights": {"研发工程师": 3, "射频工程师": 1}},
            {"value": "comm", "label": "通信原理", "icon": "📻", "weights": {"通信工程师": 2, "网络优化工程师": 1, "研发工程师": 1}},
            {"value": "embedded", "label": "嵌入式系统", "icon": "💾", "weights": {"通信工程师": 2, "研发工程师": 1}}
        ]
    },
    {
        "id": "q4",
        "question": "你希望未来的工作环境是？",
        "type": "single",
        "options": [
            {"value": "lab", "label": "实验室/研发中心", "icon": "🧪", "weights": {"研发工程师": 3, "射频工程师": 2}},
            {"value": "office", "label": "办公室/数据中心", "icon": "🏢", "weights": {"网络优化工程师": 2, "通信工程师": 1}},
            {"value": "field", "label": "现场/出差为主", "icon": "🚗", "weights": {"通信工程师": 3, "网络优化工程师": 1}},
            {"value": "mix", "label": "实验室+现场混合", "icon": "🔄", "weights": {"射频工程师": 2, "通信工程师": 2}}
        ]
    },
    {
        "id": "q5",
        "question": "你的职业发展倾向？",
        "type": "single",
        "options": [
            {"value": "expert", "label": "成为技术专家", "icon": "🎓", "weights": {"研发工程师": 3, "射频工程师": 2}},
            {"value": "manager", "label": "走向管理岗位", "icon": "👔", "weights": {"通信工程师": 2, "网络优化工程师": 2}},
            {"value": "engineer", "label": "资深工程师", "icon": "⚙️", "weights": {"射频工程师": 2, "通信工程师": 2, "网络优化工程师": 2}},
            {"value": "entrepreneur", "label": "创业/自由职业", "icon": "🚀", "weights": {"研发工程师": 1, "通信工程师": 1}}
        ]
    }
]

# 岗位详细描述
CAREER_DETAILS = {
    "通信工程师": {
        "icon": "🔧",
        "description": "负责通信网络设备的安装、调试、运维与故障排查",
        "skills": ["设备调试", "故障排查", "网络运维", "协议分析"],
        "salary_range": "8K-25K",
        "career_path": "初级工程师 → 高级工程师 → 技术主管 → 项目经理",
        "learning_focus": ["通信原理", "设备操作", "故障排查", "安全规范"]
    },
    "网络优化工程师": {
        "icon": "🌐",
        "description": "负责无线网络规划、优化与性能分析，提升网络质量",
        "skills": ["网络规划", "数据分析", "参数优化", "路测分析"],
        "salary_range": "10K-30K",
        "career_path": "优化工程师 → 高级优化师 → 网络规划专家",
        "learning_focus": ["通信原理", "调制技术", "网络协议", "数据分析"]
    },
    "射频工程师": {
        "icon": "📡",
        "description": "负责射频电路设计、天线开发与电磁仿真",
        "skills": ["射频设计", "天线仿真", "阻抗匹配", "EMC设计"],
        "salary_range": "12K-35K",
        "career_path": "射频工程师 → 高级射频工程师 → 射频专家",
        "learning_focus": ["射频工程", "天线设计", "电磁场", "调制技术"]
    },
    "研发工程师": {
        "icon": "🔬",
        "description": "负责通信系统算法研发、仿真验证与新产品开发",
        "skills": ["算法设计", "仿真建模", "编程开发", "专利撰写"],
        "salary_range": "15K-40K",
        "career_path": "研发工程师 → 高级研发 → 算法专家 → 技术总监",
        "learning_focus": ["信号与系统", "通信原理", "数字信号处理", "创新思维"]
    }
}

# 每周任务模板（按能力领域）
WEEKLY_TASK_TEMPLATES = {
    "signal_system": [
        {"title": "复习傅里叶变换的物理意义", "detail": "理解时域到频域的转换原理，完成3道相关练习题", "estimated_time": "60分钟"},
        {"title": "学习拉普拉斯变换", "detail": "掌握s域分析方法和系统稳定性判据", "estimated_time": "45分钟"}
    ],
    "communication_principle": [
        {"title": "学习香农定理", "detail": "理解信道容量公式C=Blog2(1+SNR)，完成计算练习", "estimated_time": "40分钟"},
        {"title": "复习信道编码", "detail": "掌握汉明码、卷积码的基本原理", "estimated_time": "50分钟"}
    ],
    "digital_signal": [
        {"title": "学习FFT算法", "detail": "理解蝶形运算原理，用Python实现一个FFT示例", "estimated_time": "60分钟"},
        {"title": "复习数字滤波器设计", "detail": "FIR与IIR滤波器的比较与设计方法", "estimated_time": "45分钟"}
    ],
    "network_protocol": [
        {"title": "深入理解TCP/IP协议栈", "detail": "绘制OSI七层模型图，标注每层关键协议", "estimated_time": "40分钟"},
        {"title": "学习路由协议", "detail": "OSPF与BGP的基本原理与配置", "estimated_time": "50分钟"}
    ],
    "modulation": [
        {"title": "复习数字调制技术", "detail": "ASK/FSK/PSK/QAM的原理与星座图绘制", "estimated_time": "45分钟"},
        {"title": "学习OFDM技术", "detail": "理解正交频分复用在4G/5G中的应用", "estimated_time": "60分钟"}
    ],
    "rf_engineering": [
        {"title": "学习阻抗匹配原理", "detail": "Smith圆图的使用方法，完成匹配电路设计练习", "estimated_time": "60分钟"},
        {"title": "复习射频放大器", "detail": "PA与LNA的设计要点与非线性指标", "estimated_time": "50分钟"}
    ],
    "antenna_design": [
        {"title": "学习天线基础参数", "detail": "增益、方向图、极化、带宽等概念", "estimated_time": "40分钟"},
        {"title": "了解MIMO天线技术", "detail": "多天线技术在5G中的应用原理", "estimated_time": "50分钟"}
    ],
    "troubleshooting": [
        {"title": "学习通信故障排查流程", "detail": "掌握分层排查方法，分析3个典型案例", "estimated_time": "45分钟"},
        {"title": "常见基站故障分析", "detail": "学习基站告警分析与处理流程", "estimated_time": "40分钟"}
    ],
    "equipment_operation": [
        {"title": "熟悉通信测试仪器", "detail": "频谱仪、信号源、示波器的使用方法", "estimated_time": "50分钟"},
        {"title": "学习设备配置流程", "detail": "基站设备开通配置的基本步骤", "estimated_time": "40分钟"}
    ],
    "safety_awareness": [
        {"title": "学习通信安全规范", "detail": "防雷接地、EMC防护、高压安全操作规程", "estimated_time": "30分钟"},
        {"title": "应急处理流程", "detail": "通信中断应急处理流程与上报机制", "estimated_time": "30分钟"}
    ],
    "innovation": [
        {"title": "阅读通信前沿技术文献", "detail": "阅读1篇6G或卫星通信相关的最新论文", "estimated_time": "60分钟"},
        {"title": "设计一个创新方案", "detail": "针对当前通信痛点提出一个改进方案", "estimated_time": "45分钟"}
    ],
    "teamwork": [
        {"title": "参与团队学习讨论", "detail": "与同学组队讨论一个通信工程案例", "estimated_time": "40分钟"},
        {"title": "完成一次知识分享", "detail": "向同学讲解一个你掌握的知识点", "estimated_time": "30分钟"}
    ]
}

# 基础摸底任务（前2周）- 覆盖所有12个能力领域各1个入门任务
BASIC_WEEKLY_TASKS = {
    1: [
        {"title": "认识信号与系统", "detail": "了解什么是信号、系统的基本概念，阅读教材前3章", "estimated_time": "45分钟", "area": "信号与系统", "area_id": "signal_system"},
        {"title": "通信原理入门", "detail": "了解通信系统的基本组成：信源、信道、信宿", "estimated_time": "40分钟", "area": "通信原理", "area_id": "communication_principle"},
        {"title": "数字信号处理基础", "detail": "了解采样定理的基本内容，尝试手动计算一个采样例子", "estimated_time": "45分钟", "area": "数字信号处理", "area_id": "digital_signal"},
        {"title": "网络协议概览", "detail": "了解OSI七层模型和TCP/IP四层模型的对应关系", "estimated_time": "30分钟", "area": "网络协议", "area_id": "network_protocol"},
        {"title": "调制技术简介", "detail": "了解ASK、FSK、PSK三种基本调制方式的区别", "estimated_time": "35分钟", "area": "调制技术", "area_id": "modulation"},
        {"title": "射频工程基础", "detail": "了解射频信号的基本特征：频率、波长、阻抗", "estimated_time": "40分钟", "area": "射频工程", "area_id": "rf_engineering"},
        {"title": "天线设计入门", "detail": "了解天线的基本参数：增益、方向图、极化", "estimated_time": "30分钟", "area": "天线设计", "area_id": "antenna_design"},
        {"title": "故障排查思维", "detail": "学习分层故障排查法：从物理层到应用层逐层排查", "estimated_time": "35分钟", "area": "故障排查", "area_id": "troubleshooting"},
        {"title": "常见仪器介绍", "detail": "认识频谱仪、示波器、信号源的基本用途", "estimated_time": "30分钟", "area": "设备操作", "area_id": "equipment_operation"},
        {"title": "通信安全意识", "detail": "了解通信工程中的基本安全规范：防雷、接地、防静电", "estimated_time": "25分钟", "area": "安全意识", "area_id": "safety_awareness"},
        {"title": "创新思维训练", "detail": "思考一个问题：5G相比4G有哪些创新？写出3点", "estimated_time": "30分钟", "area": "创新思维", "area_id": "innovation"},
        {"title": "团队协作案例", "detail": "了解一个真实的通信工程团队协作案例", "estimated_time": "30分钟", "area": "团队协作", "area_id": "teamwork"}
    ],
    2: [
        {"title": "傅里叶变换深入", "detail": "理解傅里叶变换的时域频域对应关系，做5道计算题", "estimated_time": "60分钟", "area": "信号与系统", "area_id": "signal_system"},
        {"title": "信道容量与香农定理", "detail": "学习C=Blog2(1+SNR)公式，理解信噪比与信道容量的关系", "estimated_time": "45分钟", "area": "通信原理", "area_id": "communication_principle"},
        {"title": "FFT算法实践", "detail": "用Python实现一个简单的FFT，对比DFT的计算效率", "estimated_time": "60分钟", "area": "数字信号处理", "area_id": "digital_signal"},
        {"title": "IP地址与路由", "detail": "学习IP地址分类、子网划分、基本路由配置", "estimated_time": "45分钟", "area": "网络协议", "area_id": "network_protocol"},
        {"title": "星座图分析", "detail": "绘制QPSK和16QAM的星座图，理解调制阶数的意义", "estimated_time": "40分钟", "area": "调制技术", "area_id": "modulation"},
        {"title": "Smith圆图入门", "detail": "认识Smith圆图的基本结构，学会读取阻抗点", "estimated_time": "50分钟", "area": "射频工程", "area_id": "rf_engineering"},
        {"title": "天线方向图", "detail": "阅读一个天线方向图，分析其主瓣、旁瓣特性", "estimated_time": "35分钟", "area": "天线设计", "area_id": "antenna_design"},
        {"title": "基站告警分析", "detail": "了解常见的基站告警类型及其处理方法", "estimated_time": "40分钟", "area": "故障排查", "area_id": "troubleshooting"},
        {"title": "频谱仪使用", "detail": "学习频谱仪的基本操作：中心频率、SPAN、RBW的设置", "estimated_time": "45分钟", "area": "设备操作", "area_id": "equipment_operation"},
        {"title": "高压安全规程", "detail": "学习高压设备操作的安全距离和防护措施", "estimated_time": "30分钟", "area": "安全意识", "area_id": "safety_awareness"},
        {"title": "6G前沿调研", "detail": "查阅资料了解6G的关键技术方向，写一份简要报告", "estimated_time": "60分钟", "area": "创新思维", "area_id": "innovation"},
        {"title": "模拟团队项目", "detail": "假设你在一个5G建设团队中，列出你的角色和职责", "estimated_time": "40分钟", "area": "团队协作", "area_id": "teamwork"}
    ]
}

# 测验题库（按能力领域分类）
QUIZ_BANKS = {
    "signal_system": [
        {"id": "sig_1", "question": "以下哪个是信号的基本特征？", "options": ["频率、幅度、相位", "温度、压力、速度", "颜色、形状、大小", "电压、电流、功率"], "answer": 0, "analysis": "信号的三个基本特征是频率、幅度和相位。"},
        {"id": "sig_2", "question": "傅里叶变换的核心作用是？", "options": ["时域转频域", "模拟转数字", "放大信号", "压缩数据"], "answer": 0, "analysis": "傅里叶变换将时域信号转换为频域表示，揭示信号的频率成分。"},
        {"id": "sig_3", "question": "卷积在信号与系统中的意义是？", "options": ["计算系统输出", "放大信号", "消除噪声", "生成新信号"], "answer": 0, "analysis": "卷积描述了线性时不变系统的输入输出关系：y(t) = x(t) * h(t)。"},
        {"id": "sig_4", "question": "拉普拉斯变换主要用于分析什么类型的系统？", "options": ["连续时间系统", "离散时间系统", "数字系统", "通信系统"], "answer": 0, "analysis": "拉普拉斯变换是傅里叶变换的推广，主要用于分析连续时间系统。"},
        {"id": "sig_5", "question": "系统的冲激响应h(t)与什么直接相关？", "options": ["系统特性", "输入信号", "输出信号", "噪声水平"], "answer": 0, "analysis": "冲激响应h(t)完全描述了线性时不变系统的特性。"}
    ],
    "communication_principle": [
        {"id": "comm_1", "question": "通信系统的基本组成不包括？", "options": ["信源", "信道", "信宿", "路由器"], "answer": 3, "analysis": "通信系统由信源、发送设备、信道、接收设备和信宿组成。路由器属于网络设备。"},
        {"id": "comm_2", "question": "香农定理的公式是什么？", "options": ["C = B·log2(1+SNR)", "C = B·SNR", "C = log2(B+SNR)", "C = B/SNR"], "answer": 0, "analysis": "香农信道容量公式：C = B·log2(1+SNR)，其中B为带宽，SNR为信噪比。"},
        {"id": "comm_3", "question": "以下哪种不是信道噪声？", "options": ["热噪声", "散粒噪声", "环境噪声", "编码噪声"], "answer": 3, "analysis": "编码是主动行为，编码噪声不是信道固有的噪声类型。"},
        {"id": "comm_4", "question": "误码率BER的含义是？", "options": ["错误比特数占总传输比特数的比例", "正确比特数", "传输速率", "信号强度"], "answer": 0, "analysis": "BER (Bit Error Rate) 即比特误码率，是错误比特数与总传输比特数之比。"},
        {"id": "comm_5", "question": "信噪比SNR的计算公式是？", "options": ["信号功率/噪声功率", "信号幅度/噪声幅度", "信号频率/噪声频率", "信号电压/噪声电流"], "answer": 0, "analysis": "SNR = 信号功率/噪声功率，通常用dB表示。"}
    ],
    "digital_signal": [
        {"id": "dsp_1", "question": "奈奎斯特采样定理要求采样频率满足？", "options": ["fs > 2fmax", "fs > fmax", "fs = fmax", "fs < 2fmax"], "answer": 0, "analysis": "奈奎斯特采样定理：fs > 2fmax，才能无失真重建原信号。"},
        {"id": "dsp_2", "question": "FFT相比DFT的优势是？", "options": ["计算复杂度低", "精度更高", "能处理更大数据", "不需要计算机"], "answer": 0, "analysis": "FFT将DFT的O(N²)复杂度降到O(NlogN)，大幅提升计算效率。"},
        {"id": "dsp_3", "question": "数字滤波器按功能可分为？", "options": ["低通、高通、带通、带阻", "模拟、数字、混合", "有源、无源", "FIR、IIR"], "answer": 0, "analysis": "按频率响应分为低通、高通、带通、带阻滤波器。"},
        {"id": "dsp_4", "question": "以下关于量化的描述错误的是？", "options": ["量化会引入误差", "量化位数越多精度越高", "量化可以消除噪声", "量化是模拟转数字的关键步骤"], "answer": 2, "analysis": "量化会引入量化误差，不能消除噪声。"},
        {"id": "dsp_5", "question": "FIR滤波器的特点是？", "options": ["线性相位、稳定", "非线性相位、不稳定", "递归结构", "需要反馈"], "answer": 0, "analysis": "FIR滤波器具有线性相位特性且绝对稳定，因为没有反馈。"}
    ],
    "network_protocol": [
        {"id": "net_1", "question": "OSI七层模型中，负责端到端可靠传输的是？", "options": ["传输层", "网络层", "数据链路层", "会话层"], "answer": 0, "analysis": "传输层（TCP/UDP）负责端到端的可靠数据传输。"},
        {"id": "net_2", "question": "TCP三次握手的主要目的是？", "options": ["建立可靠连接", "加密数据", "压缩数据", "路由选择"], "answer": 0, "analysis": "TCP三次握手用于建立可靠的面向连接的通信通道。"},
        {"id": "net_3", "question": "以下哪个不是IP协议的功能？", "options": ["路由选择", "地址寻址", "数据分片", "可靠传输"], "answer": 3, "analysis": "可靠传输是TCP的功能，IP提供尽力而为的不可靠传输。"},
        {"id": "net_4", "question": "子网划分的主要目的是？", "options": ["有效利用IP地址", "加密通信", "加速传输", "增加带宽"], "answer": 0, "analysis": "子网划分将大网络分为更小的子网，有效利用IP地址空间。"},
        {"id": "net_5", "question": "HTTP协议默认端口号是？", "options": ["80", "443", "8080", "21"], "answer": 0, "analysis": "HTTP默认端口为80，HTTPS为443。"}
    ],
    "modulation": [
        {"id": "mod_1", "question": "ASK、FSK、PSK分别代表什么？", "options": ["幅移键控、频移键控、相移键控", "移幅、移频、移相", "调制、解调、编码", "模拟、数字、混合"], "answer": 0, "analysis": "ASK(幅移键控)、FSK(频移键控)、PSK(相移键控)是三种基本数字调制方式。"},
        {"id": "mod_2", "question": "QPSK相比BPSK的优势是？", "options": ["频带利用率高", "抗干扰能力强", "实现更简单", "功率更小"], "answer": 0, "analysis": "QPSK每符号传输2bit，频带利用率是BPSK的两倍。"},
        {"id": "mod_3", "question": "16QAM的星座图有多少个点？", "options": ["16个", "4个", "8个", "64个"], "answer": 0, "analysis": "16QAM的星座图有16个点，每个符号传输4bit信息。"},
        {"id": "mod_4", "question": "以下哪种调制方式抗干扰能力最强？", "options": ["BPSK", "QPSK", "16QAM", "64QAM"], "answer": 0, "analysis": "调制阶数越低抗干扰能力越强，BPSK最抗干扰但频带利用率最低。"},
        {"id": "mod_5", "question": "调制的本质是？", "options": ["将基带信号搬移到载波上", "放大信号", "滤除噪声", "编码数据"], "answer": 0, "analysis": "调制是将基带信号（低频）搬移到高频载波上以便传输。"}
    ],
    "rf_engineering": [
        {"id": "rf_1", "question": "射频信号的频率范围通常是？", "options": ["3kHz~300GHz", "300Hz~3kHz", "300GHz~3THz", "直流~300Hz"], "answer": 0, "analysis": "射频(RF)频率范围通常为3kHz~300GHz。"},
        {"id": "rf_2", "question": "阻抗匹配的目的是？", "options": ["实现最大功率传输", "减少信号衰减", "提高频率", "增加带宽"], "answer": 0, "analysis": "阻抗匹配使源阻抗和负载阻抗共轭匹配，实现最大功率传输。"},
        {"id": "rf_3", "question": "Smith圆图主要用于？", "options": ["阻抗匹配分析", "信号调制", "编码解码", "数据分析"], "answer": 0, "analysis": "Smith圆图是射频工程中进行阻抗匹配和网络分析的重要工具。"},
        {"id": "rf_4", "question": "VSWR的含义是？", "options": ["电压驻波比", "电压增益", "信号速度", "带宽"], "answer": 0, "analysis": "VSWR (Voltage Standing Wave Ratio) 是传输线上驻波电压最大值与最小值之比。"},
        {"id": "rf_5", "question": "以下哪种不是射频无源器件？", "options": ["晶体管", "电容", "电感", "电阻"], "answer": 0, "analysis": "晶体管是有源器件，电容、电感、电阻是无源器件。"}
    ],
    "antenna_design": [
        {"id": "ant_1", "question": "天线的主要功能是？", "options": ["发射和接收电磁波", "放大信号", "调制解调", "编码解码"], "answer": 0, "analysis": "天线是无线通信系统中实现电磁波发射和接收的关键部件。"},
        {"id": "ant_2", "question": "天线增益的含义是？", "options": ["天线方向性的能量集中程度", "功率放大倍数", "频率倍数", "电压增益"], "answer": 0, "analysis": "天线增益衡量天线将能量集中到特定方向的能力，用dBi或dBd表示。"},
        {"id": "ant_3", "question": "半波振子天线的长度约为？", "options": ["λ/2", "λ/4", "λ", "2λ"], "answer": 0, "analysis": "半波振子天线的长度约为工作波长的一半（λ/2）。"},
        {"id": "ant_4", "question": "天线极化方式不包括？", "options": ["圆极化", "椭圆极化", "线极化", "方形极化"], "answer": 3, "analysis": "天线极化方式有线极化、圆极化和椭圆极化，没有方形极化。"},
        {"id": "ant_5", "question": "天线方向图中的主瓣宽度表示？", "options": ["天线波束的宽度", "工作频带宽度", "功率范围", "阻抗范围"], "answer": 0, "analysis": "主瓣宽度是天线方向图中主瓣两侧3dB点之间的夹角，表示天线波束的窄宽程度。"}
    ],
    "troubleshooting": [
        {"id": "trou_1", "question": "通信网络故障排查的一般顺序是？", "options": ["物理层→数据链路层→网络层→应用层", "应用层→网络层→物理层", "数据链路层→物理层→应用层", "随机排查"], "answer": 0, "analysis": "故障排查通常分层进行，从物理层到应用层逐层排查。"},
        {"id": "trou_2", "question": "基站出现高驻波比告警，最可能的原因是？", "options": ["馈线接头松动或进水", "基带板故障", "传输中断", "电源故障"], "answer": 0, "analysis": "高驻波比通常由馈线系统问题引起，如接头松动、进水、天线损坏等。"},
        {"id": "trou_3", "question": "以下哪种工具用于排查无线信号问题？", "options": ["频谱分析仪", "万用表", "示波器", "功率计"], "answer": 0, "analysis": "频谱分析仪用于分析信号频谱，是无线信号排查的核心工具。"},
        {"id": "trou_4", "question": "基站退服的常见原因不包括？", "options": ["Abis链路中断", "电源故障", "软件异常", "用户投诉"], "answer": 3, "analysis": "用户投诉不会直接导致基站退服，链路中断、电源故障和软件异常才是常见原因。"},
        {"id": "trou_5", "question": "排查思路中'望闻问切'的'问'是指？", "options": ["询问用户和运维人员", "查询日志", "查看告警", "远程登录设备"], "answer": 0, "analysis": "'问'指向相关人员了解故障现象、发生时间等信息，获取第一手资料。"}
    ],
    "equipment_operation": [
        {"id": "equip_1", "question": "频谱分析仪中RBW的含义是？", "options": ["分辨率带宽", "参考带宽", "扫描带宽", "视频带宽"], "answer": 0, "analysis": "RBW (Resolution Bandwidth) 是频谱分析仪的分辨率带宽，决定能分辨的最小频率间隔。"},
        {"id": "equip_2", "question": "示波器的带宽指标表示？", "options": ["可测量信号的最高频率", "采样速度", "存储深度", "显示分辨率"], "answer": 0, "analysis": "示波器带宽决定了能准确测量的信号最高频率分量。"},
        {"id": "equip_3", "question": "使用万用表测量电压前应注意？", "options": ["选择正确的量程", "先调零", "连接地线", "打开电源"], "answer": 0, "analysis": "使用万用表前必须选择正确的量程，量程选择不当可能损坏仪表。"},
        {"id": "equip_4", "question": "以下哪个参数不是频谱分析仪可调的？", "options": ["中心频率", "SPAN", "RBW", "天线增益"], "answer": 3, "analysis": "中心频率、SPAN和RBW都是频谱分析仪的可调参数，天线增益是天线固有参数。"},
        {"id": "equip_5", "question": "信号发生器的主要功能是？", "options": ["产生标准测试信号", "放大信号", "分析频谱", "测量功率"], "answer": 0, "analysis": "信号发生器产生已知参数的标准测试信号，用于测试和调试电路。"}
    ],
    "safety_awareness": [
        {"id": "safe_1", "question": "通信机房的安全距离要求，高压设备至少？", "options": ["1米", "0.5米", "2米", "5米"], "answer": 0, "analysis": "高压设备安全距离至少1米，10kV以下安全距离为0.7米。"},
        {"id": "safe_2", "question": "雷击防护的主要措施不包括？", "options": ["接地", "屏蔽", "防雷器", "增加带宽"], "answer": 3, "analysis": "防雷措施包括接地、屏蔽、安装防雷器，增加带宽与防雷无关。"},
        {"id": "safe_3", "question": "以下哪种行为是安全的？", "options": ["断电后再检修设备", "带电插拔板卡", "用湿手操作设备", "在机房内吸烟"], "answer": 0, "analysis": "检修设备前必须断电，确保人身安全。"},
        {"id": "safe_4", "question": "防静电措施中，操作人员应佩戴？", "options": ["防静电手环", "安全帽", "绝缘手套", "护目镜"], "answer": 0, "analysis": "操作人员佩戴防静电手环可以将人体静电导入大地，防止损坏敏感电子元件。"},
        {"id": "safe_5", "question": "机房消防应使用哪种灭火器？", "options": ["气体灭火器", "水基灭火器", "泡沫灭火器", "干粉灭火器"], "answer": 0, "analysis": "机房应使用气体灭火器（如七氟丙烷），水和泡沫灭火器会损坏电子设备。"}
    ],
    "innovation": [
        {"id": "innov_1", "question": "5G相比4G的核心技术创新不包括？", "options": ["毫米波通信", "Massive MIMO", "FDMA", "网络切片"], "answer": 2, "analysis": "FDMA是4G就使用的技术，5G的创新包括毫米波、Massive MIMO、网络切片等。"},
        {"id": "innov_2", "question": "创新思维的核心是？", "options": ["突破思维定式", "遵循传统", "复制现有", "避免风险"], "answer": 0, "analysis": "创新思维的核心是突破传统思维定式，寻找新的解决方案。"},
        {"id": "innov_3", "question": "6G预计将实现哪些目标？", "options": ["太赫兹通信、空天地一体化", "更快的4G", "替代光纤", "取消基站"], "answer": 0, "analysis": "6G愿景包括太赫兹通信、空天地一体化通信、智能原生等。"},
        {"id": "innov_4", "question": "TRIZ理论的核心思想是？", "options": ["解决技术矛盾", "降低成本", "提高产量", "简化操作"], "answer": 0, "analysis": "TRIZ是发明问题解决理论，核心是通过解决技术矛盾产生创新方案。"},
        {"id": "innov_5", "question": "以下哪种方法有助于培养创新能力？", "options": ["多学科交叉学习", "专注单一技术", "避免质疑", "只读书本"], "answer": 0, "analysis": "跨学科学习能激发创新思维，不同领域的知识融合常产生创新灵感。"}
    ],
    "teamwork": [
        {"id": "team_1", "question": "团队协作中最重要的要素是？", "options": ["有效沟通", "个人能力", "技术工具", "工作时长"], "answer": 0, "analysis": "有效沟通是团队协作的基础，没有沟通就没有真正的协作。"},
        {"id": "team_2", "question": "通信工程项目中，项目经理的主要职责是？", "options": ["整体协调与资源管理", "技术研发", "现场施工", "财务核算"], "answer": 0, "analysis": "项目经理负责项目整体协调、资源管理、进度控制和风险管理。"},
        {"id": "team_3", "question": "团队冲突处理的最佳方式是？", "options": ["沟通协商达成共识", "强制压制", "回避不理", "投票表决"], "answer": 0, "analysis": "通过沟通协商达成共识是解决团队冲突的最佳方式，有助于团队长期协作。"},
        {"id": "team_4", "question": "敏捷开发中每日站会的目的是？", "options": ["同步进度和暴露问题", "分配任务", "技术培训", "考核员工"], "answer": 0, "analysis": "每日站会让团队成员同步进展、暴露阻塞问题，促进快速迭代。"},
        {"id": "team_5", "question": "以下哪种做法不利于团队协作？", "options": ["明确角色分工", "建立信任", "信息共享", "个人英雄主义"], "answer": 3, "analysis": "个人英雄主义强调个人表现而忽视团队协作，不利于团队整体发展。"}
    ]
}

# 知识领域到知识库关键词的映射
AREA_KNOWLEDGE_MAP = {
    "signal_system": ["傅里叶变换", "卷积", "拉普拉斯", "Z变换", "奈奎斯特"],
    "communication_principle": ["香农", "信噪比", "信道容量", "误码率", "编码"],
    "digital_signal": ["采样", "FFT", "量化", "滤波器", "频谱分析"],
    "network_protocol": ["TCP", "IP", "HTTP", "路由", "子网"],
    "modulation": ["调制", "ASK", "FSK", "PSK", "QAM", "星座图"],
    "rf_engineering": ["射频", "阻抗", "Smith圆图", "VSWR", "驻波"],
    "antenna_design": ["天线", "极化", "方向图", "增益", "半波振子"],
    "troubleshooting": ["故障排查", "告警", "基站", "驻波比"],
    "equipment_operation": ["频谱仪", "示波器", "信号发生器", "万用表"],
    "safety_awareness": ["防雷", "接地", "防静电", "安全距离"],
    "innovation": ["5G", "6G", "创新", "Massive MIMO", "网络切片"],
    "teamwork": ["团队", "沟通", "项目管理", "协作"]
}

# 学习建议模板
STUDY_SUGGESTIONS = {
    "signal_system": "建议复习《信号与系统》教材的前4章，重点掌握傅里叶变换、卷积和系统响应。可以使用MATLAB进行仿真练习。",
    "communication_principle": "建议学习《通信原理》第2-4章，理解通信系统基本模型、信道容量定理和编码基础。推荐阅读Proakis的著作。",
    "digital_signal": "建议学习《数字信号处理》教材，重点掌握采样定理、FFT算法和滤波器设计。使用Python的numpy库进行实践。",
    "network_protocol": "建议学习《计算机网络》自顶向下方法，重点掌握OSI模型、TCP/UDP和IP协议。使用Wireshark抓包分析。",
    "modulation": "建议学习通信电子线路中的调制解调部分，掌握ASK/FSK/PSK/QAM的原理和星座图分析。",
    "rf_engineering": "建议学习《射频通信电路》，重点掌握阻抗匹配、Smith圆图和VSWR概念。使用ADS或LTspice进行仿真。",
    "antenna_design": "建议学习《天线原理》教材，掌握天线基本参数、各种天线类型和设计方法。使用HFSS进行天线仿真。",
    "troubleshooting": "建议参加实际的基站运维实习，学习常见告警处理流程，积累现场排查经验。",
    "equipment_operation": "建议参加实验室仪器培训，熟悉频谱仪、示波器、信号源的操作方法，多做实际测量练习。",
    "safety_awareness": "建议学习通信工程安全规范和电工安全知识，参加企业安全培训课程。",
    "innovation": "建议阅读5G/6G技术白皮书和前沿论文，关注3GPP标准进展，参加创新竞赛。",
    "teamwork": "建议参加团队项目和社团活动，学习项目管理方法，提升沟通协作能力。"
}

# ====================== 胜任力分析辅助函数 ======================
def calculate_competency_profile(student):
    """基于学员数据计算5维岗位胜任力画像"""
    competence_analysis = student.get('competence_analysis', {})
    conversation_history = student.get('conversation_history', [])
    quiz_attempts = student.get('quiz_attempts', {})
    target_job = student.get('target_job', '')
    custom_job = student.get('custom_job', '')
    effective_job = custom_job or target_job

    profile = {}
    dimension_scores = {}

    for dim_id, dim_config in COMPETENCY_DIMENSIONS.items():
        mapped_areas = dim_config['mapped_areas']
        area_scores = []
        for area_id in mapped_areas:
            area_data = competence_analysis.get(area_id, {})
            score = area_data.get('score', 0)
            count = area_data.get('count', 0)
            if count > 0:
                area_scores.append(score)
            else:
                area_scores.append(0)

        base_score = sum(area_scores) / len(area_scores) if area_scores else 0

        # 根据AI对话关键词补充
        keyword_boost = 0
        if dim_id in ('communication', 'project_management', 'safety_ethics', 'innovation'):
            keywords = dim_config.get('keywords', [])
            relevant_msgs = sum(
                1 for c in conversation_history
                if any(kw in c.get('message', '') for kw in keywords)
            )
            keyword_boost = min(relevant_msgs * 0.05, 0.2)

        # 安全维度从测验安全分获取
        safety_boost = 0
        if dim_id == 'safety_ethics':
            safety_scores = []
            for task_id, qa in quiz_attempts.items():
                ss = qa.get('safety_score', 100)
                if ss < 100:
                    safety_scores.append(ss / 100.0)
            if safety_scores:
                safety_boost = sum(safety_scores) / len(safety_scores) * 0.3
            else:
                safety_boost = 0.15

        final_score = min(1.0, base_score + keyword_boost + safety_boost)
        dimension_scores[dim_id] = round(final_score, 3)

    # 岗位画像权重调整
    pos_weights = POSITION_COMPETENCY_MAP.get(effective_job, {})
    weighted_total = 0
    total_weight = 0
    for dim_id, score in dimension_scores.items():
        w = pos_weights.get(dim_id, COMPETENCY_DIMENSIONS[dim_id]['weight'])
        weighted_total += score * w
        total_weight += w
    overall_score = round(weighted_total / total_weight, 3) if total_weight > 0 else 0

    # 找出优势项和短板
    sorted_dims = sorted(dimension_scores.items(), key=lambda x: x[1], reverse=True)
    strengths = [
        {'dimension': COMPETENCY_DIMENSIONS[d]['name'], 'score': s}
        for d, s in sorted_dims[:2] if s >= 0.4
    ]
    weaknesses = [
        {'dimension': COMPETENCY_DIMENSIONS[d]['name'], 'score': s}
        for d, s in sorted_dims[-2:] if s < 0.6
    ]

    # 评级
    if overall_score >= 0.75:
        level = 'A'
        level_desc = '优秀'
    elif overall_score >= 0.6:
        level = 'B'
        level_desc = '良好'
    elif overall_score >= 0.4:
        level = 'C'
        level_desc = '合格'
    else:
        level = 'D'
        level_desc = '待提升'

    # 雷达图数据
    radar_data = []
    for dim_id, dim_config in COMPETENCY_DIMENSIONS.items():
        radar_data.append({
            'dimension': dim_id,
            'name': dim_config['name'],
            'icon': dim_config['icon'],
            'color': dim_config['color'],
            'score': dimension_scores[dim_id],
            'sub_dimensions': dim_config['sub_dimensions']
        })

    return {
        'overall_score': overall_score,
        'level': level,
        'level_desc': level_desc,
        'target_job': effective_job,
        'radar_data': radar_data,
        'dimension_scores': dimension_scores,
        'strengths': strengths,
        'weaknesses': weaknesses,
        'pos_weights_used': pos_weights or {d: c['weight'] for d, c in COMPETENCY_DIMENSIONS.items()}
    }

# ====================== 动态故障注入场景 ======================
FAULT_SCENARIOS = {
    "signal_system": [
        {"id": "sig_fault_1", "name": "信号失真故障", "description": "您负责的基站接收到的信号波形出现明显失真，频谱分析显示谐波分量异常。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已确认设备接地良好，无电磁干扰", "required": True},
            {"id": "chk_2", "text": "已备份当前配置数据，防止操作丢失", "required": True},
            {"id": "chk_3", "text": "已穿戴防静电手环，符合操作规范", "required": True},
            {"id": "chk_4", "text": "已通知现场监护人员到位", "required": False}
        ]},
        {"id": "sig_fault_2", "name": "信号衰减异常", "description": "基站覆盖区域内信号强度骤降15dBm，疑似馈线接头进水导致。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已断开射频电源，确认安全", "required": True},
            {"id": "chk_2", "text": "已准备好干燥的清洁工具和密封材料", "required": True},
            {"id": "chk_3", "text": "已记录故障发生时间和影响范围", "required": True},
            {"id": "chk_4", "text": "已协调备用馈线组件", "required": False}
        ]}
    ],
    "communication_principle": [
        {"id": "comm_fault_1", "name": "通信中断故障", "description": "核心机房与远端基站的SDH链路中断，业务全部切换至备用路由。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已确认主用路由故障告警", "required": True},
            {"id": "chk_2", "text": "已切换至备用路由，业务已恢复", "required": True},
            {"id": "chk_3", "text": "已通知传输班工程师赶赴现场", "required": True},
            {"id": "chk_4", "text": "已准备好OTDR测试仪和光功率计", "required": False}
        ]},
        {"id": "comm_fault_2", "name": "误码率突增", "description": "链路BER从10^-9恶化到10^-4，业务数据出现丢包。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已采集误码数据日志", "required": True},
            {"id": "chk_2", "text": "已确认非上游网络问题", "required": True},
            {"id": "chk_3", "text": "已备份当前配置快照", "required": True},
            {"id": "chk_4", "text": "已通知业务方可能的短暂中断", "required": False}
        ]}
    ],
    "digital_signal": [
        {"id": "dsp_fault_1", "name": "采样率异常", "description": "ADC采样时钟频率偏移，导致数字信号出现混叠失真。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已确认时钟源设备状态正常", "required": True},
            {"id": "chk_2", "text": "已备份当前DSP固件版本", "required": True},
            {"id": "chk_3", "text": "已准备示波器验证修复结果", "required": True}
        ]},
        {"id": "dsp_fault_2", "name": "滤波器故障", "description": "数字滤波器系数漂移，导致通带波纹增大3dB。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已导出当前滤波器系数", "required": True},
            {"id": "chk_2", "text": "已使用标准信号源准备验证", "required": True},
            {"id": "chk_3", "text": "已记录修复前的频谱截图", "required": True}
        ]}
    ],
    "network_protocol": [
        {"id": "net_fault_1", "name": "网络丢包", "description": "核心路由器间链路丢包率达5%，影响实时业务传输。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已确认丢包范围和受影响业务", "required": True},
            {"id": "chk_2", "text": "已准备抓包工具采集数据", "required": True},
            {"id": "chk_3", "text": "已配置路由预备份方案", "required": True},
            {"id": "chk_4", "text": "已通知网络运维团队", "required": False}
        ]},
        {"id": "net_fault_2", "name": "路由环路", "description": "OSPF协议在核心区域形成路由环路，导致流量黑洞。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已确认环路涉及的路由器ID", "required": True},
            {"id": "chk_2", "text": "已备份当前路由表", "required": True},
            {"id": "chk_3", "text": "已规划环路破除方案", "required": True}
        ]}
    ],
    "modulation": [
        {"id": "mod_fault_1", "name": "调制失真", "description": "QAM星座图出现相位偏移，EVM指标超标达8%。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已确认EVM超标范围", "required": True},
            {"id": "chk_2", "text": "已校准本振源频率", "required": True},
            {"id": "chk_3", "text": "已准备矢量信号分析仪", "required": True}
        ]}
    ],
    "rf_engineering": [
        {"id": "rf_fault_1", "name": "驻波比异常", "description": "馈线VSWR从1.2恶化到3.5，反射功率超标。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已断开射频发射电源", "required": True},
            {"id": "chk_2", "text": "已使用VSWR测试仪定位故障点", "required": True},
            {"id": "chk_3", "text": "已准备备用馈线和接头", "required": True},
            {"id": "chk_4", "text": "已通知塔下监护人员", "required": False}
        ]},
        {"id": "rf_fault_2", "name": "功率放大器故障", "description": "PA模块输出功率下降3dB，增益异常。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已确认PA偏置电压正常", "required": True},
            {"id": "chk_2", "text": "已准备替换模块和防静电工具", "required": True},
            {"id": "chk_3", "text": "已记录故障功率曲线", "required": True}
        ]}
    ],
    "antenna_design": [
        {"id": "ant_fault_1", "name": "天线失配", "description": "天线输入阻抗偏离50Ω，导致反射增大。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已使用VNA测量S参数", "required": True},
            {"id": "chk_2", "text": "已确认馈线连接牢固", "required": True},
            {"id": "chk_3", "text": "已准备匹配网络组件", "required": True}
        ]}
    ],
    "troubleshooting": [
        {"id": "trouble_fault_1", "name": "综合告警", "description": "基站同时出现温度告警、功率告警和通信告警，需快速定位根因。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已查看所有告警日志", "required": True},
            {"id": "chk_2", "text": "已按优先级排序处理", "required": True},
            {"id": "chk_3", "text": "已通知现场工程师", "required": True},
            {"id": "chk_4", "text": "已准备应急备件", "required": False}
        ]}
    ],
    "equipment_operation": [
        {"id": "equip_fault_1", "name": "仪器校准失效", "description": "频谱仪校准过期，测量结果可能存在系统误差。", "level": "warning", "pre_checklist": [
            {"id": "chk_1", "text": "已确认校准有效期", "required": True},
            {"id": "chk_2", "text": "已联系计量院校准服务", "required": True},
            {"id": "chk_3", "text": "已使用校准源进行临时核查", "required": True}
        ]}
    ],
    "safety_awareness": [
        {"id": "safety_fault_1", "name": "安全隐患排查", "description": "机房巡检发现消防通道被占用，温度监控系统告警。", "level": "danger", "pre_checklist": [
            {"id": "chk_1", "text": "已立即清理消防通道", "required": True},
            {"id": "chk_2", "text": "已检查烟感和温感设备", "required": True},
            {"id": "chk_3", "text": "已通知物业安保部门", "required": True},
            {"id": "chk_4", "text": "已记录安全检查报告", "required": True}
        ]}
    ],
    "innovation": [
        {"id": "innov_fault_1", "name": "技术选型争议", "description": "团队在5G和WiFi6方案选择上存在分歧，需要技术论证。", "level": "info", "pre_checklist": [
            {"id": "chk_1", "text": "已整理两种方案的技术对比", "required": True},
            {"id": "chk_2", "text": "已收集测试数据支撑决策", "required": True},
            {"id": "chk_3", "text": "已组织技术评审会议", "required": True}
        ]}
    ],
    "teamwork": [
        {"id": "team_fault_1", "name": "协作冲突", "description": "项目组内出现任务分配分歧，影响项目进度。", "level": "info", "pre_checklist": [
            {"id": "chk_1", "text": "已了解各方意见和诉求", "required": True},
            {"id": "chk_2", "text": "已制定折中方案初稿", "required": True},
            {"id": "chk_3", "text": "已安排团队沟通会议", "required": True}
        ]}
    ]
}

# ====================== 剧情演绎场景配置 ======================
SCENARIOS = [
    {
        "id": 1,
        "title": "新入职通信工程师",
        "description": "你刚从大学毕业，进入一家通信设备公司担任初级工程师，需要在一周内熟悉5G基站的安装调试工作。",
        "difficulty": "简单",
        "tasks": [
            "学习5G基站的基本组成和工作原理",
            "完成一次基站安装的模拟操作",
            "处理一个常见的基站连接故障"
        ]
    },
    {
        "id": 2,
        "title": "网络故障排查工程师",
        "description": "你负责城市通信网络的监控和维护，突然接到报告说某大型商场的WiFi信号大面积断网。",
        "difficulty": "中等",
        "tasks": [
            "使用网络诊断工具定位故障点",
            "制定并执行故障排除方案",
            "记录故障原因和解决方案"
        ]
    },
    {
        "id": 3,
        "title": "通信系统优化工程师",
        "description": "你被派往一个新建成的工业园区，需要优化园区内的通信网络以满足智能工厂的需求。",
        "difficulty": "较难",
        "tasks": [
            "进行信号覆盖测试",
            "分析网络瓶颈并提出优化方案",
            "实施优化方案并验证效果"
        ]
    }
]


def atomic_save_json(filepath: str, data):
    """原子写入JSON：先写临时文件再重命名，防止并发写入损坏"""
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, filepath)


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


def load_upload_history() -> List[Dict]:
    """加载上传历史记录"""
    try:
        if os.path.exists(UPLOAD_HISTORY_FILE):
            with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        print(f"加载上传历史失败: {e}")
        return []


def save_upload_history(history: List[Dict]):
    """保存上传历史记录"""
    try:
        atomic_save_json(UPLOAD_HISTORY_FILE, history)
    except Exception as e:
        print(f"保存上传历史失败: {e}")


# ====================== 错题本和学习记录 ======================
def load_wrong_questions() -> List[Dict]:
    """加载错题本"""
    try:
        if os.path.exists(WRONG_QUESTIONS_FILE):
            with open(WRONG_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"加载错题本失败: {e}")
        return []


def save_wrong_questions(questions: List[Dict]):
    """保存错题本"""
    try:
        atomic_save_json(WRONG_QUESTIONS_FILE, questions)
    except Exception as e:
        print(f"保存错题本失败: {e}")


def load_learning_records() -> Dict:
    """加载学习记录"""
    try:
        if os.path.exists(LEARNING_RECORDS_FILE):
            with open(LEARNING_RECORDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"加载学习记录失败: {e}")
        return {}


def save_learning_records(records: Dict):
    """保存学习记录"""
    try:
        atomic_save_json(LEARNING_RECORDS_FILE, records)
    except Exception as e:
        print(f"保存学习记录失败: {e}")


# ====================== PPT元数据管理 ======================
def load_ppt_metadata() -> List[Dict]:
    """加载PPT元数据"""
    try:
        if os.path.exists(PPT_METADATA_FILE):
            with open(PPT_METADATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"加载PPT元数据失败: {e}")
        return []


def save_ppt_metadata(metadata: List[Dict]):
    """保存PPT元数据"""
    try:
        atomic_save_json(PPT_METADATA_FILE, metadata)
    except Exception as e:
        print(f"保存PPT元数据失败: {e}")


# ====================== PPT 转图片预览（大文件秒开） ======================
PPT_PREVIEW_DIR = os.path.join(UPLOAD_FOLDER, "previews")
_converting_lock = threading.Lock()
_converting = set()


def convert_document_to_images(download_name: str):
    """后台将文档（ppt/pptx/doc/docx）逐页转为JPEG图片。
    转换完成后回写预览状态：PPT写ppt_metadata，Word等写upload_history，
    字段统一为 preview_ready/page_count/preview_dir，前端按同一套逻辑预览。
    """
    stem = download_name.rsplit('.', 1)[0]
    with _converting_lock:
        if stem in _converting:
            return
        _converting.add(stem)
    try:
        import subprocess
        import tempfile
        import glob as globmod
        src = os.path.join(UPLOAD_FOLDER, download_name)
        if not os.path.exists(src):
            print(f"文档预览转换跳过，源文件不存在: {download_name}")
            return
        out_dir = os.path.join(PPT_PREVIEW_DIR, stem)
        os.makedirs(out_dir, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            # 文档 -> pdf（LibreOffice 无头模式，impress/writer 均支持；
            # 25.x 不支持 --no-sandbox；profile独立避免并发锁）
            profile_url = 'file://' + os.path.join(tmp, 'lo_profile')
            r = subprocess.run(
                ['soffice', '--headless', '--norestore', '--nologo',
                 f'-env:UserInstallation={profile_url}',
                 '--convert-to', 'pdf', '--outdir', tmp, src],
                timeout=600, capture_output=True)
            pdf_path = os.path.join(tmp, stem + '.pdf')
            if not os.path.exists(pdf_path):
                detail = (r.stderr.decode('utf-8', 'ignore') + r.stdout.decode('utf-8', 'ignore'))[:300]
                raise RuntimeError(f"PDF转换失败: {detail}")
            # pdf -> 逐页jpg（统一两位编号 page-01.jpg）
            subprocess.run(
                ['pdftoppm', '-jpeg', '-r', '90', '-jpegopt', 'quality=80',
                 pdf_path, os.path.join(out_dir, 'page')],
                timeout=300, capture_output=True)
        pages = sorted(globmod.glob(os.path.join(out_dir, 'page*.jpg')))
        if not pages:
            raise RuntimeError("PDF未产出页面图片")
        if len(pages) > 1 or os.path.basename(pages[0]) != 'page-01.jpg':
            for idx, old in enumerate(pages, 1):
                os.replace(old, os.path.join(out_dir, f'page-{idx:02d}.jpg'))
        preview_fields = {
            'preview_ready': True,
            'page_count': len(pages),
            'preview_dir': f'previews/{stem}'
        }
        # PPT 课件元数据（学生端课件中心等仍在使用，保持原行为）
        metadata = load_ppt_metadata()
        changed = False
        for m in metadata:
            if m.get('download_name') == download_name:
                m.update(preview_fields)
                changed = True
        if changed:
            save_ppt_metadata(metadata)
        # 上传历史条目（Word/通用文档的预览状态存这里）
        history = load_upload_history()
        hist_changed = False
        for h in history:
            if h.get('download_name') == download_name:
                h.update(preview_fields)
                hist_changed = True
        if hist_changed:
            save_upload_history(history)
        print(f"文档预览图转换完成: {download_name} -> {len(pages)}页")
    except Exception as e:
        print(f"文档预览图转换失败 {download_name}: {e}")
    finally:
        with _converting_lock:
            _converting.discard(stem)


def save_ppt_for_download(file, file_path: str) -> str:
    """保存PPT文件供下载使用"""
    try:
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if ext in ['pptx', 'ppt']:
            download_name = f"lecture_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            download_path = os.path.join(UPLOAD_FOLDER, download_name)
            file.save(download_path)
            return download_name
        return ""
    except Exception as e:
        print(f"保存PPT文件失败: {e}")
        return ""


def search_ppt_by_keyword(keyword: str) -> List[Dict]:
    """根据关键词搜索相关PPT"""
    metadata = load_ppt_metadata()
    results = []
    
    keyword_lower = keyword.lower()
    
    for ppt in metadata:
        match_score = 0
        
        if keyword_lower in ppt['filename'].lower():
            match_score += 3
        
        for kp in ppt.get('knowledge_points', []):
            if keyword_lower in kp.lower():
                match_score += 2
        
        for chapter in ppt.get('chapters', []):
            if keyword_lower in chapter['title'].lower():
                match_score += 2
            if keyword_lower in chapter['content'].lower():
                match_score += 1
        
        if match_score > 0:
            ppt_copy = ppt.copy()
            ppt_copy['match_score'] = match_score
            results.append(ppt_copy)
    
    results.sort(key=lambda x: x['match_score'], reverse=True)
    return results[:5]


def record_wrong_question(student_name: str, question: str, category: str, 
                          knowledge_point: str = "", student_answer: str = "", 
                          correct_answer: str = ""):
    """记录错题"""
    questions = load_wrong_questions()
    # 检查是否已存在相同错题
    existing = next((q for q in questions 
                     if q['student_name'] == student_name 
                     and q['question'] == question), None)
    
    if existing:
        existing['count'] = existing.get('count', 1) + 1
        existing['last_wrong_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        questions.append({
            'id': str(uuid.uuid4()),
            'student_name': student_name,
            'question': question,
            'category': category,
            'knowledge_point': knowledge_point,
            'student_answer': student_answer,
            'correct_answer': correct_answer,
            'count': 1,
            'mastered': False,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_wrong_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    
    save_wrong_questions(questions)


def get_recommended_review(student_name: str, limit: int = 5) -> List[Dict]:
    """根据错题本推荐复习内容"""
    questions = load_wrong_questions()
    student_wrong = [q for q in questions if q['student_name'] == student_name and not q.get('mastered', False)]
    
    # 按错误次数和最后错误时间排序
    student_wrong.sort(key=lambda x: (x.get('count', 1), x.get('last_wrong_time', '')), reverse=True)
    
    return student_wrong[:limit]


def record_learning_activity(student_name: str, activity_type: str, 
                             knowledge_point: str = "", score: float = None):
    """记录学习活动"""
    records = load_learning_records()
    if student_name not in records:
        records[student_name] = []
    
    records[student_name].append({
        'activity_type': activity_type,
        'knowledge_point': knowledge_point,
        'score': score,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'date': datetime.now().strftime('%Y-%m-%d')
    })
    
    # 只保留最近1000条记录
    if len(records[student_name]) > 1000:
        records[student_name] = records[student_name][-1000:]
    
    save_learning_records(records)


def calculate_job_match_score(student_scores: Dict, job_name: str) -> Dict:
    """计算学生与岗位的匹配度"""
    if job_name not in JOB_REQUIREMENTS:
        return {'match_rate': 0, 'gaps': [], 'strengths': []}
    
    job_req = JOB_REQUIREMENTS[job_name]
    total_score = 0
    total_weight = 0
    gaps = []
    strengths = []
    
    for area in COMPETENCE_AREAS:
        area_id = area['id']
        if area_id in job_req:
            student_score = student_scores.get(area_id, 0)
            required = job_req[area_id]
            gap = required - student_score
            
            if gap > 0.2:
                gaps.append({
                    'area': area['name'],
                    'current': student_score,
                    'required': required,
                    'gap': gap
                })
            elif student_score > required + 0.1:
                strengths.append({
                    'area': area['name'],
                    'current': student_score,
                    'required': required
                })
            
            total_score += student_score * area['weight']
            total_weight += area['weight']
    
    match_rate = (total_score / total_weight) * 100 if total_weight > 0 else 0
    
    return {
        'match_rate': round(match_rate, 1),
        'gaps': sorted(gaps, key=lambda x: x['gap'], reverse=True),
        'strengths': strengths
    }


def is_content_duplicate(new_content: str) -> bool:
    """检查内容是否已存在于知识库中。
    1) 规范化（去除所有空白）后 SHA256 完全一致 -> 同一文件重复上传
    2) 长度接近的已有条目，用 difflib 计算文本相似度 > 0.92 -> 同一文档的微调版本
    注意：不能用 Python 内置 hash() 的整数差值比较相似度——哈希值的数量级与内容
    相似性毫无关系，无关文档也会得到 >0.9 的"相似度"，造成大量误判；且哈希带进程随机盐。
    """
    kb_content = load_knowledge()
    if not kb_content:
        return False

    def normalize(text: str) -> str:
        return ''.join(text.split())

    new_norm = normalize(new_content)
    if len(new_norm) < 20:
        return False
    new_hash = hashlib.sha256(new_norm.encode('utf-8')).hexdigest()
    new_len = len(new_norm)

    for existing_entry in kb_content.split('=' * 50):
        existing_norm = normalize(existing_entry)
        if len(existing_norm) < 20:
            continue
        # 精确重复：规范化后的全文哈希一致
        existing_hash = hashlib.sha256(existing_norm.encode('utf-8')).hexdigest()
        if existing_hash == new_hash:
            return True
        # 高度相似：长度相差超过15%时相似度不可能达到0.92阈值，直接跳过以节省计算
        len_ratio = min(new_len, len(existing_norm)) / max(new_len, len(existing_norm))
        if len_ratio >= 0.85 and difflib.SequenceMatcher(None, new_norm, existing_norm).ratio() > 0.92:
            return True

    return False


def load_search_logs() -> List[Dict]:
    """加载搜索日志"""
    try:
        if os.path.exists(SEARCH_LOG_FILE):
            with open(SEARCH_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        print(f"搜索日志加载失败: {e}")
        return []


def save_search_logs(logs: List[Dict]):
    """保存搜索日志"""
    try:
        atomic_save_json(SEARCH_LOG_FILE, logs)
    except Exception as e:
        print(f"搜索日志保存失败: {e}")


# ====================== 学生档案管理 ======================
def load_students() -> List[Dict]:
    """加载学生档案"""
    try:
        if os.path.exists(STUDENTS_FILE):
            with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        print(f"学生档案加载失败: {e}")
        return []


def save_students(students: List[Dict]):
    """保存学生档案"""
    try:
        atomic_save_json(STUDENTS_FILE, students)
    except Exception as e:
        print(f"学生档案保存失败: {e}")


def next_student_id(students: List[Dict]) -> str:
    """生成不与现有档案冲突的新学生 ID。
    旧实现用 len(students)+1，删除学生后会复用已存在的 ID 造成撞号、删错人，
    故改为取现有最大数字 ID + 1。"""
    max_id = 0
    for s in students:
        try:
            max_id = max(max_id, int(s.get('id', 0)))
        except (TypeError, ValueError):
            continue
    return str(max_id + 1)


def load_classes() -> List[Dict]:
    """加载班级数据"""
    try:
        if os.path.exists(CLASSES_FILE):
            with open(CLASSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        print(f"班级数据加载失败: {e}")
        return []


def save_classes(classes: List[Dict]):
    """保存班级数据"""
    try:
        atomic_save_json(CLASSES_FILE, classes)
    except Exception as e:
        print(f"班级数据保存失败: {e}")


def load_notifications() -> List[Dict]:
    """加载通知数据"""
    try:
        if os.path.exists(NOTIFICATIONS_FILE):
            with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        print(f"通知数据加载失败: {e}")
        return []


def save_notifications(notifications: List[Dict]):
    """保存通知数据"""
    try:
        atomic_save_json(NOTIFICATIONS_FILE, notifications)
    except Exception as e:
        print(f"通知数据保存失败: {e}")


def load_homework() -> List[Dict]:
    """加载作业列表"""
    try:
        if os.path.exists(HOMEWORK_FILE):
            with open(HOMEWORK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"作业数据加载失败: {e}")
    return []


def save_homework(homework_list: List[Dict]):
    """保存作业列表"""
    try:
        atomic_save_json(HOMEWORK_FILE, homework_list)
    except Exception as e:
        print(f"作业数据保存失败: {e}")


def load_homework_submissions() -> List[Dict]:
    """加载作业提交记录"""
    try:
        if os.path.exists(HOMEWORK_SUBMISSIONS_FILE):
            with open(HOMEWORK_SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"作业提交数据加载失败: {e}")
    return []


def save_homework_submissions(submissions: List[Dict]):
    """保存作业提交记录"""
    try:
        atomic_save_json(HOMEWORK_SUBMISSIONS_FILE, submissions)
    except Exception as e:
        print(f"作业提交数据保存失败: {e}")


def load_self_assessment() -> Dict:
    """加载学生自评画像"""
    try:
        if os.path.exists(SELF_ASSESSMENT_FILE):
            with open(SELF_ASSESSMENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"自评数据加载失败: {e}")
    return {}


def save_self_assessment(data: Dict):
    """保存学生自评画像"""
    try:
        atomic_save_json(SELF_ASSESSMENT_FILE, data)
    except Exception as e:
        print(f"自评数据保存失败: {e}")


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_upload_filename(filename: str) -> str:
    """清洗上传文件名：去除路径成分与非法字符，但保留中文、空格等正常字符。
    不能直接用 werkzeug.secure_filename——它会把中文全部删光
    （如"通信原理课件.txt"会变成"txt"），造成历史记录丢名，
    且删除时短名容易匹配到其他文档条目导致误删。
    """
    filename = os.path.basename(filename.replace('\\', '/'))
    filename = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', filename)
    filename = filename.strip(' .')
    return filename or 'unnamed'


def save_uploaded_file(file, upload_type: str) -> Dict:
    """保存上传的文件"""
    if file and allowed_file(file.filename):
        # 生成唯一文件名
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # 保存文件
        file.save(file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        return {
            'filename': filename,
            'stored_filename': unique_filename,
            'file_path': file_path,
            'file_size': file_size,
            'type': upload_type
        }
    return {}


def get_file_type(filename: str) -> str:
    """根据文件扩展名判断文件类型"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov', 'mkv', 'webm']:
        return 'video'
    else:
        return 'document'


def extract_text_from_docx(file_path: str) -> str:
    """从docx文件中提取文本"""
    if not DOCX_AVAILABLE:
        return ""
    
    try:
        doc = DocxDocument(file_path)
        text = []
        for para in doc.paragraphs:
            if para.text.strip():
                text.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    row_text.append(cell.text.strip())
                if row_text:
                    text.append(' | '.join(row_text))
        return '\n\n'.join(text)
    except Exception as e:
        print(f"解析docx文件失败: {e}")
        return ""


def extract_text_from_pptx(file_path: str) -> str:
    """从pptx文件中提取文本"""
    if not PPTX_AVAILABLE:
        return ""
    
    try:
        prs = Presentation(file_path)
        text = []
        for slide in prs.slides:
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    slide_text.append(shape.text)
            if slide_text:
                text.append('\n'.join(slide_text))
                text.append('---')
        return '\n\n'.join(text)
    except Exception as e:
        print(f"解析pptx文件失败: {e}")
        return ""


def extract_pptx_structure(file_path: str) -> Dict:
    """从PPTX文件中提取章节结构和知识点"""
    if not PPTX_AVAILABLE:
        return {'chapters': [], 'knowledge_points': []}
    
    try:
        prs = Presentation(file_path)
        chapters = []
        all_text = []
        
        for idx, slide in enumerate(prs.slides, 1):
            slide_title = ""
            slide_content = []
            
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    text = shape.text.strip()
                    if not slide_title and (len(text) < 50 or '章' in text or '节' in text):
                        slide_title = text
                    else:
                        slide_content.append(text)
            
            if slide_title or slide_content:
                chapters.append({
                    'slide_num': idx,
                    'title': slide_title,
                    'content': '\n'.join(slide_content)
                })
                all_text.append(slide_title)
                all_text.extend(slide_content)
        
        knowledge_points = extract_knowledge_points('\n'.join(all_text))
        
        return {
            'chapters': chapters,
            'knowledge_points': knowledge_points
        }
    except Exception as e:
        print(f"提取PPT结构失败: {e}")
        return {'chapters': [], 'knowledge_points': []}


def extract_knowledge_points(text: str) -> List[str]:
    """从文本中提取知识点（基于知识图谱关键词）"""
    points = []
    text_lower = text.lower()
    
    for kp in KNOWLEDGE_GRAPH.keys():
        if kp in text or any(kw in text_lower for kw in kp.split()):
            points.append(kp)
    
    for area_id, keywords in COMPETENCE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower and kw not in points:
                points.append(kw)
    
    return list(set(points))[:20]


def extract_text_from_document(file_path: str) -> str:
    """根据文件类型提取文本内容"""
    ext = file_path.rsplit('.', 1)[1].lower() if '.' in file_path else ''
    
    if ext == 'docx':
        return extract_text_from_docx(file_path)
    elif ext == 'pptx':
        return extract_text_from_pptx(file_path)
    elif ext == 'txt':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()
    elif ext == 'pdf':
        return ""
    else:
        return ""


def analyze_competence(message: str) -> Dict:
    """分析消息涉及的能力领域"""
    scores = {}
    message_lower = message.lower()
    
    for area_id, keywords in COMPETENCE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in message_lower)
        scores[area_id] = min(count / len(keywords), 1.0)
    
    return scores


def update_student_profile(student_id: str, message: str, is_question: bool = True):
    """更新学生档案（基于对话内容）"""
    students = load_students()
    # 优先按学号查找，再按name查找，最后按id查找
    student = next((s for s in students if s.get('student_no') == student_id), None)
    if not student:
        student = next((s for s in students if s.get('name') == student_id), None)
    if not student:
        student = next((s for s in students if s['id'] == student_id), None)
    
    if not student:
        return
    
    # 分析能力领域
    competence_scores = analyze_competence(message)
    
    # 更新能力分析
    if 'competence_analysis' not in student:
        student['competence_analysis'] = {area['id']: {'count': 0, 'score': 0.0} for area in COMPETENCE_AREAS}
    
    for area_id, score in competence_scores.items():
        if score > 0:
            # setdefault 兼容旧数据：字段缺失或为空字典时自动补全领域键
            area_data = student['competence_analysis'].setdefault(area_id, {'count': 0, 'score': 0.0})
            area_data['count'] += 1
            # 加权平均更新分数
            current = area_data['score']
            area_data['score'] = (current * (area_data['count'] - 1) + score) / area_data['count']
    
    # 添加对话记录
    if 'conversation_history' not in student:
        student['conversation_history'] = []

    student['conversation_history'].append({
        'message': message,
        'is_question': is_question,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # 累计提问数：只要是学生主动提问就 +1，与是否命中能力关键词无关
    # （旧口径只在命中关键词时累加，导致问"什么是通信工程"这类问题不计次数）
    if is_question:
        student['total_questions'] = student.get('total_questions', 0) + 1
        # 同步写学习活动，驱动"学习曲线"
        record_learning_activity(student.get('name', ''), 'question')

    # 限制对话记录数量
    if len(student['conversation_history']) > 50:
        student['conversation_history'] = student['conversation_history'][-50:]

    save_students(students)


def generate_personalized_report(student_id: str) -> Dict:
    """生成学生个性化分析报告"""
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    
    if not student:
        return {'error': '学生不存在'}
    
    # 分析能力短板
    analysis = student.get('competence_analysis', {})
    weaknesses = []
    strengths = []
    
    for area in COMPETENCE_AREAS:
        area_id = area['id']
        score = analysis.get(area_id, {}).get('score', 0.0)
        count = analysis.get(area_id, {}).get('count', 0)
        
        if count >= 1:  # 降低阈值，至少1次对话就可以分析
            if score < 0.4:  # 调整阈值
                weaknesses.append({'area': area['name'], 'score': score, 'count': count})
            elif score > 0.6:  # 调整阈值
                strengths.append({'area': area['name'], 'score': score, 'count': count})
    
    # 按分数排序
    weaknesses.sort(key=lambda x: x['score'])
    strengths.sort(key=lambda x: x['score'], reverse=True)
    
    # 生成补习建议
    suggestions = []
    for weakness in weaknesses[:3]:
        suggestions.append(generate_suggestion(weakness['area']))
    
    # 推荐场景
    recommended_scenarios = recommend_scenarios(weaknesses)

    # 按5大类目聚合能力分数（用于雷达图：理论基础/专业核心/工程实践/工程伦理/综合素质）
    categories = {}
    for area in COMPETENCE_AREAS:
        cat = area.get('category', '综合素质')
        score = analysis.get(area['id'], {}).get('score', 0.0)
        if cat not in categories:
            categories[cat] = {'total': 0.0, 'n': 0}
        categories[cat]['total'] += score  # 未互动的领域按0分计入，雷达图能体现空白维度
        categories[cat]['n'] += 1
    radar = [{'category': k, 'score': round(v['total'] / v['n'], 3)} for k, v in categories.items()]

    return {
        'student': student['name'],
        'weaknesses': weaknesses,
        'strengths': strengths,
        'suggestions': suggestions,
        'recommended_scenarios': recommended_scenarios,
        'total_conversations': student.get(
            'total_questions',
            sum(1 for m in (student.get('conversation_history') or []) if m.get('is_question', True))
        ),
        'radar': radar
    }


def generate_suggestion(area_name: str) -> str:
    """针对特定领域生成补习建议"""
    suggestions = {
        "信号与系统": "建议复习傅里叶变换、拉普拉斯变换等核心概念，多做卷积和系统响应的练习题。推荐教材：《信号与系统》（奥本海姆）",
        "通信原理": "重点学习香农定理、信道编码、调制解调技术。建议通过仿真软件如MATLAB/Simulink进行实践。",
        "数字信号处理": "加强采样定理、FFT变换、数字滤波器设计的学习。可以尝试用Python实现简单的信号处理算法。",
        "网络协议": "系统学习TCP/IP协议栈，理解HTTP、UDP等协议的工作原理。建议搭建小型网络进行实践。",
        "调制技术": "深入理解ASK、FSK、PSK、QAM等调制方式的原理和应用场景。分析星座图的特点。",
        "射频工程": "学习天线原理、阻抗匹配、功率放大器设计。可以通过实验板进行射频电路的调试。",
        "故障排查": "培养系统排查思路，学习常用诊断工具的使用。多参与实际故障案例分析。"
    }
    return suggestions.get(area_name, f"建议加强{area_name}的学习，多做相关练习和实践。")


def build_student_analysis_prompt(student: Dict):
    """组装学生AI个性化分析的 system 与 prompt，返回 (system, prompt)"""
    name = student.get('name', '该学生')

    # 1) 对话历史（只取最近15条，控制上下文长度）
    conv_history = student.get('conversation_history') or []
    recent_conv = conv_history[-15:]
    conv_text = '\n'.join(
        f"- [{m.get('timestamp','')}] {'问' if m.get('is_question') else '说'}：{m.get('message','')[:120]}"
        for m in recent_conv
    ) or '（暂无对话记录）'

    # 2) 能力维度得分
    competence = student.get('competence_analysis') or {}
    comp_lines = []
    for area in COMPETENCE_AREAS:
        aid = area['id']
        data = competence.get(aid, {})
        score = data.get('score', 0.0)
        count = data.get('count', 0)
        pct = round(score * 100)
        comp_lines.append(f"- {area['name']}（{area['category']}）：掌握度 {pct}%，互动 {count} 次")
    comp_text = '\n'.join(comp_lines)

    # 3) 错题本（最近10条）
    wrong_qs = load_wrong_questions()
    student_wrong = [q for q in wrong_qs if q.get('student_name') == name][-10:]
    wrong_text = '\n'.join(
        f"- [{q.get('knowledge_point','未分类')}] {str(q.get('question',''))[:100]}"
        for q in student_wrong
    ) if student_wrong else '（暂无错题记录）'

    # 4) 学习记录（题目/实训，只保留汇总与最近5条）
    records = load_learning_records()
    student_records = records.get(name, [])[-30:]
    type_counts = {}
    for r in student_records:
        t = r.get('activity_type', 'other')
        type_counts[t] = type_counts.get(t, 0) + 1
    rec_summary = '、'.join(f"{t}:{c}次" for t, c in type_counts.items()) or '（暂无学习记录）'
    rec_detail = '\n'.join(
        f"- [{r.get('timestamp','')}] {r.get('activity_type','')} {r.get('knowledge_point','')} 得分:{r.get('score','-')}"
        for r in student_records[-5:]
    )

    total_q = student.get('total_questions', len([m for m in conv_history if m.get('is_question')]))

    system_content = '你是通信工程专业的资深教学导师，擅长根据学生的学习数据给出精准、实用的能力分析和学习建议。回答要专业但不晦涩，建议要具体可执行。'
    prompt = f"""你是一名通信工程专业的资深教学导师。请根据以下学生数据，对该学生进行综合能力分析。

【学生基本信息】
姓名：{name}
累计提问次数：{total_q}
对话历史条数：{len(conv_history)}

【最近对话内容】
{conv_text}

【12维能力掌握度】
{comp_text}

【错题记录】
{wrong_text}

【学习/实训记录统计】
{rec_summary}
最近学习记录：
{rec_detail}

请输出结构化分析，严格按以下格式返回（不要添加多余说明）：

【优势】
（列出2-4个该学生表现较好的方面，结合具体数据说明）

【不足】
（列出2-4个该学生需要提升的方面，结合具体数据说明）

【学习建议】
（给出3-5条具体可执行的学习建议，针对其不足，要结合通信工程专业特点）

【整体评价】
（用1-2句话概括该学生当前的学习状态与成长方向）"""
    return system_content, prompt


def analysis_sse_generator(system_content: str, prompt: str, max_tokens: int = 1200, temperature: float = 0.7):
    """通用AI分析流式生成器（SSE）：data: {"content": "..."}，结束发送 [DONE]"""
    payload = {
        "model": MODEL_FLASH,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "enable_thinking": False  # 关闭长思考链，避免先思考30秒+才输出
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    def generate():
        got_any = False
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
            if resp.status_code != 200:
                yield f"data: {json.dumps({'error': f'AI分析失败: {resp.status_code}'}, ensure_ascii=False)}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                try:
                    chunk_json = json.loads(data)
                    choices = chunk_json.get('choices') or []
                    if choices:
                        chunk = choices[0].get('delta', {}).get('content', '')
                        if chunk:
                            got_any = True
                            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    continue
            if not got_any:
                yield f"data: {json.dumps({'error': 'AI未返回内容，请稍后重试'}, ensure_ascii=False)}\n\n"
        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'AI分析超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'AI分析出错: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return Response(
        generate(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no'
        }
    )


def recommend_scenarios(weaknesses: List[Dict]) -> List[Dict]:
    """根据短板推荐场景"""
    recommended = []
    
    weakness_areas = [w['area'] for w in weaknesses]
    
    # 根据短板匹配场景
    if "故障排查" in weakness_areas or "网络协议" in weakness_areas:
        recommended.append({
            "id": 2,
            "title": "网络故障排查工程师",
            "reason": "适合提升网络故障排查能力"
        })
    
    if "调制技术" in weakness_areas or "射频工程" in weakness_areas:
        recommended.append({
            "id": 1,
            "title": "新入职通信工程师",
            "reason": "适合学习基站安装调试和调制技术"
        })
    
    if "通信原理" in weakness_areas or "信号与系统" in weakness_areas:
        recommended.append({
            "id": 3,
            "title": "通信系统优化工程师",
            "reason": "适合深入理解通信系统设计和优化"
        })
    
    return recommended


def add_search_log(query: str, content: str, is_from_kb: bool = False):
    """添加搜索记录"""
    logs = load_search_logs()
    log_entry = {
        "id": len(logs) + 1,
        "query": query,
        "content": content,
        "is_from_kb": is_from_kb,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reviewed": False,
        "note": ""
    }
    logs.append(log_entry)
    save_search_logs(logs)
    return log_entry


# 加载知识库
knowledge_content = load_knowledge()

# ====================== 智能意图识别 ======================
INTENT_PATTERNS = [
    {
        'intent': 'concept_understanding',
        'name': '概念理解',
        'patterns': [
            r'什么是(.+)',
            r'.+是什么',
            r'.+的定义',
            r'.+的概念',
            r'.+的含义',
            r'.+是什么意思',
            r'.+指的是什么'
        ]
    },
    {
        'intent': 'principle_analysis',
        'name': '原理分析',
        'patterns': [
            r'.+的原理',
            r'.+的工作原理',
            r'.+为什么',
            r'.+背后的原理',
            r'.+的机制',
            r'.+是如何工作的',
            r'.+的数学原理',
            r'.+公式推导'
        ]
    },
    {
        'intent': 'method_steps',
        'name': '方法步骤',
        'patterns': [
            r'如何(.+)',
            r'.+的步骤',
            r'.+的方法',
            r'.+怎么操作',
            r'.+的流程',
            r'.+的做法',
            r'.+的实现步骤'
        ]
    },
    {
        'intent': 'comparison_analysis',
        'name': '对比分析',
        'patterns': [
            r'.+和.+的区别',
            r'.+与.+的差异',
            r'.+对比.+',
            r'.+和.+哪个好',
            r'.+和.+的优缺点',
            r'.+与.+的异同'
        ]
    },
    {
        'intent': 'problem_solving',
        'name': '问题解决',
        'patterns': [
            r'.+怎么处理',
            r'.+怎么解决',
            r'.+的解决方案',
            r'.+故障排查',
            r'.+问题分析',
            r'.+报错',
            r'.+故障',
            r'.+异常'
        ]
    },
    {
        'intent': 'application_scenario',
        'name': '应用场景',
        'patterns': [
            r'.+的应用',
            r'.+的应用场景',
            r'.+在哪里使用',
            r'.+的用途',
            r'.+的实际应用',
            r'.+的例子'
        ]
    },
    {
        'intent': 'knowledge_review',
        'name': '知识复习',
        'patterns': [
            r'.+复习',
            r'.+知识点',
            r'.+学习',
            r'.+总结',
            r'.+重点',
            r'.+考点'
        ]
    }
]

def identify_intent(query: str) -> Dict:
    """识别用户提问意图"""
    query_lower = query.lower()
    
    for intent_info in INTENT_PATTERNS:
        for pattern in intent_info['patterns']:
            if re.search(pattern, query_lower):
                return {
                    'intent': intent_info['intent'],
                    'name': intent_info['name'],
                    'confidence': 0.85
                }
    
    return {
        'intent': 'general_question',
        'name': '一般问题',
        'confidence': 0.5
    }

# ====================== 动态提示词生成 ======================
def _build_kb_context(query: str):
    """构造知识库上下文：优先 RAG 召回最相关片段，索引不可用时退回全文注入。

    返回 (context_text, meta)。meta 用于接口/日志展示召回来源与提示词压缩比，
    让「用了 RAG」这件事可被观察和验证。
    """
    total_chars = len(knowledge_content or '')
    if RAG_MODULE_AVAILABLE:
        try:
            chunks = rag_retriever.search(query, top_k=rag_retriever.TOP_K)
            if chunks:
                used = sum(len(c['text']) for c in chunks)
                return rag_retriever.format_context(chunks), {
                    'mode': 'rag',
                    'chunks': len(chunks),
                    'used_chars': used,
                    'total_chars': total_chars,
                    'compress_ratio': round(1 - used / total_chars, 3) if total_chars else 0,
                    'degraded': bool(chunks[0].get('degraded')),
                    'sources': [
                        {'title': c['title'], 'source': c['source'], 'score': c['score'],
                         'vector_score': c['vector_score'], 'keyword_score': c['keyword_score']}
                        for c in chunks
                    ],
                }
        except Exception as e:  # noqa: BLE001 - 召回异常绝不阻断问答
            print(f"[RAG] 召回失败，退回全文注入: {e}")
    return (knowledge_content or ""), {
        'mode': 'full', 'chunks': 0, 'used_chars': total_chars, 'total_chars': total_chars,
        'compress_ratio': 0, 'degraded': False, 'sources': [],
    }


def generate_system_prompt(query: str, mode: str = 'fast') -> str:
    """根据用户查询动态生成系统提示词，集成 RAG 召回、知识图谱上下文和意图识别"""
    kg_results = search_knowledge_graph(query)
    intent = identify_intent(query)
    kb_context, _kb_meta = _build_kb_context(query)
    
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

【知识库】
{kb_context if kb_context else "（知识库为空）"}
{kg_context}

要求：
1. 严格依据知识库检索结果回答，引用时标注来源片段编号
2. 如果涉及多个知识点，说明它们之间的关联关系
3. 回答要专业、准确，符合通信工程领域规范
"""
    
    if mode == 'deep':
        base_prompt += """
4. 深入分析问题，给出多个角度的解释
5. 如果需要，分点说明
6. 提供实用的建议或解决方案
7. 引用相关知识点的关联关系
"""
    else:
        base_prompt += """
4. 回答要简洁明了
5. 控制回答长度在300字以内
"""
    
    return base_prompt

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

def create_scenario_prompt(scenario_info=None):
    """创建剧情演绎的系统提示词"""
    base_prompt = f"""
你是灵智尚人，通信工程专业的职业导师。现在正在进行剧情演绎，帮助学生模拟未来的工作场景。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

你的角色是：
- 引导学生完成剧情任务
- 在学生遇到困难时提供专业指导
- 对学生的解决方案给出客观评价
- 结合实际工作场景给出建议

要求：
1. 引导式教学，不要直接给出答案
2. 结合通信工程专业知识
3. 保持对话的连贯性和代入感
4. 鼓励学生独立思考和动手实践
"""
    
    if scenario_info:
        scenario_title = scenario_info.get('title', '')
        scenario_description = scenario_info.get('description', '')
        scenario_tasks = scenario_info.get('tasks', [])
        
        scenario_context = f"""
【当前剧情场景】
场景名称：{scenario_title}
场景描述：{scenario_description}
"""
        if scenario_tasks:
            scenario_context += f"\n目标任务：\n"
            for i, task in enumerate(scenario_tasks, 1):
                scenario_context += f"{i}. {task}\n"
        
        scenario_context += "\n请根据以上设定的剧情场景进行引导式教学。"
        base_prompt += scenario_context
    
    return base_prompt

SYSTEM_PROMPT_SCENARIO = create_scenario_prompt()


# ====================== 路由 ======================
@app.route('/')
def index():
    # 检查是否已验证
    if session.get('authenticated'):
        return render_template('index.html')
    else:
        return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # GET：直接访问 /login 时渲染登录页（未登录），已登录跳首页；避免 405 白页
    if request.method == 'GET':
        if session.get('authenticated'):
            return redirect(url_for('index'))
        return render_template('login.html')
    data = request.get_json()
    password = data.get('password', '')
    role = data.get('role', 'student')
    student_no = data.get('student_no', '')
    student_name = data.get('student_name', '')
    class_name = data.get('class_name', '')
    
    if role == 'teacher':
        # 老师登录：校验哈希密码（历史明文已在启动时迁移为哈希，明文不再落盘）
        if SECURITY_MODULE_AVAILABLE:
            ok = security.verify_teacher(student_name, password)
        else:
            ok = TEACHER_ACCOUNTS.get(student_name) == password
        if ok:
            session['authenticated'] = True
            session['role'] = 'teacher'
            session['student_name'] = student_name
            if SECURITY_MODULE_AVAILABLE:
                security.audit('login', target=f'teacher:{student_name}', detail='老师登录成功')
            return jsonify({'success': True})
        else:
            if SECURITY_MODULE_AVAILABLE:
                security.audit('login_failed', target=f'teacher:{student_name}', detail='老师账号或密码错误')
            return jsonify({'success': False, 'message': '老师账号或密码错误'})
    
    # 学生登录：使用统一访问密码（哈希校验）
    if SECURITY_MODULE_AVAILABLE:
        password_ok = security.verify_access_password(password)
    else:
        password_ok = password == ACCESS_PASSWORD
    if password_ok:
        session['authenticated'] = True
        session['role'] = role
        is_new_user = False

        # 如果是学生，存储学生信息并创建/更新学生档案
        if role == 'student' and student_no:
            # 验证学号必须是13位数字
            if not student_no.isdigit() or len(student_no) != 13:
                return jsonify({'success': False, 'message': '学号必须是13位数字'})

            session['student_no'] = student_no
            session['student_name'] = student_name
            session['class_name'] = class_name

            # 创建或更新学生档案
            students = load_students()
            existing_student = next((s for s in students if s.get('student_no') == student_no), None)

            if existing_student:
                # 一个学号只能对应一个账号：姓名不一致则拒绝登录
                if existing_student.get('name') and existing_student['name'] != student_name:
                    return jsonify({'success': False,
                                    'message': f'该学号已绑定姓名"{existing_student["name"]}"，一个学号只能对应一个账号'})
                # 更新现有学生信息
                if class_name:
                    existing_student['class_name'] = class_name
                existing_student['last_login'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                # 创建新学生
                is_new_user = True
                new_student = {
                    'id': next_student_id(students),
                    'student_no': student_no,
                    'name': student_name,
                    'class_name': class_name,
                    'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'last_login': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'competence_analysis': {area['id']: {'count': 0, 'score': 0.0} for area in COMPETENCE_AREAS},
                    'conversation_history': []
                }
                students.append(new_student)

            save_students(students)

        elif role == 'student' and student_name:
            # 未填学号的学生：按姓名关联已有档案（如老师手工添加的），没有则创建无学号档案
            # 否则聊天时找不到档案，能力数据无法记录
            session['student_name'] = student_name
            if class_name:
                session['class_name'] = class_name

            students = load_students()
            existing_student = next((s for s in students if s.get('name') == student_name), None)

            if existing_student:
                if class_name:
                    existing_student['class_name'] = class_name
                existing_student['last_login'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                is_new_user = True
                new_student = {
                    'id': next_student_id(students),
                    'student_no': '',
                    'name': student_name,
                    'class_name': class_name,
                    'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'last_login': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'competence_analysis': {area['id']: {'count': 0, 'score': 0.0} for area in COMPETENCE_AREAS},
                    'conversation_history': []
                }
                students.append(new_student)

            save_students(students)

        if SECURITY_MODULE_AVAILABLE:
            security.audit('login', target=f"student:{student_no or student_name}",
                           detail=f"学生登录成功（{'新用户' if is_new_user else '老用户'}）")
        return jsonify({'success': True, 'is_new_user': is_new_user, 'student_name': student_name})
    else:
        if SECURITY_MODULE_AVAILABLE:
            security.audit('login_failed', target=f"student:{student_no or student_name}",
                           detail='访问密码错误')
        return jsonify({'success': False, 'message': '密码错误'})


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('authenticated', None)
    session.pop('role', None)
    session.pop('student_name', None)
    session.pop('class_name', None)
    return jsonify({'success': True})


@app.after_request
def no_cache_html(response):
    """HTML页面不缓存，避免部署后浏览器拿到旧页面"""
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route('/current-user', methods=['GET'])
def get_current_user():
    """获取当前登录用户信息"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    return jsonify({
        'authenticated': True,
        'role': session.get('role', 'student'),
        'student_name': session.get('student_name', ''),
        'student_no': session.get('student_no', ''),
        'class_name': session.get('class_name', ''),
        'avatar_url': _find_avatar(session.get('role', 'student'), session.get('student_name', ''))
    })


# ====================== 用户头像API ======================
def _avatar_prefix(role, username):
    """按 角色_用户名 生成头像文件名前缀（学生和教师互不冲突）"""
    safe = re.sub(r'[^\w\u4e00-\u9fff-]', '_', f"{role}_{username or 'guest'}")
    return f"avatar_{safe}"


def _find_avatar(role, username):
    """查找用户当前头像的访问URL，没有则返回None"""
    prefix = _avatar_prefix(role, username)
    for ext in ALLOWED_AVATAR_EXT:
        if os.path.exists(os.path.join(AVATAR_DIR, f"{prefix}.{ext}")):
            return f"/avatars/{prefix}.{ext}"
    return None


@app.route('/api/avatar', methods=['POST'])
def upload_avatar():
    """上传/更换当前登录用户的头像"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    file = request.files.get('avatar')
    if not file or not file.filename:
        return jsonify({'error': '请选择图片文件'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_AVATAR_EXT:
        return jsonify({'error': '只支持 png/jpg/jpeg/gif/webp 格式'}), 400

    data = file.read()
    if len(data) > 2 * 1024 * 1024:
        return jsonify({'error': '头像图片不能超过2MB'}), 400

    role = session.get('role', 'student')
    username = session.get('student_name', '')
    prefix = _avatar_prefix(role, username)

    # 删除旧头像（不同扩展名的旧文件），保证一个用户只保留最新一张
    for old_ext in ALLOWED_AVATAR_EXT:
        old_path = os.path.join(AVATAR_DIR, f"{prefix}.{old_ext}")
        if old_ext != ext and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    with open(os.path.join(AVATAR_DIR, f"{prefix}.{ext}"), 'wb') as f:
        f.write(data)

    return jsonify({'success': True, 'avatar_url': f"/avatars/{prefix}.{ext}"})


@app.route('/avatars/<path:filename>')
def serve_avatar(filename):
    """提供头像图片访问"""
    return send_from_directory(AVATAR_DIR, filename)


@app.route('/api/update-class', methods=['POST'])
def update_my_class():
    """学生自主修改所在班级（仅限已创建的班级）"""
    if not session.get('authenticated') or session.get('role') != 'student':
        return jsonify({'error': '仅学生可修改班级'}), 403
    data = request.get_json(silent=True) or {}
    class_name = str(data.get('class_name', '')).strip()
    if not class_name:
        return jsonify({'error': '请选择班级'}), 400
    if len(class_name) > 30:
        return jsonify({'error': '班级名称过长'}), 400
    valid_names = {c.get('name') for c in load_classes() if c.get('name')}
    if valid_names and class_name not in valid_names:
        return jsonify({'error': '班级不存在，请从列表中选择'}), 400
    student_no = str(session.get('student_no') or '')
    student_name = session.get('student_name', '')
    students = load_students()
    target = next((s for s in students
                   if (student_no and s.get('student_no') == student_no)
                   or (not student_no and s.get('name') == student_name)), None)
    if target is None:
        return jsonify({'error': '未找到学生档案，请联系老师'}), 404
    old = target.get('class_name', '')
    target['class_name'] = class_name
    save_students(students)
    session['class_name'] = class_name
    try:
        security.audit('class_self_update', target=class_name,
                       detail=f'学生 {student_name}({student_no}) 修改班级: {old or "未分班"} -> {class_name}')
    except Exception:
        pass
    return jsonify({'success': True, 'class_name': class_name})


# ====================== 班级管理API ======================
@app.route('/api/classes', methods=['GET'])
def get_classes():
    """获取所有班级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    classes = load_classes()
    return jsonify({'classes': classes})


@app.route('/api/classes', methods=['POST'])
def create_class():
    """创建班级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能创建班级'}), 403
    
    data = request.get_json()
    class_name = data.get('name', '').strip()
    
    if not class_name:
        return jsonify({'error': '班级名称不能为空'}), 400
    
    classes = load_classes()
    
    # 检查班级是否已存在
    if any(c['name'] == class_name for c in classes):
        return jsonify({'error': '班级已存在'}), 400
    
    new_class = {
        'id': len(classes) + 1,
        'name': class_name,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'student_count': 0
    }
    
    classes.append(new_class)
    save_classes(classes)
    
    if SECURITY_MODULE_AVAILABLE:
        security.audit('class_create', target=class_name, detail=f'新建班级 id={new_class["id"]}',
                       after={'name': class_name})
    return jsonify({'success': True, 'class': new_class})


@app.route('/api/classes/<int:class_id>', methods=['PUT'])
def update_class(class_id):
    """更新班级信息"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能更新班级'}), 403
    
    data = request.get_json()
    class_name = data.get('name', '').strip()
    
    classes = load_classes()
    class_obj = next((c for c in classes if c['id'] == class_id), None)
    
    if not class_obj:
        return jsonify({'error': '班级不存在'}), 404
    
    # 检查新名称是否与其他班级冲突
    if class_name and any(c['name'] == class_name and c['id'] != class_id for c in classes):
        return jsonify({'error': '班级名称已存在'}), 400
    
    old_name = class_obj.get('name', '')
    if class_name:
        class_obj['name'] = class_name
    
    save_classes(classes)
    if SECURITY_MODULE_AVAILABLE and class_name and class_name != old_name:
        security.audit('class_update', target=class_name, detail=f'班级 id={class_id} 更名',
                       before={'name': old_name}, after={'name': class_name})
    return jsonify({'success': True, 'class': class_obj})


@app.route('/api/classes/<int:class_id>', methods=['DELETE'])
def delete_class(class_id):
    """删除班级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能删除班级'}), 403
    
    classes = load_classes()
    target = next((c for c in classes if c['id'] == class_id), None)
    classes = [c for c in classes if c['id'] != class_id]
    save_classes(classes)
    
    if SECURITY_MODULE_AVAILABLE and target:
        security.audit('class_delete', target=target.get('name', str(class_id)),
                       detail=f'删除班级 id={class_id}',
                       before={'name': target.get('name', ''), 'student_count': target.get('student_count', 0)})
    return jsonify({'success': True})


@app.route('/api/classes/<int:class_id>/students', methods=['GET'])
def get_class_students(class_id):
    """获取班级成员列表（含姓名，仅限老师，避免学生枚举同学名单）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if SECURITY_MODULE_AVAILABLE and session.get('role') != 'teacher':
        security.audit('login_failed', target=f"class_roster:{class_id}",
                       detail='非教师尝试读取班级名册，已拒绝')
        return jsonify({'error': '权限不足：该操作仅限老师'}), 403

    classes = load_classes()
    class_obj = next((c for c in classes if c['id'] == class_id), None)
    
    if not class_obj:
        return jsonify({'error': '班级不存在'}), 404
    
    # 获取该班级的所有学生
    students = load_students()
    class_students = [s for s in students if s.get('class_name') == class_obj['name']]
    
    # 只返回必要的信息
    student_list = [{
        'id': s['id'],
        'name': s.get('name', s['id']),
        'created_at': s.get('created_at', '')
    } for s in class_students]
    
    return jsonify({
        'class_name': class_obj['name'],
        'students': student_list
    })


@app.route('/api/classes/<int:class_id>/students', methods=['POST'])
def add_student_to_class(class_id):
    """添加学生到班级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能添加学生'}), 403
    
    classes = load_classes()
    class_obj = next((c for c in classes if c['id'] == class_id), None)
    
    if not class_obj:
        return jsonify({'error': '班级不存在'}), 404
    
    data = request.get_json()
    student_name = data.get('name', '').strip()
    
    if not student_name:
        return jsonify({'error': '学生姓名不能为空'}), 400
    
    students = load_students()
    
    # 检查学生是否已存在
    existing_student = next((s for s in students if s.get('name') == student_name or s['id'] == student_name), None)
    
    if existing_student:
        # 更新学生的班级
        existing_student['class_name'] = class_obj['name']
    else:
        # 创建新学生
        new_student = {
            'id': student_name,
            'name': student_name,
            'class_name': class_obj['name'],
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'competence_analysis': {area['id']: {'count': 0, 'score': 0.0} for area in COMPETENCE_AREAS},
            'conversation_history': []
        }
        students.append(new_student)
    
    save_students(students)
    
    # 更新班级的学生数量
    class_obj['student_count'] = len([s for s in students if s.get('class_name') == class_obj['name']])
    save_classes(classes)
    
    if SECURITY_MODULE_AVAILABLE:
        security.audit('class_add_student', target=student_name,
                       detail=f'加入班级 {class_obj["name"]}（id={class_id}）',
                       after={'class_name': class_obj['name']})
    return jsonify({'success': True, 'message': f'学生 {student_name} 已添加到班级'})


@app.route('/api/classes/<int:class_id>/students/<student_id>', methods=['DELETE'])
def remove_student_from_class(class_id, student_id):
    """从班级移除学生"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能移除学生'}), 403
    
    classes = load_classes()
    class_obj = next((c for c in classes if c['id'] == class_id), None)
    
    if not class_obj:
        return jsonify({'error': '班级不存在'}), 404
    
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    # 移除学生的班级信息
    student['class_name'] = ''
    save_students(students)
    
    # 更新班级的学生数量
    class_obj['student_count'] = len([s for s in students if s.get('class_name') == class_obj['name']])
    save_classes(classes)
    
    if SECURITY_MODULE_AVAILABLE:
        security.audit('class_remove_student', target=student.get('name', student_id),
                       detail=f'移出班级 {class_obj["name"]}（id={class_id}）',
                       before={'class_name': class_obj['name']}, after={'class_name': ''})
    return jsonify({'success': True, 'message': f'学生已从班级移除'})


# ====================== 通知管理API ======================
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """获取通知列表"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    notifications = load_notifications()
    current_user = session.get('student_name', '')
    current_class = session.get('class_name', '')
    user_role = session.get('role', 'student')
    
    # 筛选通知
    filtered_notifications = []
    for notif in notifications:
        if user_role == 'teacher':
            # 老师可以看到自己发送的所有通知
            if current_user:
                if notif.get('sender') == current_user:
                    filtered_notifications.append(notif)
            else:
                # 如果没有登录用户名，显示所有通知（管理员视角）
                filtered_notifications.append(notif)
        else:
            # 学生只能看到发给所在班级的通知
            if notif.get('class_name') == current_class:
                filtered_notifications.append(notif)
    
    # 按时间倒序排列
    filtered_notifications.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return jsonify({'notifications': filtered_notifications})


@app.route('/api/notifications', methods=['POST'])
def create_notification():
    """发送通知"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能发送通知'}), 403
    
    # 获取表单数据
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    class_name = request.form.get('class_name', '').strip()
    
    # 处理文件上传
    attachments = []
    
    # 处理图片上传
    for file in request.files.getlist('images'):
        if file and file.filename:
            saved_file = save_uploaded_file(file, 'image')
            if saved_file:
                attachments.append(saved_file)
    
    # 处理文档上传
    for file in request.files.getlist('documents'):
        if file and file.filename:
            saved_file = save_uploaded_file(file, 'document')
            if saved_file:
                attachments.append(saved_file)
    
    # 处理视频上传
    for file in request.files.getlist('videos'):
        if file and file.filename:
            saved_file = save_uploaded_file(file, 'video')
            if saved_file:
                attachments.append(saved_file)
    
    # 验证：标题不能为空
    if not title:
        return jsonify({'error': '通知标题不能为空'}), 400
    
    # 验证：必须选择班级
    if not class_name:
        return jsonify({'error': '请选择班级'}), 400
    
    # 验证：内容或附件至少有一个
    if not content and not attachments:
        return jsonify({'error': '通知内容和附件至少填写一项'}), 400
    
    notifications = load_notifications()
    
    new_notification = {
        'id': len(notifications) + 1,
        'title': title,
        'content': content,
        'class_name': class_name,
        'sender': session.get('student_name', '老师'),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'read': False,
        'attachments': attachments
    }
    
    notifications.append(new_notification)
    save_notifications(notifications)
    
    return jsonify({'success': True, 'notification': new_notification})


@app.route('/api/notifications/<int:notification_id>', methods=['PUT'])
def mark_notification_read(notification_id):
    """标记通知为已读"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    notifications = load_notifications()
    notification = next((n for n in notifications if n['id'] == notification_id), None)
    
    if not notification:
        return jsonify({'error': '通知不存在'}), 404
    
    notification['read'] = True
    save_notifications(notifications)
    
    return jsonify({'success': True})


@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    """删除通知"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    notifications = load_notifications()
    
    # 找到要删除的通知
    notification = next((n for n in notifications if n['id'] == notification_id), None)
    
    if not notification:
        return jsonify({'error': '通知不存在'}), 404
    
    # 只能删除自己发送的通知
    current_user = session.get('student_name', '')
    if notification.get('sender') != current_user:
        return jsonify({'error': '只能删除自己发送的通知'}), 403
    
    # 删除通知
    notifications = [n for n in notifications if n['id'] != notification_id]
    
    save_notifications(notifications)
    return jsonify({'success': True})


# ====================== 学生班级分配API ======================
@app.route('/api/students/<int:student_id>/class', methods=['PUT'])
def assign_student_to_class(student_id):
    """将学生分配到班级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能分配班级'}), 403
    
    data = request.get_json()
    class_name = data.get('class_name', '')
    
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    student['class_name'] = class_name
    save_students(students)
    
    # 更新班级学生数量
    update_class_student_counts()
    
    return jsonify({'success': True, 'student': student})


def update_class_student_counts():
    """更新各班级的学生数量"""
    classes = load_classes()
    students = load_students()
    
    for class_obj in classes:
        class_obj['student_count'] = len([s for s in students if s.get('class_name') == class_obj['name']])
    
    save_classes(classes)


SYSTEM_PROMPT_PET = """你是"灵智小助手"，一只住在"灵智尚人 AI 工程训练平台"页面右下角的桌面宠物，是平台主 AI 助手的 Q 版分身。

性格设定：机灵、话痨、爱开玩笑、偶尔傲娇，像一只精力旺盛的电子小仓鼠。

说话规则（必须遵守）：
1. 像微信聊天一样口语化，短句为主，最多两三句话，绝不写长篇大论、绝不分点论述
2. 每条回复都要带点幽默感：可以玩梗、抖机灵、自嘲、用可爱语气词（嘿嘿、哼、哎呀、哒）
3. 每条回复最多 1-2 个表情，不要堆砌
4. 用户问正经问题（比如知识点）也用轻松的方式答：先给答案，再补一句俏皮话或神比喻
5. 不确定的事就撒娇打岔，不要瞎编
6. 不要自称"AI助手"，自称"本宠"或"小灵我"
7. 直接给答案，不要复述问题，不要说"从某某角度来说"这种学术腔
"""

@app.route('/chat', methods=['POST'])
def chat_endpoint():
    # 检查是否已验证
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    try:
        data = request.get_json()
        print(f"收到聊天请求: {json.dumps(data, ensure_ascii=False)[:500]}")
        
        user_message = data.get('message', '')
        image_data = data.get('image', '')
        mode = data.get('mode', 'fast')
        stream = data.get('stream', True)
        is_scenario = data.get('is_scenario', False)
        scenario_info = data.get('scenario_info', None)
        conversation_history = data.get('conversation_history', [])
        persona = data.get('persona', '')  # 'pet' = 桌宠幽默模式
        
        # 获取当前学生信息（用于更新档案）
        current_role = session.get('role', 'student')
        current_student_name = session.get('student_name', '')
        current_student_no = session.get('student_no', '')
        
        # 检查是否需要搜索记录（这里简化处理，实际可以通过关键词匹配判断）
        query_lower = user_message.lower()
        needs_search = True  # 改为记录所有对话，方便用户后续审核
        if persona == 'pet':
            needs_search = False  # 桌宠闲聊不记入学习日志
        
        # 选择提示词
        if persona == 'pet':
            system_prompt = SYSTEM_PROMPT_PET
            temperature = 0.9
            max_tokens = 200
        elif is_scenario:
            if scenario_info:
                system_prompt = create_scenario_prompt(scenario_info)
            else:
                system_prompt = SYSTEM_PROMPT_SCENARIO
            temperature = 0.8
            max_tokens = 4000
        else:
            system_prompt = generate_system_prompt(user_message, mode)
            temperature = 0.85 if mode == 'deep' else 0.6
            max_tokens = 4000 if mode == 'deep' else 2000
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        # 处理图片
        if image_data:
            # 检查是否是完整的Data URL（包含data:image/...base64,）
            if image_data.startswith('data:image/'):
                # 已经是完整的Data URL，直接使用
                image_url = image_data
            else:
                # 假设是base64编码的数据，默认使用PNG格式
                image_url = f"data:image/png;base64,{image_data}"
            
            user_content = [
                {"type": "text", "text": user_message or "请描述这张图片的内容"},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        else:
            user_content = user_message
        
        # 构建消息列表（包含对话历史）
        messages = [{"role": "system", "content": system_prompt}]
        
        # 添加历史对话
        for msg in conversation_history:
            if msg.get('role') == 'user':
                messages.append({"role": "user", "content": msg.get('content', '')})
            elif msg.get('role') == 'assistant':
                messages.append({"role": "assistant", "content": msg.get('content', '')})
        
        # 添加当前用户消息
        messages.append({"role": "user", "content": user_content})
        
        # 如果是学生，更新学生档案（桌宠闲聊不计入）
        # 学号或姓名任一存在即可定位档案（update_student_profile 按学号→姓名→id 查找）
        current_student_name = session.get('student_name', '')
        if current_role == 'student' and (current_student_no or current_student_name) and persona != 'pet':
            update_student_profile(current_student_no or current_student_name, user_message, True)
        
        # 选择模型：剧情 AI (is_scenario=True) 保留 Kimi 质量，其余全部走 Flash 提速省费
        model_choice = MODEL_KIMI if (is_scenario and not persona) else MODEL_FLASH

        if stream:
            # 流式输出 - 记录所有对话到日志
            return Response(
                stream_generator(headers, messages, temperature, max_tokens, user_message,
                                 model_name=model_choice),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache, no-transform',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            # 非流式输出
            payload = {
                "model": model_choice,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
                "enable_thinking": False  # 关闭长思考链
            }
            
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            
            print(f"API请求状态码: {response.status_code}")
            print(f"API请求响应: {response.text[:500]}")
            
            if response.status_code == 200:
                result = response.json()
                if "choices" in result and result["choices"]:
                    answer = result["choices"][0]["message"]["content"].strip()
                    answer = re.sub(r'\n{3,}', '\n\n', answer)
                    
                    # 记录搜索日志（如果需要）
                    if needs_search:
                        is_kb_content = any(kw in answer for kw in knowledge_content[:200].split()) if knowledge_content else False
                        add_search_log(user_message, answer, is_kb_content)
                    
                    return jsonify({'response': answer})
                else:
                    return jsonify({'error': 'API返回格式错误'}), 500
            else:
                return jsonify({'error': f'API请求失败: {response.status_code} - {response.text}'}), 500
        
    except requests.exceptions.Timeout:
        return jsonify({'error': '请求超时，请稍后重试'}), 500
    except Exception as e:
        return jsonify({'error': f'请求出错: {str(e)}'}), 500


# ====================== 会话历史（侧边栏） ======================
CONVERSATIONS_FILE = 'conversations.json'
MAX_CONVS_PER_USER = 50        # 每用户最多保留会话数
MAX_MSGS_PER_CONV = 200        # 每会话最多消息数
MAX_CONTENT_LEN = 8000         # 单条消息文本上限

def load_conversations():
    try:
        with open(CONVERSATIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_conversations(data):
    atomic_save_json(CONVERSATIONS_FILE, data)

def get_user_key():
    role = session.get('role', 'student')
    no = session.get('student_no', '')
    name = session.get('student_name', '')
    return f"{role}:{no or name or 'anon'}"

def get_user_convs(data):
    return data.setdefault(get_user_key(), {}).setdefault('convs', [])

def conv_summary(c):
    preview = ''
    for m in reversed(c['messages']):
        if m.get('content'):
            preview = m['content'][:60]
            break
    return {
        'id': c['id'],
        'title': c['title'],
        'updated_at': c['updated_at'],
        'message_count': len(c['messages']),
        'preview': preview
    }

def find_conv(convs, cid):
    for c in convs:
        if c['id'] == cid:
            return c
    return None

@app.route('/api/conversations', methods=['GET'])
def api_list_conversations():
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    convs = get_user_convs(load_conversations())
    convs.sort(key=lambda c: c['updated_at'], reverse=True)
    return jsonify({'conversations': [conv_summary(c) for c in convs]})

@app.route('/api/conversations', methods=['POST'])
def api_create_conversation():
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    req = request.get_json(silent=True) or {}
    now = datetime.now().isoformat(timespec='seconds')
    conv = {
        'id': uuid.uuid4().hex[:12],
        'title': (req.get('title') or '新的对话').strip()[:30] or '新的对话',
        'created_at': now,
        'updated_at': now,
        'messages': []
    }
    data = load_conversations()
    convs = get_user_convs(data)
    convs.insert(0, conv)
    # 超出上限时删掉最旧的会话
    if len(convs) > MAX_CONVS_PER_USER:
        convs.sort(key=lambda c: c['updated_at'], reverse=True)
        del convs[MAX_CONVS_PER_USER:]
    save_conversations(data)
    return jsonify(conv_summary(conv))

@app.route('/api/conversations/<cid>', methods=['GET'])
def api_get_conversation(cid):
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    conv = find_conv(get_user_convs(load_conversations()), cid)
    if not conv:
        return jsonify({'error': '会话不存在'}), 404
    out = conv_summary(conv)
    out['messages'] = conv['messages']
    return jsonify(out)

@app.route('/api/conversations/<cid>', methods=['PATCH'])
def api_rename_conversation(cid):
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    req = request.get_json(silent=True) or {}
    title = (req.get('title') or '').strip()[:30]
    if not title:
        return jsonify({'error': '标题不能为空'}), 400
    data = load_conversations()
    conv = find_conv(get_user_convs(data), cid)
    if not conv:
        return jsonify({'error': '会话不存在'}), 404
    conv['title'] = title
    save_conversations(data)
    return jsonify(conv_summary(conv))

@app.route('/api/conversations/<cid>', methods=['DELETE'])
def api_delete_conversation(cid):
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    data = load_conversations()
    convs = get_user_convs(data)
    conv = find_conv(convs, cid)
    if not conv:
        return jsonify({'error': '会话不存在'}), 404
    convs.remove(conv)
    save_conversations(data)
    return jsonify({'ok': True})

@app.route('/api/conversations/<cid>/messages', methods=['POST'])
def api_add_conv_message(cid):
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    req = request.get_json(silent=True) or {}
    content = str(req.get('content', ''))[:MAX_CONTENT_LEN]
    data = load_conversations()
    conv = find_conv(get_user_convs(data), cid)
    if not conv:
        return jsonify({'error': '会话不存在'}), 404
    conv['messages'].append({
        'content': content,
        'isUser': bool(req.get('isUser')),
        'image': req.get('image'),       # data URL 或 null
        'timestamp': int(time.time() * 1000)
    })
    if len(conv['messages']) > MAX_MSGS_PER_CONV:
        del conv['messages'][:len(conv['messages']) - MAX_MSGS_PER_CONV]
    conv['updated_at'] = datetime.now().isoformat(timespec='seconds')
    save_conversations(data)
    return jsonify({'ok': True, 'summary': conv_summary(conv)})


def stream_generator(headers, messages, temperature, max_tokens, search_query=None, model_name=None):
    payload = {
        "model": model_name or MODEL_FLASH,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "enable_thinking": False  # 关闭长思考链：否则模型先思考30秒+才输出，前端表现为卡住
    }
    
    full_response = ""
    try:
        response = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
        
        print(f"流式API请求状态码: {response.status_code}")
        
        if response.status_code != 200:
            print(f"流式API请求失败: {response.text[:500]}")
            yield f"data: {json.dumps({'error': f'API请求失败: {response.status_code}'})}\n\n"
            return
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        if search_query and full_response:
                            is_kb_content = False
                            if knowledge_content:
                                kb_keywords = knowledge_content[:1000].split()
                                response_words = full_response[:500].split()
                                match_count = sum(1 for kw in kb_keywords if kw in response_words)
                                is_kb_content = match_count > 2
                            add_search_log(search_query, full_response, is_kb_content)
                        
                        ppt_recommendation = generate_ppt_recommendation(search_query)
                        if ppt_recommendation:
                            yield f"data: {json.dumps({'content': ppt_recommendation})}\n\n"
                        
                        kg_recommendation = generate_knowledge_recommendation(search_query)
                        if kg_recommendation:
                            yield f"data: {json.dumps({'content': kg_recommendation})}\n\n"
                        
                        break
                    try:
                        json_data = json.loads(data)
                        if 'choices' in json_data and len(json_data['choices']) > 0:
                            delta = json_data['choices'][0].get('delta', {})
                            chunk = delta.get('content', '')
                            if chunk:
                                full_response += chunk
                                yield f"data: {json.dumps({'content': chunk})}\n\n"
                    except:
                        pass
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


def generate_ppt_recommendation(query: str) -> str:
    """根据用户查询生成PPT推荐信息"""
    if not query:
        return ""
    
    ppt_list = search_ppt_by_keyword(query)
    if not ppt_list:
        return ""
    
    recommendation = "\n\n📚 **相关学习资源**\n\n"
    for i, ppt in enumerate(ppt_list[:3], 1):
        download_url = f"/uploads/{ppt['download_name']}"
        recommendation += f"**{i}. [{ppt['filename']}]({download_url})**\n"
        if ppt.get('chapters'):
            chapter_titles = [c['title'] for c in ppt['chapters'][:3] if c['title']]
            if chapter_titles:
                recommendation += f"   - 章节：{', '.join(chapter_titles)}\n"
        if ppt.get('knowledge_points'):
            recommendation += f"   - 知识点：{', '.join(ppt['knowledge_points'][:3])}\n"
    
    return recommendation


def generate_knowledge_recommendation(query: str) -> str:
    """根据用户查询生成知识图谱推荐信息"""
    if not query:
        return ""
    
    kg_results = search_knowledge_graph(query)
    if not kg_results:
        return ""
    
    recommendation = "\n\n🔗 **相关知识点推荐**\n\n"
    
    for concept, info in kg_results.items():
        recommendation += f"**📍 {concept}**\n"
        
        if info.get('prerequisites'):
            recommendation += f"   ── 前置知识：{', '.join(info['prerequisites'])}\n"
        
        if info.get('related'):
            recommendation += f"   ── 相关知识：{', '.join(info['related'])}\n"
        
        if info.get('applications'):
            recommendation += f"   ── 应用场景：{', '.join(info['applications'])}\n"
    
    related_knowledge = {}
    for concept, info in kg_results.items():
        for related in info.get('related', []):
            if related not in kg_results and related in KNOWLEDGE_GRAPH:
                related_knowledge[related] = KNOWLEDGE_GRAPH[related]
    
    if related_knowledge:
        recommendation += "\n📚 **延伸学习**\n\n"
        for concept, info in list(related_knowledge.items())[:3]:
            recommendation += f"**📖 {concept}**（难度: {'⭐' * info.get('difficulty', 0)}）\n"
    
    return recommendation


# ====================== 剧情演绎相关路由 ======================
@app.route('/scenarios', methods=['GET'])
def get_scenarios():
    """获取所有剧情场景"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    return jsonify({'scenarios': SCENARIOS})


@app.route('/scenario/<int:scenario_id>', methods=['GET'])
def get_scenario(scenario_id):
    """获取单个剧情场景详情"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    scenario = next((s for s in SCENARIOS if s['id'] == scenario_id), None)
    if scenario:
        return jsonify({'scenario': scenario})
    else:
        return jsonify({'error': '场景不存在'}), 404


@app.route('/start-scenario', methods=['POST'])
def start_scenario():
    """开始剧情演绎"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.get_json()
    scenario_id = data.get('scenario_id')
    
    scenario = next((s for s in SCENARIOS if s['id'] == scenario_id), None)
    if not scenario:
        return jsonify({'error': '场景不存在'}), 404
    
    # 初始化会话状态
    session['current_scenario'] = scenario_id
    session['scenario_progress'] = 0
    session['scenario_history'] = []
    
    return jsonify({
        'success': True,
        'scenario': scenario,
        'message': f"已开始剧情：{scenario['title']}"
    })


@app.route('/scenario-progress', methods=['GET'])
def get_scenario_progress():
    """获取剧情演绎进度"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    return jsonify({
        'current_scenario': session.get('current_scenario'),
        'progress': session.get('scenario_progress', 0),
        'history': session.get('scenario_history', [])
    })


# ====================== 搜索日志相关路由 ======================
@app.route('/search-logs', methods=['GET'])
def get_search_logs():
    """获取所有搜索日志"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    logs = load_search_logs()
    return jsonify({'logs': logs})


@app.route('/search-logs/analysis', methods=['GET'])
def analyze_search_logs():
    """分析学生普遍问题"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    logs = load_search_logs()
    
    # 定义关键词分类
    categories = {
        '信号与系统': ['傅里叶', '拉普拉斯', '卷积', '时域', '频域', 'Z变换', '差分方程', '系统响应', '滤波器', '响应'],
        '通信原理': ['香农', '信道容量', '编码', '译码', '误码率', '信噪比', '信道', '带宽', '调制', '解调'],
        '数字信号处理': ['采样', '量化', '编码', 'FFT', '频谱', '噪声', '失真', 'DFT', '滤波器'],
        '网络协议': ['TCP', 'IP', 'UDP', 'HTTP', '协议', '路由', '交换机', '路由器', 'Socket'],
        '射频工程': ['射频', '天线', '功率', '增益', '衰减', '阻抗', '匹配', '电磁波', '驻波'],
        '5G技术': ['5G', 'NR', '毫米波', 'MIMO', '波束赋形', '载波聚合', '边缘计算'],
        'LTE/4G': ['LTE', '4G', 'OFDMA', 'SC-FDMA', 'eMBB', 'uRLLC', 'mMTC']
    }
    
    # 统计各类别的问题数量
    category_stats = {}
    for category, keywords in categories.items():
        count = 0
        category_logs = []
        for log in logs:
            query_lower = log['query'].lower()
            content_lower = log['content'].lower()
            if any(kw in query_lower or kw in content_lower for kw in keywords):
                count += 1
                category_logs.append({
                    'query': log['query'],
                    'id': log['id'],
                    'timestamp': log['timestamp']
                })
        category_stats[category] = {
            'count': count,
            'percentage': round(count / len(logs) * 100, 1) if logs else 0,
            'logs': category_logs[:5]
        }
    
    # 统计高频关键词
    word_freq = {}
    stop_words = ['的', '了', '是', '在', '和', '与', '或', '什么', '怎么', '如何', '为什么', '请', '我', '你', '有', '能', '可以', '吗', '呢', '啊', '这', '那', '一个', '一些', '这个', '那个', '这些', '那些', '因为', '所以', '但是', '可是', '然而', '不过', '虽然', '如果', '要是', '只要', '只有', '除非', '无论', '不管', '不仅', '而且', '并且', '以及', '等等', '例如', '比如', '就是', '还是', '或者', '还是', '已经', '正在', '曾经', '将要', '能够', '应该', '必须', '需要', '可能', '应该']
    
    for log in logs:
        query = log['query']
        # 使用正则表达式提取中文词（连续的中文字符）
        import re
        chinese_words = re.findall(r'[\u4e00-\u9fff]+', query)
        
        for word in chinese_words:
            # 跳过单个字符和停用词
            if len(word) >= 2 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1
                
                # 也提取双字词
                if len(word) > 2:
                    for i in range(len(word) - 1):
                        bi_gram = word[i:i+2]
                        if bi_gram not in stop_words:
                            word_freq[bi_gram] = word_freq.get(bi_gram, 0) + 1
    
    # 获取TOP10关键词
    top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # 找出最常见的问题类型
    common_questions = []
    question_patterns = [
        (r'什么是(.+)', '概念理解'),
        (r'(.+?)的原理', '原理分析'),
        (r'如何(.+)', '方法步骤'),
        (r'(.+?)和(.+?)的区别', '对比分析'),
        (r'(.+?)怎么处理', '问题解决'),
        (r'(.+?)怎么配置', '配置方法'),
    ]
    
    for pattern, qtype in question_patterns:
        count = 0
        examples = []
        for log in logs:
            import re
            if re.search(pattern, log['query']):
                count += 1
                if len(examples) < 3:
                    examples.append(log['query'])
        if count > 0:
            common_questions.append({
                'type': qtype,
                'count': count,
                'examples': examples
            })
    
    # 按数量排序
    common_questions.sort(key=lambda x: x['count'], reverse=True)
    
    return jsonify({
        'total_logs': len(logs),
        'category_stats': category_stats,
        'top_keywords': [{'keyword': k, 'count': c} for k, c in top_keywords],
        'common_questions': common_questions
    })


@app.route('/search-logs/category/<string:category>', methods=['GET'])
def get_search_logs_by_category(category):
    """按分类获取搜索日志"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    logs = load_search_logs()
    
    # 定义关键词分类
    categories = {
        '信号与系统': ['傅里叶', '拉普拉斯', '卷积', '时域', '频域', 'Z变换', '差分方程', '系统响应', '滤波器', '响应'],
        '通信原理': ['香农', '信道容量', '编码', '译码', '误码率', '信噪比', '信道', '带宽', '调制', '解调'],
        '数字信号处理': ['采样', '量化', '编码', 'FFT', '频谱', '噪声', '失真', 'DFT', '滤波器'],
        '网络协议': ['TCP', 'IP', 'UDP', 'HTTP', '协议', '路由', '交换机', '路由器', 'Socket'],
        '射频工程': ['射频', '天线', '功率', '增益', '衰减', '阻抗', '匹配', '电磁波', '驻波'],
        '5G技术': ['5G', 'NR', '毫米波', 'MIMO', '波束赋形', '载波聚合', '边缘计算'],
        'LTE/4G': ['LTE', '4G', 'OFDMA', 'SC-FDMA', 'eMBB', 'uRLLC', 'mMTC']
    }
    
    keywords = categories.get(category, [])
    filtered_logs = []
    
    for log in logs:
        query_lower = log['query'].lower()
        content_lower = log['content'].lower()
        if any(kw.lower() in query_lower or kw.lower() in content_lower for kw in keywords):
            filtered_logs.append(log)
    
    return jsonify({'logs': filtered_logs, 'category': category})


@app.route('/search-logs/<int:log_id>', methods=['GET'])
def get_search_log(log_id):
    """获取单个搜索日志详情"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    logs = load_search_logs()
    log = next((l for l in logs if l['id'] == log_id), None)
    
    if log:
        return jsonify({'log': log})
    else:
        return jsonify({'error': '日志不存在'}), 404


@app.route('/search-logs/<int:log_id>/review', methods=['PUT'])
def review_search_log(log_id):
    """审核搜索日志（审核通过且非知识库内容自动加入知识库）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.get_json()
    reviewed = data.get('reviewed', False)
    note = data.get('note', '')
    
    logs = load_search_logs()
    log = next((l for l in logs if l['id'] == log_id), None)
    
    if log:
        log['reviewed'] = reviewed
        log['note'] = note
        save_search_logs(logs)
        
        # 如果审核通过，且不是来自知识库的内容，自动加入知识库
        if reviewed and not log.get('is_from_kb', False):
            try:
                knowledge_entry = f"\n\n{'='*50}\n【新增知识】{log['query']}\n{'='*50}\n{log['content']}\n\n"
                
                with open(KNOWLEDGE_FILE, "a", encoding="utf-8") as f:
                    f.write(knowledge_entry)
                
                # 重新加载知识库
                global knowledge_content, SYSTEM_PROMPT_FAST, SYSTEM_PROMPT_DEEP
                knowledge_content = load_knowledge()
                
                # 更新提示词
                SYSTEM_PROMPT_FAST = f"""
你是灵智尚人，通信工程专家助手，请结合知识库快速、简洁地回答问题。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 优先使用知识库内容回答
2. 如果知识库没有相关内容，可以用自己的知识回答，但要注明
3. 回答要简洁明了，控制在150字以内
"""
                
                SYSTEM_PROMPT_DEEP = f"""
你是灵智尚人，通信工程专家助手，请结合知识库进行深度分析和详细解答。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 必须结合知识库内容进行深度分析
2. 分析问题的本质和原理
3. 提供具体的解决方法和建议
4. 回答要详细、有深度，控制在500字以内
"""
                
                log['added_to_kb'] = True
                save_search_logs(logs)
                
                return jsonify({'success': True, 'log': log, 'added_to_kb': True, 'message': '已审核并自动加入知识库'})
            except Exception as e:
                print(f"自动加入知识库失败: {e}")
                return jsonify({'success': True, 'log': log, 'added_to_kb': False, 'message': '审核成功，但加入知识库失败'})
        
        return jsonify({'success': True, 'log': log})
    else:
        return jsonify({'error': '日志不存在'}), 404


@app.route('/search-logs/<int:log_id>/add-to-knowledge', methods=['POST'])
def add_to_knowledge(log_id):
    """将搜索日志内容添加到知识库"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    logs = load_search_logs()
    log = next((l for l in logs if l['id'] == log_id), None)
    
    if not log:
        return jsonify({'error': '日志不存在'}), 404
    
    # 添加到知识库
    knowledge_entry = f"\n\n{'='*50}\n【新增知识】{log['query']}\n{'='*50}\n{log['content']}\n\n"
    
    try:
        with open(KNOWLEDGE_FILE, "a", encoding="utf-8") as f:
            f.write(knowledge_entry)
        
        # 重新加载知识库
        global knowledge_content, SYSTEM_PROMPT_FAST, SYSTEM_PROMPT_DEEP
        knowledge_content = load_knowledge()
        
        # 更新提示词
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
        
        return jsonify({'success': True, 'message': '已添加到知识库'})
    except Exception as e:
        return jsonify({'error': f'添加失败: {str(e)}'}), 500


@app.route('/search-logs/<int:log_id>', methods=['DELETE'])
def delete_search_log(log_id):
    """删除搜索日志"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    logs = load_search_logs()
    logs = [l for l in logs if l['id'] != log_id]
    save_search_logs(logs)
    
    return jsonify({'success': True})


@app.route('/search-logs-page')
def search_logs_page():
    """搜索日志查看页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('search_logs.html')


@app.route('/upload-knowledge-page')
def upload_knowledge_page():
    """上传知识库文件页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('upload_knowledge.html')


def process_single_file(file):
    """处理单个文件上传的核心逻辑"""
    result = {
        'filename': file.filename,
        'success': False,
        'error': None,
        'duplicate': False,
        'extracted_length': 0
    }
    
    if not file or file.filename == '':
        result['error'] = '文件名为空'
        return result
    
    if not allowed_file(file.filename):
        result['error'] = '不支持的文件格式'
        return result
    
    try:
        filename = safe_upload_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        
        extracted_text = extract_text_from_document(file_path)
        
        if not extracted_text.strip():
            os.remove(file_path)
            result['error'] = '无法从文件中提取内容'
            return result
        
        if is_content_duplicate(extracted_text):
            os.remove(file_path)
            result['error'] = '内容已存在于知识库中'
            result['duplicate'] = True
            return result
        
        knowledge_entry = f"\n\n{'='*50}\n【文档导入】{filename}\n{'='*50}\n{extracted_text}\n\n"
        
        with open(KNOWLEDGE_FILE, "a", encoding="utf-8") as f:
            f.write(knowledge_entry)
        
        download_name = ""
        chapters = []
        knowledge_points = []
        # 支持服务端转图片在线预览的格式（LibreOffice 均可转 PDF）
        image_preview_exts = {'doc', 'docx', 'ppt', 'pptx'}
        preview_ready = False
        page_count = 0
        preview_dir = ""

        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext == 'pptx':
            ppt_structure = extract_pptx_structure(file_path)
            chapters = ppt_structure['chapters']
            knowledge_points = ppt_structure['knowledge_points']

            download_name = f"lecture_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            download_path = os.path.join(UPLOAD_FOLDER, download_name)
            os.rename(file_path, download_path)

            ppt_metadata = load_ppt_metadata()
            ppt_metadata.append({
                'id': str(uuid.uuid4()),
                'filename': filename,
                'download_name': download_name,
                'chapters': chapters,
                'knowledge_points': knowledge_points,
                'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'uploader': session.get('username') or session.get('student_name') or 'unknown',
                'preview_ready': False,
                'page_count': 0,
                'preview_dir': f"previews/{download_name.rsplit('.', 1)[0]}"
            })
            save_ppt_metadata(ppt_metadata)
            # 后台转图片：学生预览秒开，不阻塞上传响应
            threading.Thread(target=convert_document_to_images, args=(download_name,), daemon=True).start()
        else:
            # doc/docx/ppt/txt 等文档同样保留原件，供教师在上传历史中查看/下载
            download_name = f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            os.rename(file_path, os.path.join(UPLOAD_FOLDER, download_name))
            if ext in image_preview_exts:
                # doc/docx/ppt：后台逐页转图片，前端与PPT共用同一套预览弹窗
                preview_dir = f"previews/{download_name.rsplit('.', 1)[0]}"
                threading.Thread(target=convert_document_to_images, args=(download_name,), daemon=True).start()

        history_entry = {
            'id': str(uuid.uuid4()),
            'filename': filename,
            'download_name': download_name,
            'file_ext': ext,
            'extracted_length': len(extracted_text),
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uploader': session.get('username') or session.get('student_name') or 'unknown',
            'status': 'success',
            'chapters': chapters,
            'knowledge_points': knowledge_points
        }
        if ext in image_preview_exts:
            history_entry.update({
                'preview_ready': preview_ready,
                'page_count': page_count,
                'preview_dir': preview_dir
            })
        history = load_upload_history()
        history.append(history_entry)
        save_upload_history(history)
        
        result['success'] = True
        result['extracted_length'] = len(extracted_text)
        result['chapters'] = chapters
        result['knowledge_points'] = knowledge_points
        return result
        
    except Exception as e:
        result['error'] = str(e)
        return result


def update_system_prompt():
    """更新系统提示词"""
    global knowledge_content, SYSTEM_PROMPT_FAST, SYSTEM_PROMPT_DEEP
    knowledge_content = load_knowledge()
    
    SYSTEM_PROMPT_FAST = f"""
你是灵智尚人，通信工程专家助手，请结合知识库快速、简洁地回答问题。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 优先使用知识库内容回答
2. 如果知识库没有相关内容，可以用自己的知识回答，但要注明
3. 回答要简洁明了，控制在150字以内
"""
    
    SYSTEM_PROMPT_DEEP = f"""
你是灵智尚人，通信工程专家助手，请结合知识库进行深度分析和详细解答。

【知识库】
{knowledge_content if knowledge_content else "（知识库为空）"}

要求：
1. 必须结合知识库内容进行深度分析
2. 分析问题的本质和原理
3. 提供具体的解决方法和建议
4. 回答要详细、有深度，控制在500字以内
"""

    # 知识库内容变化 → 后台重建 RAG 索引（不阻塞上传/审核等调用方）
    if RAG_MODULE_AVAILABLE:
        try:
            rag_retriever.ensure_index(async_mode=True)
        except Exception as e:  # noqa: BLE001
            print(f"[RAG] 索引重建调度失败: {e}")


@app.route('/api/knowledge/upload', methods=['POST'])
def upload_knowledge_file():
    """上传文档到知识库（支持单文件和多文件，支持docx/doc/pptx/ppt/txt）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    role = session.get('role', '')
    if role != 'teacher':
        return jsonify({'error': '只有老师可以上传知识库文件'}), 403
    
    files = request.files.getlist('files')
    if not files:
        files = request.files.getlist('file')
    
    if not files or all(f.filename == '' for f in files):
        return jsonify({'error': '请选择要上传的文件'}), 400
    
    results = []
    success_count = 0
    duplicate_count = 0
    failed_count = 0
    
    for file in files:
        if file.filename:
            result = process_single_file(file)
            results.append(result)
            if result['success']:
                success_count += 1
            elif result['duplicate']:
                duplicate_count += 1
            else:
                failed_count += 1
    
    if success_count > 0:
        update_system_prompt()
        if SECURITY_MODULE_AVAILABLE:
            security.audit(
                'knowledge_upload',
                target='、'.join(r.get('filename', '') for r in results if r.get('success')),
                detail=f"成功 {success_count} 个，重复 {duplicate_count} 个，失败 {failed_count} 个")
    
    if len(results) == 1:
        single = results[0]
        if single['success']:
            return jsonify({
                'success': True,
                'message': f'成功导入文档 "{single["filename"]}"，共 {single["extracted_length"]} 字符',
                'extracted_length': single['extracted_length']
            })
        elif single['duplicate']:
            return jsonify({
                'success': False,
                'error': f'文档 "{single["filename"]}" 的内容已存在于知识库中，无需重复上传',
                'duplicate': True
            }), 400
        else:
            return jsonify({'error': single['error']}), 400
    
    return jsonify({
        'success': success_count > 0,
        'total': len(results),
        'success_count': success_count,
        'duplicate_count': duplicate_count,
        'failed_count': failed_count,
        'results': results,
        'message': f'上传完成：成功 {success_count} 个，重复 {duplicate_count} 个，失败 {failed_count} 个'
    })


@app.route('/api/knowledge/count', methods=['GET'])
def get_knowledge_count():
    """获取知识库内容统计"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({
            'success': True,
            'char_count': len(content),
            'line_count': content.count('\n'),
            'kb_available': DOCX_AVAILABLE and PPTX_AVAILABLE
        })
    return jsonify({
        'success': True,
        'char_count': 0,
        'line_count': 0,
        'kb_available': DOCX_AVAILABLE and PPTX_AVAILABLE
    })


@app.route('/api/knowledge/history', methods=['GET'])
def get_upload_history():
    """获取上传历史记录"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    history = load_upload_history()
    history.reverse()

    # 合并文件查看信息：
    # - 新记录自带 download_name/file_ext（doc/docx/txt/pptx 均保留原件）
    # - 旧记录没有这些字段，按文件名从 PPT 元数据补全（向后兼容）
    ppt_by_name = {p['filename']: p for p in load_ppt_metadata()}
    for h in history:
        ext = (h.get('file_ext') or h.get('filename', '').rsplit('.', 1)[-1]).lower()
        p = ppt_by_name.get(h.get('filename'))
        if not h.get('download_name') and p:
            h['download_name'] = p.get('download_name', '')
        h['file_ext'] = ext
        # PPT 的预览状态存于 ppt_metadata；Word 等文档自带于历史条目，自带优先
        if p and 'preview_ready' not in h:
            h['preview_ready'] = p.get('preview_ready', False)
            h['page_count'] = p.get('page_count', 0)
            h['preview_dir'] = p.get('preview_dir', '')

    return jsonify({
        'success': True,
        'history': history,
        'total_count': len(history)
    })


def remove_knowledge_sections(filename: str):
    """从knowledge.txt移除指定文档的导入段落"""
    try:
        sep = '=' * 50
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            parts = content.split(sep)
            out = []
            skip_next = False
            for part in parts:
                if skip_next:
                    skip_next = False
                    continue
                if filename in part and '【文档导入】' in part:
                    skip_next = True
                    continue
                out.append(part)
            with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
                f.write(sep.join(out))
    except Exception as e:
        print(f"清理知识库段落失败: {e}")


@app.route('/api/knowledge/upload/<entry_id>', methods=['DELETE'])
def delete_knowledge_upload(entry_id):
    """删除上传记录：同时清理知识库段落、PPT文件、预览图和元数据"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师可以删除上传的文件'}), 403

    history = load_upload_history()
    entry = next((h for h in history if h.get('id') == entry_id), None)
    if not entry:
        return jsonify({'error': '记录不存在'}), 404

    filename = entry.get('filename', '')

    # 1. 移除知识库中的导入段落
    remove_knowledge_sections(filename)

    import shutil

    # 2. 移除历史条目自带的原文件（doc/docx/txt 等非 PPT 文档）
    #    单个文件清理失败（如 Windows 句柄暂未释放）不应阻断知识库段落和历史记录的清理
    def safe_remove_file(path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"上传文件删除失败 {path}: {e}")

    own_dn = entry.get('download_name', '')
    if own_dn:
        own_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, own_dn))
        if own_path.startswith(os.path.abspath(UPLOAD_FOLDER)):
            safe_remove_file(own_path)
    # 历史条目自带的预览图目录（doc/docx/ppt 等通用文档）
    own_pd = entry.get('preview_dir', '')
    if own_pd.startswith('previews/'):
        own_pdir = os.path.abspath(os.path.join(UPLOAD_FOLDER, own_pd))
        if own_pdir.startswith(os.path.abspath(os.path.join(UPLOAD_FOLDER, 'previews'))):
            shutil.rmtree(own_pdir, ignore_errors=True)

    # 3. 移除PPT文件、预览图目录和元数据
    meta = load_ppt_metadata()
    removed = [m for m in meta if m.get('filename') == filename]
    save_ppt_metadata([m for m in meta if m.get('filename') != filename])
    for m in removed:
        fpath = os.path.abspath(os.path.join(UPLOAD_FOLDER, m.get('download_name', '')))
        if fpath.startswith(os.path.abspath(UPLOAD_FOLDER)):
            safe_remove_file(fpath)
        pd_rel = m.get('preview_dir', '')
        if pd_rel.startswith('previews/'):
            pdir = os.path.abspath(os.path.join(UPLOAD_FOLDER, pd_rel))
            if pdir.startswith(os.path.abspath(os.path.join(UPLOAD_FOLDER, 'previews'))):
                shutil.rmtree(pdir, ignore_errors=True)

    # 4. 移除上传历史条目
    save_upload_history([h for h in history if h.get('id') != entry_id])

    # 5. 刷新系统提示词中的知识库内容
    update_system_prompt()

    if SECURITY_MODULE_AVAILABLE:
        security.audit('knowledge_delete', target=filename,
                       detail=f'删除上传记录 {entry_id}，同步清理知识库段落与原件')

    return jsonify({'success': True, 'message': f'已删除 "{filename}" 及其知识库内容'})


# ====================== 阶段一：核心引擎升级 API ======================

@app.route('/api/wrong-questions', methods=['GET'])
def get_wrong_questions():
    """获取错题本"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    student_name = request.args.get('student_name', session.get('student_name', ''))
    # 学生只能查看自己的数据；老师可通过参数查看任意学生
    if session.get('role') != 'teacher':
        student_name = session.get('student_name', '')
    questions = load_wrong_questions()
    
    if student_name:
        questions = [q for q in questions if q['student_name'] == student_name]
    
    # 按最后错误时间倒序
    questions.sort(key=lambda x: x.get('last_wrong_time', ''), reverse=True)
    
    return jsonify({
        'success': True,
        'questions': questions,
        'total': len(questions),
        'unmastered': len([q for q in questions if not q.get('mastered', False)])
    })


@app.route('/api/wrong-questions', methods=['POST'])
def add_wrong_question():
    """添加错题"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.json
    student_name = data.get('student_name', session.get('student_name', ''))
    question = data.get('question', '')
    category = data.get('category', '通用')
    knowledge_point = data.get('knowledge_point', '')
    student_answer = data.get('student_answer', '')
    correct_answer = data.get('correct_answer', '')
    
    if not question:
        return jsonify({'error': '问题内容不能为空'}), 400
    
    record_wrong_question(student_name, question, category, knowledge_point, student_answer, correct_answer)
    record_learning_activity(student_name, 'wrong_question', knowledge_point)
    
    return jsonify({'success': True, 'message': '错题已记录'})


@app.route('/api/wrong-questions/<question_id>/master', methods=['POST'])
def mark_mastered(question_id):
    """标记错题为已掌握"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    questions = load_wrong_questions()
    for q in questions:
        if q['id'] == question_id:
            q['mastered'] = True
            q['mastered_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            break
    save_wrong_questions(questions)
    
    return jsonify({'success': True, 'message': '已标记为掌握'})


@app.route('/api/review/recommend', methods=['GET'])
def recommend_review():
    """推荐复习内容"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    student_name = request.args.get('student_name', session.get('student_name', ''))
    # 学生只能查看自己的数据；老师可通过参数查看任意学生
    if session.get('role') != 'teacher':
        student_name = session.get('student_name', '')
    limit = int(request.args.get('limit', 5))
    
    recommendations = get_recommended_review(student_name, limit)
    
    return jsonify({
        'success': True,
        'recommendations': recommendations,
        'count': len(recommendations)
    })


# ====================== 互动式练习 API ======================
@app.route('/api/exercises/knowledge-points', methods=['GET'])
def get_exercise_knowledge_points():
    """获取有练习题的知识点列表"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    points = get_all_knowledge_points_with_exercises()
    result = []
    
    for point in points:
        kg_info = KNOWLEDGE_GRAPH.get(point, {})
        all_bank = get_all_exercises_with_custom()
        exercise_count = len(all_bank.get(point, []))
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


@app.route('/api/exercises/generate', methods=['POST'])
def generate_exercises():
    """生成练习题"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.json
    knowledge_point = data.get('knowledge_point', '')
    count = int(data.get('count', 3))
    
    if not knowledge_point:
        return jsonify({'error': '请指定知识点'}), 400
    
    exercises = get_exercises_by_knowledge(knowledge_point, count)
    
    if not exercises:
        return jsonify({
            'success': False,
            'error': f'知识点 "{knowledge_point}" 暂无练习题'
        })
    
    return jsonify({
        'success': True,
        'knowledge_point': knowledge_point,
        'exercises': exercises,
        'count': len(exercises)
    })


@app.route('/api/exercises/submit', methods=['POST'])
def submit_exercise_answer():
    """提交练习答案并批改"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.json
    question_id = data.get('question_id', '')
    student_answer = data.get('student_answer', '')
    
    if not question_id:
        return jsonify({'error': '请指定题目ID'}), 400
    
    correct_answer = None
    analysis = None
    question_text = None
    knowledge_point = None
    ex = None
    
    # 先在内置题库中查找
    for kp, exercises in EXERCISE_BANK.items():
        for e in exercises:
            if e['id'] == question_id:
                correct_answer = e['answer']
                analysis = e['analysis']
                question_text = e['question']
                knowledge_point = kp
                ex = e
                break
        if correct_answer:
            break
    
    # 再在自定义题库中查找
    if not correct_answer:
        custom = load_custom_exercises()
        for kp, exercises in custom.items():
            for e in exercises:
                if e['id'] == question_id:
                    correct_answer = e['answer']
                    analysis = e['analysis']
                    question_text = e['question']
                    knowledge_point = kp
                    ex = e
                    break
            if correct_answer:
                break
    
    if not correct_answer:
        return jsonify({'error': '题目不存在'}), 404
    
    is_correct = False
    if ex['type'] == 'choice':
        is_correct = student_answer.strip().upper() == correct_answer.strip().upper()
    elif ex['type'] == 'fill':
        is_correct = student_answer.strip().lower() == correct_answer.strip().lower()
    else:
        is_correct = len(student_answer.strip()) >= len(correct_answer) * 0.6
    
    student_name = session.get('student_name', '')
    
    if not is_correct and student_name:
        record_wrong_question(
            student_name=student_name,
            question=question_text,
            category='练习题',
            knowledge_point=knowledge_point,
            student_answer=student_answer,
            correct_answer=correct_answer
        )
    
    return jsonify({
        'success': True,
        'is_correct': is_correct,
        'correct_answer': correct_answer,
        'analysis': analysis,
        'knowledge_point': knowledge_point
    })


# ====================== 教师管理练习题 ======================
CUSTOM_EXERCISE_FILE = "data/custom_exercises.json"


def load_custom_exercises():
    """加载教师自定义练习题"""
    try:
        if os.path.exists(CUSTOM_EXERCISE_FILE):
            with open(CUSTOM_EXERCISE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"自定义练习题加载失败: {e}")
        return {}


def save_custom_exercises(exercises):
    """保存教师自定义练习题"""
    try:
        os.makedirs(os.path.dirname(CUSTOM_EXERCISE_FILE), exist_ok=True)
        atomic_save_json(CUSTOM_EXERCISE_FILE, exercises)
    except Exception as e:
        print(f"自定义练习题保存失败: {e}")


def get_all_exercises_with_custom():
    """合并内置题库和自定义题库"""
    custom = load_custom_exercises()
    # 深拷贝内置题库
    merged = {}
    for kp, exercises in EXERCISE_BANK.items():
        merged[kp] = list(exercises)
    # 合并自定义题库
    for kp, exercises in custom.items():
        if kp in merged:
            merged[kp].extend(exercises)
        else:
            merged[kp] = list(exercises)
    return merged


@app.route('/api/teacher/exercises', methods=['GET'])
def api_teacher_list_exercises():
    """教师查看所有练习题（含自定义）"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    custom = load_custom_exercises()
    result = []
    # 内置题库
    for kp, exercises in EXERCISE_BANK.items():
        for ex in exercises:
            result.append({**ex, 'knowledge_point': kp, 'source': 'builtin'})
    # 自定义题库
    for kp, exercises in custom.items():
        for ex in exercises:
            result.append({**ex, 'knowledge_point': kp, 'source': 'custom'})

    return jsonify({
        'success': True,
        'exercises': result,
        'total': len(result),
        'builtin_count': sum(len(v) for v in EXERCISE_BANK.values()),
        'custom_count': sum(len(v) for v in custom.values())
    })


@app.route('/api/teacher/exercises/add', methods=['POST'])
def api_teacher_add_exercise():
    """教师手动添加练习题"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    data = request.get_json()
    knowledge_point = data.get('knowledge_point', '').strip()
    question = data.get('question', '').strip()
    q_type = data.get('type', 'choice')
    difficulty = int(data.get('difficulty', 2))
    options = data.get('options', [])
    answer = data.get('answer', '').strip()
    analysis = data.get('analysis', '').strip()

    if not knowledge_point or not question or not answer:
        return jsonify({'error': '知识点、题目和答案不能为空'}), 400

    if q_type == 'choice' and (not options or len(options) < 2):
        return jsonify({'error': '选择题至少需要2个选项'}), 400

    custom = load_custom_exercises()
    if knowledge_point not in custom:
        custom[knowledge_point] = []

    # 生成唯一ID
    import uuid
    ex_id = f"custom_{uuid.uuid4().hex[:8]}"

    new_exercise = {
        'id': ex_id,
        'type': q_type,
        'difficulty': difficulty,
        'question': question,
        'answer': answer,
        'analysis': analysis or '教师添加的练习题，暂无解析。',
        'created_by': session.get('student_name', 'teacher'),
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if q_type == 'choice':
        new_exercise['options'] = options

    custom[knowledge_point].append(new_exercise)
    save_custom_exercises(custom)

    return jsonify({
        'success': True,
        'message': f'题目已添加到知识点「{knowledge_point}」',
        'exercise': new_exercise
    })


@app.route('/api/teacher/exercises/<exercise_id>', methods=['DELETE'])
def api_teacher_delete_exercise(exercise_id):
    """教师删除自定义练习题"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    custom = load_custom_exercises()
    deleted = False
    kp_name = ''
    for kp, exercises in custom.items():
        before = len(exercises)
        custom[kp] = [e for e in exercises if e['id'] != exercise_id]
        if len(custom[kp]) < before:
            deleted = True
            kp_name = kp
            break

    if not deleted:
        return jsonify({'error': '题目不存在或为内置题库不可删除'}), 404

    # 清理空知识点
    if not custom[kp_name]:
        del custom[kp_name]

    save_custom_exercises(custom)
    return jsonify({'success': True, 'message': '题目已删除'})


@app.route('/api/teacher/exercises/batch-add', methods=['POST'])
def api_teacher_batch_add_exercises():
    """教师批量添加练习题"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    data = request.get_json()
    knowledge_point = data.get('knowledge_point', '').strip()
    questions = data.get('questions', [])

    if not knowledge_point or not questions:
        return jsonify({'error': '知识点和题目列表不能为空'}), 400

    custom = load_custom_exercises()
    if knowledge_point not in custom:
        custom[knowledge_point] = []

    import uuid
    added = 0
    for q in questions:
        if not q.get('question') or not q.get('answer'):
            continue
        ex_id = f"custom_{uuid.uuid4().hex[:8]}"
        new_ex = {
            'id': ex_id,
            'type': q.get('type', 'choice'),
            'difficulty': int(q.get('difficulty', 2)),
            'question': q['question'],
            'answer': q['answer'],
            'analysis': q.get('analysis', '教师批量添加的练习题。'),
            'created_by': session.get('student_name', 'teacher'),
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if new_ex['type'] == 'choice':
            new_ex['options'] = q.get('options', [])
        custom[knowledge_point].append(new_ex)
        added += 1

    save_custom_exercises(custom)
    return jsonify({
        'success': True,
        'message': f'成功添加 {added} 道题目到知识点「{knowledge_point}」',
        'added_count': added
    })


@app.route('/api/teacher/exercises/import', methods=['POST'])
def api_teacher_import_exercises():
    """教师上传JSON文件批量导入练习题"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': '请提供有效的JSON数据'}), 400

    import uuid
    custom = load_custom_exercises()
    total_added = 0
    errors = []

    # 支持两种格式：
    # 格式A: {"知识点名": [题目数组, ...], ...}
    # 格式B: {"exercises": [{"knowledge_point":"xxx","question":"xxx",...}, ...]}
    if isinstance(data, dict) and 'exercises' in data and isinstance(data['exercises'], list):
        # 格式B：扁平数组
        for idx, q in enumerate(data['exercises']):
            try:
                kp = (q.get('knowledge_point') or q.get('kp') or '未分类').strip()
                if not kp:
                    kp = '未分类'
                result = _import_single_exercise(custom, kp, q)
                if result:
                    errors.append(result)
                else:
                    total_added += 1
            except Exception as e:
                errors.append(f'第{idx+1}条: {str(e)}')
    else:
        # 格式A：按知识点分组
        for kp, exercises in data.items():
            if not isinstance(exercises, list):
                continue
            for idx, q in enumerate(exercises):
                try:
                    result = _import_single_exercise(custom, kp.strip(), q)
                    if result:
                        errors.append(f'[{kp}]第{idx+1}条: {result}')
                    else:
                        total_added += 1
                except Exception as e:
                    errors.append(f'[{kp}]第{idx+1}条: {str(e)}')

    save_custom_exercises(custom)
    return jsonify({
        'success': True,
        'added_count': total_added,
        'error_count': len(errors),
        'errors': errors[:20]  # 最多返回20条错误
    })


@app.route('/api/teacher/exercises/template', methods=['GET'])
def api_teacher_exercises_template():
    """下载导入模板（JSON格式示例）"""
    template = {
        "格式A-按知识点分组": {
            "傅里叶变换": [
                {
                    "question": "傅里叶变换的核心思想是将信号从时域转换到哪个域？",
                    "type": "choice",
                    "options": ["频率域", "空间域", "能量域", "相位域"],
                    "answer": "A",
                    "difficulty": 2,
                    "analysis": "傅里叶变换将信号分解为不同频率的正弦波叠加，实现时域到频域的转换。"
                },
                {
                    "question": "拉普拉斯变换是傅里叶变换的推广，引入了____因子。",
                    "type": "fill",
                    "answer": "衰减",
                    "difficulty": 1,
                    "analysis": "拉普拉斯变换引入衰减因子，使更多信号能够进行变换。"
                }
            ],
            "5G NR": [
                {
                    "question": "5G NR的子载波间隔支持以下哪些？",
                    "type": "choice",
                    "options": ["15kHz", "30kHz", "60kHz", "以上都支持"],
                    "answer": "D",
                    "difficulty": 2,
                    "analysis": "5G NR支持15/30/60/120/240kHz等多种子载波间隔。"
                }
            ]
        },
        "格式B-扁平数组": [
            {
                "knowledge_point": "天线原理",
                "question": "天线的方向性系数定义是什么？",
                "type": "choice",
                "options": ["最大辐射方向功率与平均功率之比", "效率", "增益", "带宽"],
                "answer": "A",
                "difficulty": 2,
                "analysis": "方向性系数是最大辐射方向的辐射强度与平均辐射强度之比。"
            }
        ],
        "字段说明": {
            "question": "题目内容（必填）",
            "type": "题型：choice=选择题, fill=填空题, short=简答题（默认choice）",
            "options": "选项数组（选择题必填，如['选项A','选项B']）",
            "answer": "正确答案（选择题填 A/B/C/D；填空题填答案文本）",
            "difficulty": "难度1-3（可选，默认2）",
            "analysis": "答案解析（可选）"
        }
    }
    return jsonify(template)


def _import_single_exercise(custom, knowledge_point, q):
    """导入单道练习题，返回错误字符串（成功返回None）"""
    import uuid as _uuid
    question_text = q.get('question', '').strip()
    if not question_text:
        return '题目内容为空'

    q_type = q.get('type', 'choice')
    if q_type not in ('choice', 'fill', 'short'):
        q_type = 'choice'

    answer = q.get('answer', '').strip()
    if not answer:
        return '答案为空'

    options = q.get('options', [])
    if q_type == 'choice' and (not options or len(options) < 2):
        return '选择题至少需要2个选项'

    difficulty = int(q.get('difficulty', 2))
    analysis = q.get('analysis', f'导入的练习题')

    if knowledge_point not in custom:
        custom[knowledge_point] = []

    ex_id = f"import_{_uuid.uuid4().hex[:8]}"
    new_ex = {
        'id': ex_id,
        'type': q_type,
        'question': question_text,
        'difficulty': difficulty,
        'answer': answer,
        'analysis': analysis,
        'created_by': session.get('student_name', 'teacher'),
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if q_type == 'choice':
        new_ex['options'] = options

    custom[knowledge_point].append(new_ex)
    return None


@app.route('/api/learning-curve', methods=['GET'])
def get_learning_curve():
    """获取学习曲线数据"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    student_name = request.args.get('student_name', session.get('student_name', ''))
    # 学生只能查看自己的数据；老师可通过参数查看任意学生
    if session.get('role') != 'teacher':
        student_name = session.get('student_name', '')
    days = int(request.args.get('days', 30))
    
    records = load_learning_records()
    student_records = records.get(student_name, [])
    
    # 按日期分组统计
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
    
    # 生成曲线数据
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
        'total_records': len(student_records)
    })


@app.route('/api/today-progress', methods=['GET'])
def api_today_progress():
    """今日学习进度（日期口径与学习记录写入保持一致）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_name = session.get('student_name', '')
    today = datetime.now().strftime('%Y-%m-%d')
    records = load_learning_records().get(student_name, [])
    todays = [r for r in records if r.get('date') == today]

    done = len(todays)
    wrong = sum(1 for r in todays if r.get('activity_type') == 'wrong_question')
    scores = [r.get('score') for r in todays if r.get('score') is not None]
    goal = 10
    percent = min(100, int(round(done * 100.0 / goal))) if goal else 0
    accuracy = round((1 - wrong / float(done)) * 100, 1) if done else 0.0

    return jsonify({
        'success': True,
        'date': today,
        'done': done,
        'goal': goal,
        'percent': percent,
        'wrong': wrong,
        'accuracy': accuracy,
        'avg_score': round(sum(scores) / len(scores), 1) if scores else 0
    })


# ====================== 剧情实训成绩回传（接入学生能力画像） ======================

# 固定副本未携带题型明细时的默认能力维度映射
SCENE_DEFAULT_DIMS = {
    'ssv': ['equipment_operation', 'rf_engineering', 'troubleshooting'],
    'cluster': ['equipment_operation', 'rf_engineering', 'safety_awareness', 'troubleshooting'],
    'grid': ['equipment_operation', 'rf_engineering', 'safety_awareness', 'troubleshooting'],
}
VALID_DIM_IDS = {a['id'] for a in COMPETENCE_AREAS}


def _aggregate_scenario_dims(details, scene_id, rate):
    """按能力维度聚合得分率：优先用前端上报的题型明细，缺省回退到副本默认映射"""
    dim_rates = {}
    for d in details[:20]:
        if not isinstance(d, dict):
            continue
        dim, got, mx = d.get('dim'), d.get('got', 0), d.get('max', 0)
        if dim not in VALID_DIM_IDS:
            continue
        if not isinstance(got, (int, float)) or isinstance(got, bool) or \
           not isinstance(mx, (int, float)) or isinstance(mx, bool) or mx <= 0:
            continue
        dim_rates.setdefault(dim, []).append(min(100.0, max(0.0, got / mx * 100)))

    if dim_rates:
        return {dim: sum(rs) / len(rs) for dim, rs in dim_rates.items()}
    # 无明细：整体得分率平均计入该副本的默认维度
    return {dim: rate for dim in SCENE_DEFAULT_DIMS.get(scene_id, [])}


@app.route('/api/scenario-result', methods=['POST'])
def api_scenario_result():
    """剧情实训成绩回传：反哺能力画像 + 学习活动 + 成绩历史存档"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'student':
        return jsonify({'error': '仅记录学生成绩'}), 403

    data = request.get_json(silent=True) or {}
    scene_id = str(data.get('scene_id', ''))[:40]
    scene_name = str(data.get('scene_name', ''))[:60]
    score, score_max = data.get('score'), data.get('score_max')
    details = data.get('details') if isinstance(data.get('details'), list) else []

    if not scene_id or not scene_name:
        return jsonify({'error': '缺少副本标识'}), 400
    if not isinstance(score, (int, float)) or isinstance(score, bool) or \
       not isinstance(score_max, (int, float)) or isinstance(score_max, bool) or score_max <= 0:
        return jsonify({'error': '分数格式错误'}), 400
    score = max(0.0, min(float(score), float(score_max)))
    rate = round(score / float(score_max) * 100, 1)

    students = load_students()
    student = next((s for s in students if s.get('student_no') == session.get('student_no')), None)
    if not student:
        return jsonify({'error': '学生档案不存在'}), 404

    # 1) 反哺能力画像（与作业反哺同口径：得分率加权平均）
    dim_scores = _aggregate_scenario_dims(details, scene_id, rate)
    if dim_scores:
        # 兼容老档案：字段缺失或为空字典时补全全部维度键
        if not isinstance(student.get('competence_analysis'), dict) or not student['competence_analysis']:
            student['competence_analysis'] = {a['id']: {'count': 0, 'score': 0.0} for a in COMPETENCE_AREAS}
        for dim, dscore in dim_scores.items():
            if dim not in student['competence_analysis']:
                student['competence_analysis'][dim] = {'count': 0, 'score': 0.0}
            area = student['competence_analysis'][dim]
            area['count'] += 1
            area['score'] = round((area['score'] * (area['count'] - 1) + dscore) / area['count'], 2)

    # 2) 记录学习活动（驱动学习曲线与今日进度环）
    record_learning_activity(student.get('name', ''), 'scenario',
                             knowledge_point=scene_name, score=rate)

    # 3) 存档成绩历史（每人保留最近 50 次）
    history = student.setdefault('scenario_results', [])
    history.append({
        'scene_id': scene_id,
        'scene_name': scene_name,
        'score': round(score, 1),
        'score_max': round(float(score_max), 1),
        'rate': rate,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    if len(history) > 50:
        student['scenario_results'] = history[-50:]

    save_students(students)
    return jsonify({'success': True, 'rate': rate, 'dims': sorted(dim_scores.keys())})


@app.route('/api/scenario-results', methods=['GET'])
def api_scenario_results():
    """查询本人剧情实训成绩历史"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    students = load_students()
    student = next((s for s in students if s.get('student_no') == session.get('student_no')), None)
    return jsonify({'success': True, 'results': (student or {}).get('scenario_results', [])})


@app.route('/api/teacher-files', methods=['GET'])
def api_teacher_files():
    """老师共享文件：上传历史里非学生身份上传的文件（老师登录时 uploader 存老师名）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    try:
        student_names = {s.get('name') for s in load_students() if s.get('name')}
    except Exception:
        student_names = set()

    files = []
    for h in load_upload_history():
        if not h.get('download_name'):
            continue  # 源文件已删除的孤儿记录不展示
        uploader = h.get('uploader') or ''
        if uploader in student_names:
            continue  # 学生上传的不算老师共享
        files.append({
            'filename': h.get('filename'),
            'download_name': h.get('download_name'),
            'file_ext': (h.get('file_ext') or '').lower(),
            'upload_time': h.get('upload_time'),
            'uploader': uploader,
            'preview_ready': bool(h.get('preview_ready')),
            'page_count': h.get('page_count', 0),
            'preview_dir': h.get('preview_dir', '')
        })
    files.sort(key=lambda x: x.get('upload_time') or '', reverse=True)
    return jsonify({'success': True, 'files': files[:20]})


@app.route('/api/job-match', methods=['GET'])
def get_job_match():
    """获取岗位匹配度"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    student_name = request.args.get('student_name', session.get('student_name', ''))
    # 学生只能查看自己的数据；老师可通过参数查看任意学生
    if session.get('role') != 'teacher':
        student_name = session.get('student_name', '')
    job_name = request.args.get('job_name', '通信工程师')
    
    students = load_students()
    student = next((s for s in students if s.get('name') == student_name), None)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    student_scores = {}
    for area in student.get('competence_analysis', {}):
        student_scores[area] = student['competence_analysis'][area].get('score', 0)
    
    match_result = calculate_job_match_score(student_scores, job_name)
    
    # 所有岗位匹配度
    all_jobs = {}
    for job in JOB_REQUIREMENTS.keys():
        all_jobs[job] = calculate_job_match_score(student_scores, job)['match_rate']
    
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


@app.route('/api/competence-radar', methods=['GET'])
def get_competence_radar():
    """获取12维能力雷达图数据"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    student_name = request.args.get('student_name', session.get('student_name', ''))
    # 学生只能查看自己的数据；老师可通过参数查看任意学生
    if session.get('role') != 'teacher':
        student_name = session.get('student_name', '')
    
    students = load_students()
    student = next((s for s in students if s.get('name') == student_name), None)
    
    if not student:
        return jsonify({
            'success': True,
            'radar_data': [],
            'category_summary': {},
            'total_questions': 0
        })

    # 累计提问数：新字段优先；旧档案没有该字段时，用对话历史中的提问数兜底
    if 'total_questions' in student:
        total_questions = student.get('total_questions', 0)
    else:
        total_questions = sum(1 for m in (student.get('conversation_history') or [])
                              if m.get('is_question', True))

    radar_data = []
    category_summary = {}
    
    for area in COMPETENCE_AREAS:
        area_id = area['id']
        score_data = student.get('competence_analysis', {}).get(area_id, {'count': 0, 'score': 0})
        score = score_data.get('score', 0)
        count = score_data.get('count', 0)
        
        score_pct = round(score * 100, 1)
        radar_data.append({
            'id': area_id,
            'name': area['name'],
            'category': area['category'],
            'score': score_pct,
            'count': count,
            'weight': area['weight']
        })
        
        # 按类别汇总
        cat = area['category']
        if cat not in category_summary:
            category_summary[cat] = {'total_score': 0, 'count': 0, 'max': 0}
        category_summary[cat]['total_score'] += score_pct * area['weight']
        category_summary[cat]['count'] += 1
        category_summary[cat]['max'] += 100 * area['weight']
    
    return jsonify({
        'success': True,
        'student_name': student_name,
        'radar_data': radar_data,
        'category_summary': category_summary,
        'total_questions': total_questions
    })


@app.route('/api/knowledge-graph', methods=['GET'])
def get_knowledge_graph():
    """获取知识图谱"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    keyword = request.args.get('keyword', '')
    
    if keyword:
        results = {}
        for kp, info in KNOWLEDGE_GRAPH.items():
            if keyword in kp or any(keyword in r for r in info.get('related', [])):
                results[kp] = info
        return jsonify({'success': True, 'graph': results, 'keyword': keyword})
    
    return jsonify({
        'success': True,
        'graph': KNOWLEDGE_GRAPH,
        'total_concepts': len(KNOWLEDGE_GRAPH)
    })


# ====================== PPT学习资源API ======================
@app.route('/api/ppt/search', methods=['GET'])
def search_ppt():
    """根据关键词搜索PPT"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    keyword = request.args.get('keyword', '')
    if not keyword:
        return jsonify({'error': '请提供搜索关键词'}), 400
    
    results = search_ppt_by_keyword(keyword)
    
    return jsonify({
        'success': True,
        'keyword': keyword,
        'results': results,
        'count': len(results)
    })


@app.route('/api/ppt/list', methods=['GET'])
def list_ppt():
    """获取所有PPT列表"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    metadata = load_ppt_metadata()
    metadata.sort(key=lambda x: x['upload_time'], reverse=True)
    
    return jsonify({
        'success': True,
        'ppt_list': metadata,
        'count': len(metadata)
    })


@app.route('/ppt-resources-page')
def ppt_resources_page():
    """课件中心页面 - 查看所有教师上传的PPT"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('ppt_resources.html')


@app.route('/student-portrait-page')
def student_portrait_page():
    """学生能力画像页面（12维雷达图）"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('student_portrait.html')


@app.route('/wrong-questions-page')
def wrong_questions_page():
    """错题本页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('wrong_questions.html')


@app.route('/knowledge-graph-page')
def knowledge_graph_page():
    """知识图谱页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('knowledge_graph.html')


@app.route('/scenario-page')
def scenario_page():
    """场景模拟页面"""
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('scenario.html')


@app.route('/scenario-demo')
def scenario_demo():
    """剧情演绎演示页面"""
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('scenario_demo.html')


@app.route('/scenario-cluster')
def scenario_cluster():
    """剧情演练副本二：5G 簇优化（簇2）十步实训"""
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('scenario_cluster.html')


@app.route('/scenario-grid')
def scenario_grid():
    """剧情演练副本三：5G 网格优化（网格1）十步实训"""
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('scenario_grid.html')


@app.route('/scenario-ai')
def scenario_ai():
    """AI 自定义剧情：任意主题自动生成实训剧本"""
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('scenario_ai.html')


# ====================== AI 自动生成场景实训 ======================

SCENARIO_GEN_PROMPT = """你是通信与电子信息工程领域的资深实训专家，擅长把真实工程项目设计成"沉浸式、强交互、有陷阱"的虚拟仿真训练剧本。请根据用户提供的场景主题与要求，生成一套【长流程、高保真】的交互式实训。

【最重要铁律】
1. 所有内容必须紧扣用户主题！主题是数据中心就写数据中心，是光纤铺设就写光纤铺设，严禁默认套用5G基站内容。
2. 只输出纯JSON（不要markdown代码块、不要解释文字），必须是合法JSON：双引号、无注释、无尾逗号。
3. 输出格式固定：{"steps": [...], "scoreMax": 数字}

══════════ 一、总体结构（10-13步，工程全流程） ══════════
参考真实工程"接报→研判→准备→现场→诊断→处置→验收→复盘"闭环，按主题裁剪：
  text 接警/项目背景（含时间地点、工单或告警编号、影响范围、时限压力）
  choice 角色分工/班组协同选择（1-2个）
  quiz 第一轮研判：资料会审/告警关联分析（3-4小题）
  text 出动准备：安全交底、工器具与仪表清单、行车/进场要点
  siteselect 现场优先级选择（故障抢修类用"先修哪个点"，设计类用"点位/路由选择"；主题不适合可省略）
  survey 第一轮现场勘察/实测（3-4个tab、9-12个字段，含3-6个仪表测量项）
  quiz 第二轮深度诊断推理（3-5小题，基于上一步实测数据，含"表面恢复假象/误判根因"陷阱）
  choice或text 处置决策点（资源受限下的方案权衡，如"带油机先抢通 vs 等备件彻底修"）
  survey 第二轮可选（主题需要时）：处置后复测数据（1-2个tab即可）
  design 处置/设计方案（4-5组决策题）
  quiz 验收与拨测（2-3小题：验收门限、业务验证、规范红线）
  text 复盘归档：故障根因树、处理经过、经验沉淀、预防措施
要求：text 4-6个、choice 1-2个、quiz 2-3个、survey 1-2个、design 1个、siteselect 0-1个，总数10-12步。

══════════ 二、高保真要求（决定真实感，务必做到） ══════════
1. 专业细节真实：使用真实告警名称、KPI指标、门限值与仪表（如驻波比VSWR<1.5、RRU/BBU、光功率预算dBm、OTDR曲线事件、FEC误码BER、接地电阻<10Ω、红外测温温差、PDU/UPS、熔纤盘损耗等，按主题选取，不要堆砌）。
2. 数据自洽：survey里plan的参考值、measure测量值、quiz题目引用的数据必须前后一致（比如测出VSWR 2.8，后面诊断题就要围绕2.8展开）。
3. 诊断有层次：设置"表象原因"和"真正根因"，错误选项要有现场迷惑性（如"重启基站试试""直接换设备"），feedback必须讲清为什么错、正确思路是什么。
4. 安全与规范：至少1道题考安全红线（断电验电、接地、登高、有限空间、雷雨作业、动火等按主题选）。
5. 工程约束：体现时间压力、人手/备件/预算受限、多专业协同、客户沟通等真实约束。
6. 文案有现场感：像真实工单和师傅带教，简洁有力；feedback每条1-2句，先判定再讲原理，避免长篇大论。
7. 内容用<b>加粗</b>关键词、<br>换行；所有文本字段值内严禁出现英文双引号(")和反斜杠(\)，引用话语一律用中文引号「」，也不要写裸换行符（用<br>代替）；不要出现"AI/模型/本剧本"等穿帮词。
8. 仪表-物理量必须匹配（硬性铁律）：measure的device只能测对应物理量——laser=长度/高度/距离/挂高，infrared=温度/温差，multimeter=低压(≤1000V)电压/小电流(≤1000A)/通断，ground_tester=接地电阻/土壤电阻率，otdr=光缆长度/衰耗/断点位置，opm=光功率dBm，spectrum=频谱/干扰/场强(dBm)，site_master=天馈电气参数（方位角/下倾角/驻波比/馈损）。严禁错配：功率/负荷/容量/面积/荷载/带宽等无法仪表直读的量不配measure（改select或input）；高压(≥1kV)电压严禁万用表直读（改"查PT柜表计"类input）；移动网络覆盖指标（RSRP/SINR/下载速率）必须用路测终端而非频谱仪/天馈仪，此类字段不配measure、用input（ph提示"路测终端读数"）。
9. 时间约束符合行业实际：设计周期、建设工期、验收周期要符合真实工程节奏（如数据中心建设以月/年计），不得出现明显失真的"超级工期"；时限压力用"阶段性节点"表达而非整体失真。

══════════ 三、六种步骤类型的JSON格式（严格遵守） ══════════

1. text 背景/说明
{"type":"text","title":"步骤标题","label":"2-4字标签","content":"HTML内容，可用<b>和<br>","nextText":"按钮文案（贴合上下文，如'领取工单''出发上站'）"}

2. choice 单选决策（岗位/方案/协同）
{"type":"choice","title":"步骤标题","label":"标签","intro":"HTML引导语","options":[
 {"name":"选项名","sub":"说明","good":true,"feedback":"✅ 选对：详细原因"},
 {"name":"选项名","sub":"说明","feedback":"❌ 选错：为什么不行"}]}
仅一个 good:true。

3. quiz 连环选择题（研判/诊断/验收）
{"type":"quiz","title":"步骤标题","label":"标签","heatmap":false,"subSteps":[
 {"q":"题干（可含<b>）","options":[{"name":"选项","sub":"解析/现象"},{"name":"选项","sub":""}],"correct":1},
 {"q":"多选题干","multi":true,"required":[0,2],"options":[...],"sub":""}]}
- subSteps 2-5个；单选 correct 为数字索引；多选 multi:true 且 required 为必选索引数组。
- heatmap 字段：仅当本步骤需要"信号/覆盖摸测地图"可视化时设 true（整套实训最多1个），其余一律 false 或省略。

4. siteselect 地图选点
{"type":"siteselect","title":"步骤标题","label":"标签","intro":"HTML引导语","spots":[
 {"name":"点位名","ok":true,"x":46,"y":38,"feedback":"✅ 详细分析"},
 {"name":"点位名","ok":false,"x":78,"y":30,"feedback":"❌ 原因分析"}],"correctIdx":0}
x∈[5,90]，y∈[15,75]，仅一个 ok:true。

5. survey 勘察/测量表
{"type":"survey","title":"步骤标题","label":"标签","intro":"HTML引导语",
 "tabs":["Tab1","Tab2","Tab3"],
 "plan":[[["字段名","参考值"]],[["字段名","参考值"]],[["字段名","参考值"]]],
 "fields":[
  {"tab":0,"key":"字段名","type":"input","ph":"单位/提示"},
  {"tab":0,"key":"字段名","type":"select","opts":["选项A","选项B","选项C"]},
  {"tab":0,"key":"字段名","type":"input","ph":"点击测量","measure":{"device":"site_master","icon":"📟","name":"仪表名","value":"实测值含单位"}}]}
- tabs 2-4个；plan 与 tabs 一一对应（参考资料弹窗用）；fields 的 tab 为索引。
- device 可选：site_master(天馈仪)、otdr(光时域反射仪)、infrared(红外测温)、multimeter(万用表)、ground_tester(接地电阻仪)、opm(光功率计)、laser(激光测距)、spectrum(频谱仪)，按主题选，icon 用合适emoji；device与物理量的匹配必须遵守高保真要求第8条。
- measure 测量值必须与后续诊断题数据一致。

6. design 最终方案决策
{"type":"design","title":"步骤标题","label":"标签","intro":"HTML引导语（可先给现场结论）","groups":[
 {"q":"决策题1","options":["A","B","C"],"correct":0},
 {"q":"决策题2","options":["A","B","C","D"],"correct":2}],"result":"最终方案HTML总结（含验收门限与交付物）"}
groups 4-5个，options 3-4个。

══════════ 四、评分 scoreMax 计算（务必精确） ══════════
scoreMax = 所有quiz的subSteps总数（每题1分）+ siteselect个数×2 + 所有survey中measure字段总数（每项1分）+ design的groups数（每组1分）。choice和text不计分。

══════════ 五、输出前自检 ══════════
步骤数10-12；题型与字段完整；x/y在范围内；correct/required索引不越界；plan与tabs数量一致；数据前后自洽；JSON可被json.loads直接解析。"""


def _sanitize_scenario_steps(steps):
    """逐题校验 AI 生成的步骤，修复/剔除不可作答的题目：
    - quiz 小题：单选 correct 必须是合法索引；多选 required 必须是非空合法索引数组，
      多选 required 非法但 correct 合法时降级为单选，仍非法则剔除该小题
    - choice：必须存在 good 选项，多个 good 只保留第一个
    - siteselect：只允许一个 ok:true，无 ok 则剔除整个步骤
    - design：correct 非法索引的决策组剔除
    - survey：measure 字段残缺的降级为普通手填项
    """
    valid_types = {'text', 'choice', 'quiz', 'siteselect', 'survey', 'design'}
    list_fields = {'choice': 'options', 'quiz': 'subSteps', 'siteselect': 'spots',
                   'survey': 'fields', 'design': 'groups'}

    def _valid_idx(v, n):
        return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < n

    cleaned = []
    for st in steps:
        if not isinstance(st, dict) or st.get('type') not in valid_types:
            break
        lf = list_fields.get(st['type'])
        if lf and not isinstance(st.get(lf), list):
            break
        t = st['type']
        if t == 'quiz':
            subs = []
            for sub in st.get('subSteps', []):
                if not isinstance(sub, dict) or not isinstance(sub.get('options'), list) or len(sub['options']) < 2:
                    continue
                n = len(sub['options'])
                if sub.get('multi'):
                    req = sub.get('required')
                    if isinstance(req, list) and req and all(_valid_idx(v, n) for v in req):
                        subs.append(sub)
                    elif _valid_idx(sub.get('correct'), n):
                        sub.pop('multi', None); sub.pop('required', None)
                        subs.append(sub)
                    # 两个都非法：剔除该小题
                elif _valid_idx(sub.get('correct'), n):
                    subs.append(sub)
            if not subs:
                break  # 连环题全部小题非法，丢弃该步及后续（视为截断）
            st['subSteps'] = subs
        elif t == 'choice':
            opts = st.get('options', [])
            goods = [o for o in opts if isinstance(o, dict) and o.get('good')]
            if not goods:
                break
            seen = False
            for o in opts:
                if isinstance(o, dict) and o.get('good'):
                    if seen:
                        o.pop('good', None)
                    seen = True
        elif t == 'siteselect':
            spots = st.get('spots', [])
            has_ok = False
            for sp in spots:
                if isinstance(sp, dict) and sp.get('ok'):
                    if has_ok:
                        sp.pop('ok', None)
                    has_ok = True
            if not has_ok:
                break
        elif t == 'design':
            groups = [g for g in st.get('groups', [])
                      if isinstance(g, dict) and isinstance(g.get('options'), list) and _valid_idx(g.get('correct'), len(g['options']))]
            if not groups:
                break
            st['groups'] = groups
        elif t == 'survey':
            for f in st.get('fields', []):
                if isinstance(f, dict) and f.get('measure'):
                    m = f['measure']
                    if not isinstance(m, dict) or not m.get('value') or not m.get('device'):
                        f.pop('measure', None)
        cleaned.append(st)
    return cleaned


@app.route('/api/scenario/generate', methods=['POST'])
def api_generate_scenario():
    """AI自动生成交互式场景实训"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    try:
        data = request.get_json()
        topic = (data.get('topic') or '').strip()
        question = (data.get('question') or '').strip()

        if not topic:
            return jsonify({'error': '请提供场景主题'}), 400

        user_prompt = f"场景主题：{topic}\n具体要求：{question or '请根据该主题生成完整的交互式实训流程'}"
        if not question:
            user_prompt += "\n请自行设计合理的实训环节（背景→岗位选择→测试摸测→参数查询→选址→勘察表→最终设计），所有内容紧扣主题。"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        messages = [
            {"role": "system", "content": SCENARIO_GEN_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        payload = {
            "model": MODEL_FLASH,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 12000,
            "stream": True,
            "enable_thinking": False  # 关闭长思考链：生成时长由约8分钟降至1-3分钟
        }

        print(f"[场景生成] 主题={topic}, 开始流式调用AI（约需1-3分钟）...")
        # 流式接收：90秒内有任意数据块到达即保活，墙钟总时长兜底480秒
        resp = requests.post(API_URL, headers=headers, json=payload,
                             stream=True, timeout=(30, 90))

        if resp.status_code != 200:
            err_text = resp.text[:300]
            print(f"[场景生成] AI请求失败: {resp.status_code} - {err_text}")
            return jsonify({'error': f'AI请求失败: {resp.status_code}'}), 500

        chunks = []
        deadline = time.time() + 480
        for line in resp.iter_lines():
            if time.time() > deadline:
                resp.close()
                return jsonify({'error': 'AI创作超时（超过8分钟），请缩短要求或稍后重试'}), 504
            if not line:
                continue
            data_line = line.decode("utf-8", errors="ignore").strip()
            if not data_line.startswith("data:"):
                continue
            data_str = data_line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
                delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    chunks.append(delta)
            except (ValueError, IndexError, KeyError):
                continue

        answer = "".join(chunks).strip()
        if not answer:
            return jsonify({'error': 'AI未返回有效内容，请重试'}), 502
        print(f"[场景生成] 流式接收完成，正文 {len(answer)} 字符")

        # 去除可能的 ```json / ``` 包裹
        if answer.startswith('```'):
            answer = re.sub(r'^```(?:json)?\s*', '', answer)
            answer = re.sub(r'\s*```$', '', answer)

        # 多级容错解析：原文 → 去尾逗号 → 截取首尾大括号 → 截取后去尾逗号 → 截断自动补全
        def _loose_json_loads(txt):
            s, e = txt.find('{'), txt.rfind('}')
            core = txt[s:e + 1] if s >= 0 and e > s else txt
            cands = [txt,
                     re.sub(r',(\s*[}\]])', r'\1', txt),
                     core,
                     re.sub(r',(\s*[}\]])', r'\1', core)]

            def _close_json(prefix):
                """字符串感知的栈式补全：按未闭合括号的正确顺序补全（字符串值内的括号不参与计数）"""
                stack, in_str, esc = [], False, False
                for ch in prefix:
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == '\\':
                            esc = True
                        elif ch == '"':
                            in_str = False
                    else:
                        if ch == '"':
                            in_str = True
                        elif ch in '{[':
                            stack.append(ch)
                        elif ch == '}' and stack and stack[-1] == '{':
                            stack.pop()
                        elif ch == ']' and stack and stack[-1] == '[':
                            stack.pop()
                if in_str:
                    prefix += '"'
                return prefix + ''.join('}' if c == '{' else ']' for c in reversed(stack))

            # 截断补全：输出达到 max_tokens 被截断时，从末尾逐个边界回退，补全未闭合括号
            # 优先直接补全全文（截断点在字符串/数值中间时保住最多内容）
            for closed in (_close_json(txt), _close_json(core)):
                cands.append(closed)
                cands.append(re.sub(r',(\s*[}\]])', r'\1', closed))
            # 再从末尾的对象/键边界逐个回退补全（截断尾部残缺键值对时丢弃不完整部分）
            # 注意：必须在原始 txt 上搜边界，core 的 rfind('}') 会丢弃截断尾部导致深层截断无法回退
            bounds = sorted({m.start() for m in re.finditer(r',\s*\{', txt)} |
                            {m.start() for m in re.finditer(r',\s*"', txt)})
            for pos in reversed(bounds[-6:]):  # 最多回退6个边界
                for closed in (_close_json(txt[:pos]), _close_json(txt[:pos + 1])):
                    cands.append(closed)
                    cands.append(re.sub(r',(\s*[}\]])', r'\1', closed))
            for cand in cands:
                try:
                    return json.loads(cand)
                except json.JSONDecodeError:
                    continue
            return None

        result = _loose_json_loads(answer)
        if result is None:
            try:
                json.loads(answer)
            except json.JSONDecodeError as je:
                print(f"[场景生成] JSON解析失败 pos={je.pos} 上下文: "
                      f"{answer[max(0, je.pos-120):je.pos+120]}")
            return jsonify({'error': 'AI返回的JSON格式有误，请重试一次'}), 502

        steps = result.get('steps', [])
        score_max = result.get('scoreMax', 0)

        if not steps or not isinstance(steps, list):
            return jsonify({'error': 'AI生成的实训步骤为空或格式错误'}), 500

        # 逐题校验 + 截断挽救：剔除残缺尾步与不可作答的题目（correct 非法等），
        # 保证返回给前端的每一道题都有正确答案且可正常计分
        before = len(steps)
        steps = _sanitize_scenario_steps(steps)
        if len(steps) < before:
            print(f"[场景生成] 校验修复：丢弃 {before - len(steps)} 个残缺/不可作答步骤")
        if not steps:
            return jsonify({'error': 'AI生成的实训步骤为空或格式错误，请重试一次'}), 500

        # scoreMax 以步骤结构重算为准，防止 AI 算错分导致得分显示异常
        def _calc_score(s):
            total = 0
            for st in s:
                t = st.get('type')
                if t == 'quiz':
                    total += len(st.get('subSteps', []))
                elif t == 'siteselect':
                    total += 2
                elif t == 'survey':
                    total += sum(1 for f in st.get('fields', [])
                                 if isinstance(f, dict) and f.get('measure'))
                elif t == 'design':
                    total += len(st.get('groups', []))
            return total

        calc_score = _calc_score(steps)
        if not isinstance(score_max, int) or score_max != calc_score:
            print(f"[场景生成] AI给出scoreMax={score_max}，按结构重算为{calc_score}")
            score_max = calc_score

        print(f"[场景生成] 成功！生成 {len(steps)} 步, 满分 {score_max}")
        return jsonify({'steps': steps, 'scoreMax': score_max})

    except requests.Timeout:
        return jsonify({'error': 'AI创作超时（数据中断过久），请稍后重试'}), 504
    except Exception as e:
        print(f"[场景生成] 异常: {e}")
        return jsonify({'error': f'生成失败: {str(e)}'}), 500


@app.route('/exercise-page')
def exercise_page():
    """互动式练习页面"""
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('exercise.html')


# ====================== 学生档案管理路由 ======================
def _student_belongs_to_session(student):
    """判断学生档案是否属于当前登录的学生本人"""
    my_no = session.get('student_no', '')
    my_name = session.get('student_name', '')
    return (my_no and student.get('student_no') == my_no) or student.get('name') == my_name


@app.route('/students', methods=['GET'])
def get_students():
    """获取学生列表（老师可见全部；学生只能看到自己）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    students = load_students()
    if session.get('role') != 'teacher':
        my_no = session.get('student_no', '')
        my_name = session.get('student_name', '')
        students = [s for s in students
                    if (my_no and s.get('student_no') == my_no) or s.get('name') == my_name]
    return jsonify({'students': students})


@app.route('/students/<string:student_id>', methods=['GET'])
def get_student(student_id):
    """获取单个学生详情"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    
    if student:
        if session.get('role') != 'teacher' and not _student_belongs_to_session(student):
            return jsonify({'error': '无权查看其他学生的信息'}), 403
        return jsonify({'student': student})
    else:
        return jsonify({'error': '学生不存在'}), 404


@app.route('/students', methods=['POST'])
def create_student():
    """创建新学生"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能添加学生'}), 403
    
    data = request.get_json()
    name = data.get('name')
    student_no = data.get('student_no', '')
    class_name = data.get('class_name', '')
    avatar = data.get('avatar', None)
    
    if not name:
        return jsonify({'error': '请输入学生姓名'}), 400
    
    students = load_students()
    
    # 如果提供了学号，检查学号是否已存在
    if student_no:
        if not student_no.isdigit() or len(student_no) != 13:
            return jsonify({'error': '学号必须是13位数字'}), 400
        existing = next((s for s in students if s.get('student_no') == student_no), None)
        if existing:
            return jsonify({'error': '该学号已存在，一个学号只能注册一个账号'}), 400
    
    # 生成唯一ID（取现有最大ID+1，避免删除学生后撞号）
    new_id = next_student_id(students)
    
    new_student = {
        'id': new_id,
        'student_no': student_no,
        'name': name,
        'class_name': class_name,
        'avatar': avatar,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'competence_analysis': {area['id']: {'count': 0, 'score': 0.0} for area in COMPETENCE_AREAS},
        'conversation_history': []
    }
    
    students.append(new_student)
    save_students(students)
    
    return jsonify({'success': True, 'student': new_student})


@app.route('/students/<string:student_id>', methods=['PUT'])
def update_student(student_id):
    """更新学生信息"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.get_json()
    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    if 'name' in data:
        student['name'] = data['name']
    if 'class_name' in data:
        student['class_name'] = data['class_name']
    if 'avatar' in data:
        student['avatar'] = data['avatar']
    
    save_students(students)
    return jsonify({'success': True, 'student': student})


@app.route('/students/<string:student_id>', methods=['DELETE'])
def delete_student(student_id):
    """删除学生（同时清理其错题本和学习记录）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能删除学生'}), 403

    students = load_students()
    target = next((s for s in students if s['id'] == student_id), None)
    if not target:
        return jsonify({'error': '学生不存在'}), 404

    students = [s for s in students if s['id'] != student_id]
    save_students(students)

    # 按姓名清理关联数据：错题本 + 学习记录
    name = target.get('name', '')
    if name:
        questions = load_wrong_questions()
        remain = [q for q in questions if q.get('student_name') != name]
        if len(remain) != len(questions):
            save_wrong_questions(remain)

        records = load_learning_records()
        if name in records:
            del records[name]
            save_learning_records(records)

    return jsonify({'success': True, 'deleted': name})


@app.route('/students/<string:student_id>/report', methods=['GET'])
def get_student_report(student_id):
    """获取学生个性化分析报告"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    if session.get('role') != 'teacher' and not _student_belongs_to_session(student):
        return jsonify({'error': '无权查看其他学生的报告'}), 403

    report = generate_personalized_report(student_id)
    return jsonify(report)


@app.route('/students/<string:student_id>/ai-analysis', methods=['GET'])
def ai_student_analysis(student_id):
    """一键AI个性化分析（SSE流式）：综合对话历史+错题+学习记录，生成优缺点与学习建议"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    if session.get('role') != 'teacher' and not _student_belongs_to_session(student):
        return jsonify({'error': '无权查看其他学生的报告'}), 403

    system_content, prompt = build_student_analysis_prompt(student)
    return analysis_sse_generator(system_content, prompt, max_tokens=1200)


@app.route('/api/teacher/lesson-plan', methods=['POST'])
def teacher_lesson_plan():
    """教师一键生成教案（SSE流式）：根据教师提供的主题/要求/资料文件生成结构化教案"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可使用教案生成'}), 403

    topic = (request.form.get('topic') or '').strip()
    requirements = (request.form.get('requirements') or '').strip()
    if not topic:
        return jsonify({'error': '请填写课程/章节主题'}), 400

    # 可选：上传资料文件，提取文本作为参考资料
    material_text = ''
    uploaded = request.files.get('file')
    tmp_path = None
    if uploaded and uploaded.filename and '.' in uploaded.filename:
        ext = uploaded.filename.rsplit('.', 1)[1].lower()
        if ext in ('pptx', 'docx', 'txt'):
            try:
                tmp_path = os.path.join(UPLOAD_FOLDER, f"lp_{uuid.uuid4().hex}.{ext}")
                uploaded.save(tmp_path)
                material_text = extract_text_from_document(tmp_path) or ''
            except Exception:
                material_text = ''
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    # 截断参考资料，避免 prompt 过长拖慢响应
    if len(material_text) > 6000:
        material_text = material_text[:6000] + '\n……（资料已截断）'

    system_content = (
        "你是一位资深通信工程教育专家与教案设计顾问。"
        "请根据教师提供的教学主题、教学要求和参考资料，撰写一份结构完整、可直接用于备课的高质量教案。"
        "要求：\n"
        "1. 使用 Markdown 格式，包含以下固定模块：\n"
        "   ## 一、教学目标（知识/能力/素养三维度）\n"
        "   ## 二、教学重点与难点\n"
        "   ## 三、教学过程（含时间分配，如导入5min/新授30min/练习10min）\n"
        "   ## 四、教学方法与手段\n"
        "   ## 五、课堂练习与互动设计\n"
        "   ## 六、课后作业与拓展\n"
        "   ## 七、教学反思（预设学生易错点与应对）\n"
        "2. 内容贴合通信工程专业实际，结合工程案例，避免空泛。\n"
        "3. 时间分配合计与课时一致。\n"
        "4. 语言精炼、条理清晰。\n"
        "5. 末尾另起一行输出标识：✨ 本教案由 AI 生成，仅供参考"
    )

    prompt = f"【教学主题】{topic}\n"
    if requirements:
        prompt += f"\n【教学要求/学生情况/课时/特殊说明】\n{requirements}\n"
    if material_text:
        prompt += f"\n【教师提供的参考资料（PPT/Word/TXT 提取文本）】\n{material_text}\n"
    prompt += "\n请根据以上信息生成一份完整教案。"

    return analysis_sse_generator(system_content, prompt, max_tokens=2000, temperature=0.7)


# ====================== 教师发布作业 / AI 批改 ======================
def _strip_homework_answers(hw: Dict) -> Dict:
    """学生未提交时剥离答案/解析/参考答案，防止泄露"""
    safe = {k: v for k, v in hw.items() if k != 'questions'}
    safe_questions = []
    for q in hw.get('questions', []):
        qq = {'id': q.get('id'), 'type': q.get('type'), 'question': q.get('question'),
              'score': q.get('score', 0)}
        if q.get('type') == 'choice':
            qq['options'] = q.get('options', {})
        safe_questions.append(qq)
    safe['questions'] = safe_questions
    return safe


def grade_text_answers_by_ai(items: List[Dict]) -> Dict[str, Dict]:
    """AI 批改主观题（一次调用批改全部）
    items: [{question_id, question, reference_answer, max_score, student_answer}]
    返回 {question_id: {score, feedback}}；任何异常均保底，不阻塞提交"""
    result: Dict[str, Dict] = {}
    if not items:
        return result
    try:
        sys_prompt = (
            "你是通信工程课程助教，负责批改学生的主观题作答。"
            "依据题目、参考答案和满分给学生答案打分（0到满分，答到要点即给分），"
            "并给出简短、鼓励性的批改意见（指出正确点、不足与改进方向）。"
            "严格只返回JSON数组，不要输出任何额外文字或markdown代码块，格式："
            '[{"question_id":"q2","score":8,"feedback":"…"}]'
        )
        blocks = []
        for it in items:
            blocks.append(
                f"【题号】{it['question_id']}\n【题目】{it['question']}\n"
                f"【参考答案】{it.get('reference_answer') or '（无）'}\n"
                f"【满分】{it.get('max_score', 10)}\n【学生答案】{it.get('student_answer') or '（未作答）'}"
            )
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL_FLASH,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": "请批改以下主观题：\n\n" + "\n\n".join(blocks)},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
                "stream": False,
                "enable_thinking": False,
            },
            timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"AI HTTP {resp.status_code}")
        content = resp.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"\[.*\]", content, re.S)
        parsed = json.loads(m.group(0) if m else content)
        for row in parsed:
            qid = str(row.get("question_id", ""))
            try:
                score = float(row.get("score", 0))
            except (TypeError, ValueError):
                score = 0
            result[qid] = {"score": score, "feedback": str(row.get("feedback", "")).strip()}
    except Exception as e:
        print(f"[作业AI批改] 失败，转人工: {e}")
    for it in items:  # 保底：AI未返回的题目
        if it["question_id"] not in result:
            result[it["question_id"]] = {"score": 0, "feedback": "AI 暂未批改，请等待老师人工批改"}
    return result


def _final_submission_score(sub: Dict):
    """取教师覆盖分，否则取AI/自动总分"""
    if sub.get('teacher_score_override') is not None:
        return sub.get('teacher_score_override')
    return sub.get('ai_score_total', 0)


@app.route('/homework-page')
def homework_page():
    """作业管理/作答页（师生共用，前端按 role 区分）"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('homework.html')


@app.route('/api/homework', methods=['GET'])
def api_homework_list():
    """作业列表：教师看全部+统计；学生只看本班（未提交剥离答案）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    all_hw = load_homework()
    submissions = load_homework_submissions()

    if session.get('role') == 'teacher':
        students = load_students()
        out = []
        for hw in all_hw:
            classes = hw.get('class_names', [])
            subbed = [sub for sub in submissions if sub.get('homework_id') == hw['id']]
            scores = [_final_submission_score(sub) for sub in subbed]
            by_class = {}
            total_students = 0
            for cname in classes:
                members = [s for s in students if s.get('class_name') == cname]
                total_students += len(members)
                member_nos = {s.get('student_no') for s in members}
                submitted_nos = {sub.get('student_no') for sub in subbed if sub.get('student_no') in member_nos}
                by_class[cname] = {
                    'student_count': len(members),
                    'submitted_count': len(submitted_nos),
                    'unsubmitted': [s.get('name') for s in members if s.get('student_no') not in submitted_nos],
                }
            out.append({
                **hw,
                'total_students': total_students,
                'submitted_count': len(subbed),
                'avg_score': round(sum(scores) / len(scores), 1) if scores else None,
                'by_class': by_class,
            })
        out.sort(key=lambda h: h.get('created_at', ''), reverse=True)
        return jsonify({'success': True, 'homework': out})

    # 学生视图
    current_class = session.get('class_name', '')
    student_no = session.get('student_no', '')
    out = []
    for hw in all_hw:
        if current_class not in hw.get('class_names', []):
            continue
        my_sub = next((sub for sub in submissions
                       if sub.get('homework_id') == hw['id'] and sub.get('student_no') == student_no), None)
        item = hw if my_sub else _strip_homework_answers(hw)
        item = dict(item)
        item['my_submission'] = my_sub  # 已提交则带本人完整记录（含答案/批改），未提交为None
        out.append(item)
    out.sort(key=lambda h: h.get('created_at', ''), reverse=True)
    return jsonify({'success': True, 'homework': out})


@app.route('/api/homework', methods=['POST'])
def api_homework_create():
    """教师发布作业（multipart/form-data）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可发布作业'}), 403

    title = (request.form.get('title') or '').strip()
    description = (request.form.get('description') or '').strip()
    deadline = (request.form.get('deadline') or '').strip()
    if not title:
        return jsonify({'error': '作业标题不能为空'}), 400
    try:
        class_names = json.loads(request.form.get('class_names') or '[]')
        questions = json.loads(request.form.get('questions') or '[]')
    except json.JSONDecodeError:
        return jsonify({'error': '表单数据格式错误'}), 400
    class_names = [c for c in class_names if c]
    if not class_names:
        return jsonify({'error': '请至少选择一个班级'}), 400
    if not questions:
        return jsonify({'error': '请至少添加一道题目'}), 400

    clean_questions = []
    for i, q in enumerate(questions, 1):
        qtype = q.get('type')
        qtext = (q.get('question') or '').strip()
        if not qtext:
            return jsonify({'error': f'第{i}题题干为空'}), 400
        try:
            score = float(q.get('score') if q.get('score') not in (None, '') else 0)
        except (TypeError, ValueError):
            score = 0
        qd = {'id': f'q{i}', 'type': qtype, 'question': qtext, 'score': score}
        cdim = (q.get('competence_dim') or '').strip()
        if cdim:
            qd['competence_dim'] = cdim
        if qtype == 'choice':
            options = {k: str(v).strip() for k, v in (q.get('options') or {}).items() if str(v).strip()}
            if len(options) < 2:
                return jsonify({'error': f'第{i}题至少需要2个有效选项'}), 400
            answer = (q.get('answer') or '').strip()
            if answer not in options:
                return jsonify({'error': f'第{i}题请选择正确答案'}), 400
            qd['options'] = options
            qd['answer'] = answer
            qd['analysis'] = (q.get('analysis') or '').strip()
        elif qtype == 'text':
            qd['reference_answer'] = (q.get('reference_answer') or '').strip()
        else:
            return jsonify({'error': f'第{i}题题型无效'}), 400
        clean_questions.append(qd)

    attachment = None
    f = request.files.get('file')
    if f and f.filename:
        saved = save_uploaded_file(f, 'document')
        if saved:
            attachment = {'filename': saved.get('filename'), 'stored_filename': saved.get('stored_filename')}

    homework_list = load_homework()
    new_id = max([h.get('id', 0) for h in homework_list] + [0]) + 1
    hw = {
        'id': new_id,
        'title': title,
        'description': description,
        'class_names': class_names,
        'deadline': deadline,
        'attachment': attachment,
        'questions': clean_questions,
        'creator': session.get('student_name', 'teacher'),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    homework_list.append(hw)
    save_homework(homework_list)
    return jsonify({'success': True, 'homework': hw})


@app.route('/api/homework/<int:hw_id>/submit', methods=['POST'])
def api_homework_submit(hw_id):
    """学生提交作业：选择题自动判分 + 主观题AI批改（重交覆盖）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'student':
        return jsonify({'error': '仅学生可提交作业'}), 403

    hw = next((h for h in load_homework() if h.get('id') == hw_id), None)
    if not hw:
        return jsonify({'error': '作业不存在'}), 404

    student_no = session.get('student_no', '')
    current_class = session.get('class_name', '')
    if current_class not in hw.get('class_names', []):
        return jsonify({'error': '该作业不属于你的班级'}), 403

    raw_answers = (request.get_json() or {}).get('answers') or {}
    graded_answers = {}
    choice_score = 0.0
    text_items = []

    for q in hw.get('questions', []):
        qid = q['id']
        val = raw_answers.get(qid)
        student_val = val.strip() if isinstance(val, str) else ''
        if q.get('type') == 'choice':
            is_correct = student_val == q.get('answer')
            sc = q.get('score', 0) if is_correct else 0
            choice_score += sc
            graded_answers[qid] = {'answer': student_val, 'is_correct': is_correct, 'score': sc}
        else:
            text_items.append({
                'question_id': qid,
                'question': q.get('question', ''),
                'reference_answer': q.get('reference_answer', ''),
                'max_score': q.get('score', 10),
                'student_answer': student_val,
            })
            graded_answers[qid] = {'answer': student_val, 'score': 0,
                                   'ai_feedback': 'AI 暂未批改，请等待老师人工批改'}

    # 是否迟交
    late = False
    if hw.get('deadline'):
        try:
            dl_str = hw['deadline'].replace('T', ' ')
            dl = datetime.strptime(dl_str[:16], '%Y-%m-%d %H:%M')
            late = datetime.now() > dl
        except (ValueError, TypeError):
            pass

    ai_results = grade_text_answers_by_ai(text_items)
    ai_score_total = choice_score
    for it in text_items:
        qid = it['question_id']
        r = ai_results.get(qid, {'score': 0, 'feedback': 'AI 暂未批改，请等待老师人工批改'})
        sc = max(r['score'], 0)
        if it['max_score']:
            sc = min(sc, it['max_score'])
        graded_answers[qid] = {'answer': graded_answers[qid]['answer'],
                               'score': round(sc, 1), 'ai_feedback': r['feedback']}
        ai_score_total += sc

    submissions = load_homework_submissions()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    existing = next((s for s in submissions
                     if s.get('homework_id') == hw_id and s.get('student_no') == student_no), None)
    record = {
        'id': existing['id'] if existing else (max([s.get('id', 0) for s in submissions] + [0]) + 1),
        'homework_id': hw_id,
        'student_no': student_no,
        'student_name': session.get('student_name', ''),
        'class_name': current_class,
        'submitted_at': now_str,
        'late': late,
        'answers': graded_answers,
        'choice_score': round(choice_score, 1),
        'ai_score_total': round(ai_score_total, 1),
        'teacher_comment': '',
        'teacher_score_override': None,
    }
    if existing:
        submissions[submissions.index(existing)] = record
    else:
        submissions.append(record)
    save_homework_submissions(submissions)
    # 作业分数反哺能力画像
    try:
        _update_competence_from_homework(student_no, hw, record)
    except Exception as e:
        print(f"[作业反哺能力画像] 失败（不影响提交）: {e}")

    return jsonify({'success': True, 'homework': hw, 'submission': record})


@app.route('/api/homework/<int:hw_id>/submissions', methods=['GET'])
def api_homework_submissions(hw_id):
    """教师查看某作业的完成情况（已交/未交名单+分数）"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可查看'}), 403
    hw = next((h for h in load_homework() if h.get('id') == hw_id), None)
    if not hw:
        return jsonify({'error': '作业不存在'}), 404

    subs = [s for s in load_homework_submissions() if s.get('homework_id') == hw_id]
    students = load_students()
    roster = []
    seen_nos = set()
    for cname in hw.get('class_names', []):
        for s in students:
            if s.get('class_name') != cname:
                continue
            no = s.get('student_no')
            seen_nos.add(no)
            sub = next((x for x in subs if x.get('student_no') == no), None)
            roster.append({
                'student_no': no,
                'student_name': s.get('name'),
                'class_name': cname,
                'submitted': bool(sub),
                'submitted_at': sub.get('submitted_at') if sub else None,
                'late': sub.get('late', False) if sub else False,
                'score': _final_submission_score(sub) if sub else None,
                'has_teacher_comment': bool(sub.get('teacher_comment')) if sub else False,
            })
    # 兼容：已提交但档案不在该班名单中的学生（历史档案班级为空等），以提交记录补入
    for sub in subs:
        no = sub.get('student_no')
        if no in seen_nos or sub.get('class_name') not in hw.get('class_names', []):
            continue
        seen_nos.add(no)
        roster.append({
            'student_no': no,
            'student_name': sub.get('student_name'),
            'class_name': sub.get('class_name'),
            'submitted': True,
            'submitted_at': sub.get('submitted_at'),
            'late': sub.get('late', False),
            'score': _final_submission_score(sub),
            'has_teacher_comment': bool(sub.get('teacher_comment')),
        })
    return jsonify({'success': True, 'homework': hw, 'roster': roster})


@app.route('/api/homework/<int:hw_id>/submission/<student_no>', methods=['GET'])
def api_homework_one_submission(hw_id, student_no):
    """教师查看单个学生作答详情"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可查看'}), 403
    hw = next((h for h in load_homework() if h.get('id') == hw_id), None)
    if not hw:
        return jsonify({'error': '作业不存在'}), 404
    sub = next((s for s in load_homework_submissions()
                if s.get('homework_id') == hw_id and s.get('student_no') == student_no), None)
    if not sub:
        return jsonify({'error': '该学生尚未提交'}), 404
    return jsonify({'success': True, 'homework': hw, 'submission': sub})


@app.route('/api/homework/submission/<int:sub_id>/comment', methods=['POST'])
def api_homework_teacher_comment(sub_id):
    """教师保存批改建议/覆盖总分"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    data = request.get_json() or {}
    comment = (data.get('teacher_comment') or '').strip()
    override = data.get('teacher_score_override')
    if override is not None and str(override).strip() != '':
        try:
            override = float(override)
        except (TypeError, ValueError):
            return jsonify({'error': '分数必须是数字'}), 400
    else:
        override = None
    submissions = load_homework_submissions()
    sub = next((s for s in submissions if s.get('id') == sub_id), None)
    if not sub:
        return jsonify({'error': '提交记录不存在'}), 404
    sub['teacher_comment'] = comment
    sub['teacher_score_override'] = override
    sub['teacher_reviewed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_homework_submissions(submissions)
    return jsonify({'success': True, 'submission': sub})


# ====================== 岗位匹配引擎模块 ======================

def _update_competence_from_homework(student_no: str, hw: Dict, submission: Dict):
    """作业提交后，将有competence_dim的题目得分反哺到学生能力画像"""
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return
    if 'competence_analysis' not in student:
        student['competence_analysis'] = {a['id']: {'count': 0, 'score': 0.0} for a in COMPETENCE_AREAS}

    answers = submission.get('answers', {})
    questions = {q['id']: q for q in hw.get('questions', [])}
    updated = False
    for qid, ans in answers.items():
        q = questions.get(qid)
        if not q or not q.get('competence_dim'):
            continue
        dim = q['competence_dim']
        if dim not in student['competence_analysis']:
            continue
        max_score = q.get('score', 10)
        got_score = ans.get('score', 0)
        rate = (got_score / max_score * 100) if max_score > 0 else 0
        area_data = student['competence_analysis'][dim]
        area_data['count'] += 1
        current = area_data['score']
        area_data['score'] = round((current * (area_data['count'] - 1) + rate) / area_data['count'], 2)
        updated = True
    if updated:
        save_students(students)


def _match_dimensions_by_text(text: str) -> List[str]:
    """用关键词把文本匹配到能力维度，返回命中的维度ID列表"""
    if not text:
        return []
    text = str(text).lower()
    matched = []
    for dim_id, keywords in COMPETENCE_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            matched.append(dim_id)
    return matched


def _get_wrong_question_competence(student_no: str) -> Dict:
    """错题本反哺：薄弱点扣分、已掌握回补，返回各维度错题掌握分(0-100)"""
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return {'scores': {}, 'total_wrong': 0, 'mastered_rate': 0.0}
    student_name = student.get('name', '')
    wrong_list = load_wrong_questions()
    # 按维度聚合：{dim_id: {'wrong_count': N, 'mastered_count': M}}
    dim_stats = {}
    for wq in wrong_list:
        if wq.get('student_name') != student_name:
            continue
        text = f"{wq.get('knowledge_point', '')} {wq.get('question', '')}"
        dims = _match_dimensions_by_text(text)
        if not dims:
            continue
        count = wq.get('count', 1)
        mastered = wq.get('mastered', False)
        for dim_id in dims:
            stat = dim_stats.setdefault(dim_id, {'wrong_count': 0, 'mastered_count': 0})
            stat['wrong_count'] += count
            if mastered:
                stat['mastered_count'] += count
    scores = {}
    total_wrong = 0
    total_mastered = 0
    for dim_id, stat in dim_stats.items():
        wrong = stat['wrong_count']
        mastered = stat['mastered_count']
        total_wrong += wrong
        total_mastered += mastered
        # 未掌握的错题扣分：每条扣15分，最多扣到0
        unmastered = wrong - mastered
        penalty = min(100, unmastered * 15)
        scores[dim_id] = round(max(0, 100 - penalty), 1)
    mastered_rate = round(total_mastered / total_wrong, 2) if total_wrong > 0 else 0.0
    return {'scores': scores, 'total_wrong': total_wrong, 'mastered_rate': mastered_rate}


def _get_interview_competence(student_no: str) -> Dict:
    """AI模拟面试表现：competence_scores直接映射，总分映射到综合素质维度"""
    records = load_interview_records()
    completed = [r for r in records if r.get('student_no') == student_no and r.get('status') == 'completed']
    if not completed:
        return {'scores': {}, 'avg_score': 0, 'count': 0}
    dim_scores_sum = {}
    dim_scores_cnt = {}
    total_score_sum = 0
    valid_dims = {a['id'] for a in COMPETENCE_AREAS}
    for r in completed:
        comp_scores = r.get('competence_scores') or {}
        for dim_id, s in comp_scores.items():
            if dim_id in valid_dims:
                dim_scores_sum[dim_id] = dim_scores_sum.get(dim_id, 0) + float(s)
                dim_scores_cnt[dim_id] = dim_scores_cnt.get(dim_id, 0) + 1
        score = r.get('score')
        if score is not None:
            total_score_sum += float(score)
    scores = {}
    for dim_id, total in dim_scores_sum.items():
        scores[dim_id] = round(total / dim_scores_cnt[dim_id], 1)
    avg_score = round(total_score_sum / len(completed), 1) if completed else 0
    # 面试总分给综合素质维度兜底（表达能力、思维能力）
    if avg_score > 0:
        for dim_id in ['teamwork', 'innovation']:
            if dim_id not in scores:
                scores[dim_id] = avg_score
    return {'scores': scores, 'avg_score': avg_score, 'count': len(completed)}


def _get_learning_behavior_score(student_no: str) -> Dict:
    """学习行为分析：基于错题本的知识点覆盖广度+已掌握率，反映学习投入度"""
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return {'score': 0, 'coverage': 0, 'mastered_rate': 0.0}
    student_name = student.get('name', '')
    wrong_list = load_wrong_questions()
    kp_set = set()
    mastered_kp = set()
    for wq in wrong_list:
        if wq.get('student_name') != student_name:
            continue
        kp = wq.get('knowledge_point', '')
        if kp:
            kp_set.add(kp)
            if wq.get('mastered', False):
                mastered_kp.add(kp)
    # 覆盖广度：覆盖的知识点数量（上限8个得满分）
    coverage = min(100, len(kp_set) / 8 * 100)
    mastered_rate = len(mastered_kp) / len(kp_set) if kp_set else 0.0
    # 综合学习投入度 = 覆盖广度(60%) + 掌握率(40%)
    score = round(coverage * 0.6 + mastered_rate * 100 * 0.4, 1)
    return {'score': score, 'coverage': round(coverage, 1), 'mastered_rate': round(mastered_rate, 2)}


def _parse_job_competence(job_dict: Dict) -> Dict:
    """AI解析岗位JD为12维度能力权重（非流式调用）"""
    title = job_dict.get('title', '')
    desc = (job_dict.get('description') or '')[:500]
    req = (job_dict.get('requirements') or '')[:500]
    skills = ', '.join(job_dict.get('skills', [])[:10])
    dim_list = '\n'.join(f'{i+1}. {a["id"]} - {a["name"]}' for i, a in enumerate(COMPETENCE_AREAS))
    sys_prompt = (
        "你是通信工程岗位分析师。根据岗位描述，分析该岗位对通信工程学生12个能力维度的要求权重（0到1之间，0=不需要，1=极高要求）。\n"
        f"12个维度：\n{dim_list}\n\n"
        "严格只返回JSON，不要输出额外文字或markdown代码块，格式：\n"
        '{"competence_weights": {"signal_system": 0.8, "communication_principle": 0.9}, '
        '"required_skills": ["5G", "射频"], "career_type": "研发", "difficulty": "中高级"}'
    )
    user_prompt = (
        f"岗位标题：{title}\n岗位描述：{desc}\n任职要求：{req}\n技能标签：{skills}\n请分析并返回JSON。"
    )
    try:
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL_FLASH,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1000,
                "stream": False,
                "enable_thinking": False,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"AI HTTP {resp.status_code}")
        content = resp.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(m.group(0) if m else content)
        weights = parsed.get('competence_weights', {})
        for area in COMPETENCE_AREAS:
            if area['id'] not in weights:
                weights[area['id']] = 0.0
            try:
                weights[area['id']] = max(0.0, min(1.0, float(weights[area['id']])))
            except (TypeError, ValueError):
                weights[area['id']] = 0.0
        return {
            'competence_weights': weights,
            'required_skills': parsed.get('required_skills', []),
            'career_type': parsed.get('career_type', ''),
            'difficulty': parsed.get('difficulty', ''),
        }
    except Exception as e:
        print(f"[岗位能力解析] 失败: {e}")
        return None


def _get_student_competence_vector(student_no: str) -> Dict:
    """获取学生融合能力向量：作业(35%) + 错题掌握(25%) + 面试(15%) + 学习行为(10%) + 自评(15%)"""
    student = next((s for s in load_students() if s.get('student_no') == student_no), None)
    if not student:
        return {'vector': {}, 'has_self_assessment': False, 'data_dimensions': 0,
                'projects': [], 'certifications': [], 'internship': None}
    ca = student.get('competence_analysis', {})
    sa = load_self_assessment().get(student_no, {})
    self_rating = sa.get('self_rating', {})
    # 多数据源
    wq_result = _get_wrong_question_competence(student_no)
    wq_scores = wq_result['scores']
    interview_result = _get_interview_competence(student_no)
    interview_scores = interview_result['scores']
    behavior_result = _get_learning_behavior_score(student_no)
    behavior_score = behavior_result['score']

    vector = {}
    for area in COMPETENCE_AREAS:
        aid = area['id']
        hw_score = ca.get(aid, {}).get('score', 0.0)
        hw_count = ca.get(aid, {}).get('count', 0)
        rating = self_rating.get(aid, 0)
        self_score = (float(rating) / 5 * 100) if rating else 0
        wq_score = wq_scores.get(aid, 0.0)
        iv_score = interview_scores.get(aid, 0.0)
        # 仅纳入有数据的数据源，权重按比例归一化
        sources = []
        if hw_count > 0:
            sources.append((hw_score, 0.35))
        if wq_score > 0 or aid in wq_scores:
            sources.append((wq_score, 0.25))
        if iv_score > 0:
            sources.append((iv_score, 0.15))
        if behavior_score > 0:
            sources.append((behavior_score, 0.10))
        if rating:
            sources.append((self_score, 0.15))
        if sources:
            total_w = sum(w for _, w in sources)
            vector[aid] = round(sum(s * w for s, w in sources) / total_w, 1)
        else:
            vector[aid] = 0.0
    return {
        'vector': vector,
        'has_self_assessment': bool(sa),
        'data_dimensions': sum(1 for v in vector.values() if v > 0),
        'projects': sa.get('projects', []),
        'certifications': sa.get('certifications', []),
        'internship': sa.get('internship'),
        'data_sources': {
            'homework_dims': sum(1 for a in COMPETENCE_AREAS if ca.get(a['id'], {}).get('count', 0) > 0),
            'wrong_questions': wq_result['total_wrong'],
            'interview_count': interview_result['count'],
            'learning_behavior': behavior_result['score'],
            'self_assessment_dims': len(self_rating),
        },
    }


def _calculate_match_score(student_vector: Dict, job_weights: Dict) -> tuple:
    """算法匹配度计算（无AI调用，即时返回）"""
    total_weight = sum(job_weights.values())
    if total_weight == 0:
        return 0, [], [], 0
    weighted_score = sum(student_vector.get(d, 0) * w for d, w in job_weights.items())
    match_pct = (weighted_score / (total_weight * 100)) * 100
    # 差距维度
    gaps = []
    for d, w in job_weights.items():
        if w > 0:
            needed = w * 100
            have = student_vector.get(d, 0)
            gap = needed - have
            if gap > 0:
                gaps.append({'dim': d, 'gap': round(gap, 1), 'have': round(have, 1), 'needed': round(needed, 1)})
    gaps.sort(key=lambda x: -x['gap'])
    # 优势维度
    strengths = []
    for d, w in job_weights.items():
        if w > 0:
            needed = w * 100
            have = student_vector.get(d, 0)
            if have >= needed:
                strengths.append({'dim': d, 'have': round(have, 1), 'needed': round(needed, 1)})
    strengths.sort(key=lambda x: -x['have'])
    # 置信度
    job_dims = [d for d, w in job_weights.items() if w > 0]
    student_dims = [d for d in job_dims if student_vector.get(d, 0) > 0]
    confidence = (len(student_dims) / len(job_dims) * 100) if job_dims else 0
    return round(match_pct, 1), gaps[:3], strengths[:3], round(confidence, 1)


@app.route('/job-match-page')
def job_match_page():
    """岗位匹配页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('job_match.html')


@app.route('/api/career-match', methods=['GET'])
def api_career_match():
    """获取岗位列表+算法匹配分"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'error': '招聘模块未加载', 'jobs': []}), 503

    student_no = session.get('student_no', '')
    comp = _get_student_competence_vector(student_no)
    sv = comp['vector']
    jobs = job_crawler.load_job_recruitments()
    result = []
    for job in jobs[:100]:
        weights = job.get('competence_weights')
        if not weights:
            match_pct, gaps, strengths, confidence = 0, [], [], 0
            parsed = False
        else:
            match_pct, gaps, strengths, confidence = _calculate_match_score(sv, weights)
            parsed = True
        result.append({
            'id': job.get('id'),
            'title': job.get('title'),
            'company': job.get('company'),
            'location': job.get('location'),
            'salary': job.get('salary'),
            'education': job.get('education'),
            'experience': job.get('experience'),
            'match_pct': match_pct,
            'confidence': confidence,
            'gaps': gaps,
            'strengths': strengths,
            'parsed': parsed,
            'career_type': job.get('career_type', ''),
            'difficulty': job.get('difficulty', ''),
            'source': job.get('source', ''),
        })
    result.sort(key=lambda x: -x.get('match_pct', 0))
    return jsonify({
        'success': True,
        'jobs': result,
        'student_profile': comp,
        'dim_names': {a['id']: a['name'] for a in COMPETENCE_AREAS},
    })


@app.route('/api/career-match/<job_id>/analysis', methods=['GET'])
def api_career_match_analysis(job_id):
    """AI流式深度分析单个岗位匹配"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'error': '招聘模块未加载'}), 503
    if session.get('role') != 'student':
        return jsonify({'error': '仅学生可使用匹配分析'}), 403

    jobs = job_crawler.load_job_recruitments()
    job = next((j for j in jobs if str(j.get('id')) == str(job_id)), None)
    if not job:
        return jsonify({'error': '岗位不存在'}), 404

    student_no = session.get('student_no', '')
    comp = _get_student_competence_vector(student_no)
    sv = comp['vector']
    weights = job.get('competence_weights', {})
    match_pct, gaps, strengths, confidence = _calculate_match_score(sv, weights)

    dim_names = {a['id']: a['name'] for a in COMPETENCE_AREAS}
    student_dims = '\n'.join(f'{dim_names[d]}: {sv.get(d, 0):.1f}/100' for d in dim_names)
    job_dims = '\n'.join(f'{dim_names[d]}: 权重{weights.get(d, 0):.1f}' for d in dim_names if weights.get(d, 0) > 0)
    gap_desc = '\n'.join(f'{dim_names[g["dim"]]}: 学生{g["have"]}/岗位需{g["needed"]}' for g in gaps)
    strength_desc = '\n'.join(f'{dim_names[s["dim"]]}: 学生{s["have"]}/岗位需{s["needed"]}' for s in strengths)

    system_content = (
        "你是通信工程职业顾问。根据学生能力画像和岗位要求，给出深度匹配分析报告。\n"
        "报告包含四个部分：\n"
        "1. 整体匹配度评估（高/中/低 + 一句话理由，算法匹配度已给出供参考）\n"
        "2. 三大优势（学生强于岗位要求的维度，解释为什么是优势）\n"
        "3. 三大差距（学生弱于岗位要求的维度 + 具体补足建议）\n"
        "4. 职业发展路径建议（这个岗位的发展方向 + 需要准备什么）\n\n"
        "用Markdown格式输出，## 用于标题，### 用于子标题。语言简洁有力。"
    )
    prompt = (
        f"## 学生能力画像\n{student_dims}\n\n"
        f"## 岗位信息\n标题：{job.get('title')}\n公司：{job.get('company')}\n"
        f"地点：{job.get('location')}\n薪资：{job.get('salary')}\n"
        f"学历要求：{job.get('education')}\n经验要求：{job.get('experience')}\n\n"
        f"## 岗位能力权重\n{job_dims}\n\n"
        f"## 算法匹配结果\n匹配度：{match_pct}%\n置信度：{confidence}%\n"
        f"优势维度：{strength_desc or '无明显优势'}\n差距维度：{gap_desc or '无明显差距'}\n\n"
        f"## 学生补充信息\n"
        f"项目经验：{json.dumps(comp.get('projects', []), ensure_ascii=False) if comp.get('projects') else '无'}\n"
        f"证书：{json.dumps(comp.get('certifications', []), ensure_ascii=False) if comp.get('certifications') else '无'}\n"
        f"实习：{json.dumps(comp.get('internship'), ensure_ascii=False) if comp.get('internship') else '无'}\n\n"
        "请给出深度匹配分析报告。"
    )
    return Response(analysis_sse_generator(system_content, prompt, max_tokens=2000, temperature=0.7),
                    content_type='text/event-stream')


@app.route('/api/career-match/parse-competence', methods=['POST'])
def api_career_match_parse_competence():
    """教师批量解析岗位能力权重（分批+即时保存，避免超时丢失进度）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'error': '招聘模块未加载'}), 503

    body = request.get_json(silent=True) or {}
    batch_size = body.get('batch_size', 5)

    jobs = job_crawler.load_job_recruitments()
    parsed_count = 0
    failed_count = 0
    for job in jobs:
        if parsed_count >= batch_size:
            break
        if job.get('competence_weights'):
            continue
        result = _parse_job_competence(job)
        if result:
            job['competence_weights'] = result['competence_weights']
            job['required_skills'] = result.get('required_skills', [])
            job['career_type'] = result.get('career_type', '')
            job['difficulty'] = result.get('difficulty', '')
            parsed_count += 1
        else:
            failed_count += 1
        # 每解析一个立即保存，防止超时丢失进度
        job_crawler.save_job_recruitments(jobs)
    remaining = sum(1 for j in jobs if not j.get('competence_weights'))
    return jsonify({
        'success': True,
        'parsed': parsed_count,
        'failed': failed_count,
        'remaining': remaining,
        'total': len(jobs),
    })


@app.route('/api/student/self-assessment', methods=['GET'])
def api_get_self_assessment():
    """学生查看自评画像"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'student':
        return jsonify({'error': '仅学生可查看自评'}), 403
    student_no = session.get('student_no', '')
    data = load_self_assessment()
    sa = data.get(student_no, {})
    return jsonify({
        'success': True,
        'assessment': sa,
        'dimensions': [{'id': a['id'], 'name': a['name'], 'category': a['category']} for a in COMPETENCE_AREAS],
    })


@app.route('/api/student/self-assessment', methods=['POST'])
def api_save_self_assessment():
    """学生提交自评画像"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'student':
        return jsonify({'error': '仅学生可提交自评'}), 403
    student_no = session.get('student_no', '')
    body = request.get_json() or {}
    data = load_self_assessment()
    data[student_no] = {
        'projects': body.get('projects', []),
        'certifications': body.get('certifications', []),
        'internship': body.get('internship'),
        'self_rating': body.get('self_rating', {}),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    save_self_assessment(data)
    return jsonify({'success': True, 'assessment': data[student_no]})


# ====================== AI模拟面试 + 面试案例知识库模块 ======================

def load_interview_cases() -> List[Dict]:
    """加载面试案例列表"""
    try:
        if os.path.exists(INTERVIEW_CASES_FILE):
            with open(INTERVIEW_CASES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("cases", []) if isinstance(data, dict) else data
    except Exception as e:
        print(f"面试案例加载失败: {e}")
    return []


def save_interview_cases(cases: List[Dict]):
    """保存面试案例"""
    try:
        atomic_save_json(INTERVIEW_CASES_FILE, {"cases": cases})
    except Exception as e:
        print(f"面试案例保存失败: {e}")


def load_interview_records() -> List[Dict]:
    """加载面试记录"""
    try:
        if os.path.exists(INTERVIEW_RECORDS_FILE):
            with open(INTERVIEW_RECORDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("records", []) if isinstance(data, dict) else data
    except Exception as e:
        print(f"面试记录加载失败: {e}")
    return []


def save_interview_records(records: List[Dict]):
    """保存面试记录"""
    try:
        atomic_save_json(INTERVIEW_RECORDS_FILE, {"records": records})
    except Exception as e:
        print(f"面试记录保存失败: {e}")


def _get_cases_for_interview(company: str, position: str, interview_type: str) -> List[Dict]:
    """按企业+岗位+面试类型检索相关案例"""
    cases = load_interview_cases()
    exact = [c for c in cases if c.get('company') == company and c.get('position') == position and c.get('interview_type') == interview_type]
    if exact:
        return exact[:3]
    company_type = [c for c in cases if c.get('company') == company and c.get('interview_type') == interview_type]
    if company_type:
        return company_type[:3]
    type_only = [c for c in cases if c.get('interview_type') == interview_type]
    if type_only:
        return type_only[:3]
    return cases[:3]


def _build_interviewer_system_prompt(student_name, company, position, interview_type, difficulty, competence_vector, student_extras, case_questions):
    """构建面试官system prompt"""
    dim_lines = []
    for area in COMPETENCE_AREAS:
        aid = area['id']
        score = competence_vector.get(aid, 0)
        if score > 0:
            dim_lines.append(f"- {area['name']}：{score}/100")
    comp_text = '\n'.join(dim_lines) if dim_lines else "（暂无能力数据）"

    extras_lines = []
    projects = student_extras.get('projects', [])
    if projects:
        extras_lines.append(f"项目经历：{json.dumps(projects, ensure_ascii=False)[:300]}")
    certs = student_extras.get('certifications', [])
    if certs:
        extras_lines.append(f"证书：{json.dumps(certs, ensure_ascii=False)[:200]}")
    internship = student_extras.get('internship')
    if internship:
        extras_lines.append(f"实习经历：{json.dumps(internship, ensure_ascii=False)[:200]}")
    extras_text = '\n'.join(extras_lines) if extras_lines else "（无额外信息）"

    case_text = ""
    if case_questions:
        for i, cq in enumerate(case_questions[:10], 1):
            q = cq.get('question', '')
            kp = cq.get('key_points', [])
            case_text += f"\n{i}. {q}\n   考察要点：{', '.join(kp) if kp else '无'}"

    if interview_type == 'HR面':
        focus = "请侧重考察综合素质：团队协作、沟通表达、职业规划、抗压能力、责任心等，不涉及具体技术细节。"
    elif interview_type == '综合面':
        focus = "请综合考察技术能力和综合素质，既问技术问题也关注职业素养。"
    else:
        focus = "请侧重考察通信工程专业知识和工程实践能力。"

    return f"""你是【{company}】的【{position}】岗位面试官，正在进行一场【{interview_type}】模拟面试。

【面试规则】
1. 你是面试官，对方是通信工程专业学生【{student_name}】，请以面试官口吻对话。
2. 每次只提一个问题，等待对方回答后再追问或换题。
3. 根据对方回答质量决定：回答良好→追问更深层次问题；回答不足→换一个方向的新题。
4. 面试难度等级：【{difficulty}】。简单=基础概念；中等=原理+应用；困难=综合分析+工程实践。
5. 保持专业、友好的语气，适当给予鼓励但不要透露参考答案。
6. 当对话达到约8轮（学生回答8次）时，总结面试并告知结束。
7. {focus}

【候选人能力画像】
{comp_text}

【候选人附加信息】
{extras_text}

【参考题库】（从知识库检索，可灵活使用但不要照搬）
{case_text if case_text else "（无参考题库，请根据岗位要求自行出题）"}

【面试方向引导】
请根据候选人能力画像，优先考察其薄弱维度相关的知识点，同时验证其优势维度是否名副其实。
面试开始时，请先做一个简短的开场介绍（不超过100字），然后提出第一个问题。"""


def _build_scoring_prompt(interview_messages, company, position, interview_type, case_questions, competence_vector):
    """构建评分system+user prompt"""
    dialog_lines = []
    for msg in interview_messages:
        role = msg.get('role', '')
        content = msg.get('content', '')
        if role == 'interviewer':
            dialog_lines.append(f"面试官：{content}")
        elif role == 'student':
            dialog_lines.append(f"学生：{content}")
    dialog_text = '\n'.join(dialog_lines)

    ref_text = ""
    if case_questions:
        for i, cq in enumerate(case_questions[:5], 1):
            q = cq.get('question', '')
            a = cq.get('reference_answer', '')[:150]
            kp = cq.get('key_points', [])
            ref_text += f"\n题目{i}：{q}\n参考答案要点：{', '.join(kp) if kp else '无'}\n参考答案：{a}\n"

    dim_text = '\n'.join(f"- {a['id']}({a['name']})" for a in COMPETENCE_AREAS)

    system_prompt = f"""你是通信工程专业面试评审专家。请根据以下模拟面试对话记录，给出结构化评分。

【评分维度】
请对以下能力维度各打0-100分（仅对面试中实际考察到的维度打分，未考察的维度填0）：
{dim_text}

【输出格式要求】
严格只返回JSON（不要markdown代码块，不要多余文字）：
{{"score": 78, "competence_scores": {{"communication_principle": 80}}, "strengths": ["优势1"], "weaknesses": ["不足1"], "suggestions": ["建议1", "建议2"], "report": "200-300字综合评语"}}

【评分标准】
- 90-100：回答准确深入，有工程实践经验
- 75-89：回答正确但深度不足
- 60-74：基本概念掌握但有明显错误
- 60以下：核心概念未掌握

【参考答案要点】
{ref_text if ref_text else "（无参考答案）"}"""

    user_prompt = f"""岗位：{company} - {position}（{interview_type}）

【面试对话记录】
{dialog_text}

请给出评分结果。"""

    return system_prompt, user_prompt


SEED_INTERVIEW_CASES = [
    {"id": "case_huawei_001", "company": "华为", "position": "无线网络优化工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "华为无线网络优化工程师技术面试，考察5G/LTE网络优化能力",
     "questions": [
         {"question": "请解释5G NR与LTE在空口技术上的主要区别", "reference_answer": "5G NR采用灵活numerology设计，子载波间隔可变(15/30/60/120kHz)，支持mini-slot；LTE固定15kHz。NR使用LDPC编码数据信道、Polar编码控制信道，LTE用Turbo码。NR支持 Massive MIMO和波束赋形。", "key_points": ["numerology", "子载波间隔", "LDPC/Polar编码", "Massive MIMO", "波束赋形"], "competence_areas": ["communication_principle", "modulation"]},
         {"question": "在5G网络优化中，如何定位和解决覆盖空洞问题？", "reference_answer": "通过MR数据采集分析RSRP/RS-SINR分布，结合路测和数字地图识别弱覆盖区域。解决方案：调整天线方位角/下倾角、增加扇区功率、新增小微基站或室分系统、优化PCI规划减少模3干扰。", "key_points": ["MR数据", "RSRP", "RS-SINR", "PCI规划", "功率调整"], "competence_areas": ["troubleshooting", "rf_engineering"]},
         {"question": "请简述LTE中ICIC技术的作用和原理", "reference_answer": "ICIC（小区间干扰协调）通过小区间交互频域资源使用信息，协调各小区的频谱资源分配，边缘用户使用正交频段减少同频干扰。分为静态/半静态/动态ICIC。", "key_points": ["频域协调", "边缘用户", "同频干扰", "X2接口", "RNTP"], "competence_areas": ["communication_principle"]}
     ], "tags": ["5G", "LTE", "网络优化"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_huawei_002", "company": "华为", "position": "射频工程师", "interview_type": "技术面", "difficulty": "困难",
     "description": "华为射频工程师技术面试，考察射频电路设计和调试能力",
     "questions": [
         {"question": "请详细解释功率放大器的非线性失真及其改善方法", "reference_answer": "PA非线性导致AM-AM和AM-PM失真，产生谐波和交调产物(ACLR恶化)。改善方法：DPD数字预失真、Doherty架构提升效率、包络跟踪(ET)技术、回退功率。需要权衡线性化与效率的trade-off。", "key_points": ["AM-AM失真", "ACLR", "DPD预失真", "Doherty架构", "包络跟踪"], "competence_areas": ["rf_engineering", "modulation"]},
         {"question": "射频阻抗匹配有哪些方法？Smith圆图如何辅助匹配设计？", "reference_answer": "匹配方法：L型/π型/T型匹配网络、单短截线/双短截线匹配、变压器匹配。Smith圆图可直观显示阻抗归一化值，通过在圆图上移动找到匹配元件参数值，导纳圆图辅助并联匹配设计。", "key_points": ["阻抗匹配", "Smith圆图", "L型网络", "短截线匹配", "归一化阻抗"], "competence_areas": ["rf_engineering"]},
         {"question": "请解释低噪声放大器(LNA)的设计要点和噪声系数优化", "reference_answer": "LNA设计要点：低噪声系数(首级决定系统NF)、足够增益(抑制后级噪声)、高线性度(避免交调)、良好50Ω匹配。NF优化：选择低噪声器件(HEMT/pHEMT)、最佳偏置点、输入匹配在噪声圆与增益圆之间折中、PCB布局减少寄生。", "key_points": ["噪声系数", "低噪声器件", "偏置优化", "输入匹配", "寄生参数"], "competence_areas": ["rf_engineering"]}
     ], "tags": ["射频", "功率放大器", "LNA", "阻抗匹配"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_huawei_003", "company": "华为", "position": "通信协议开发工程师", "interview_type": "技术面", "difficulty": "困难",
     "description": "华为通信协议开发工程师技术面试，考察3GPP协议栈和开发能力",
     "questions": [
         {"question": "请描述5G NAS层和RRC层的功能区别", "reference_answer": "NAS层负责核心网相关功能：注册管理、连接管理、会话管理、移动性管理(AMF)。RRC层负责接入网控制：广播、寻呼、RRC连接建立/释放、无线承载配置、移动性(切换)。NAS消息通过RRC透传。", "key_points": ["NAS层", "RRC层", "AMF", "无线承载", "切换"], "competence_areas": ["network_protocol"]},
         {"question": "3GPP协议中MAC层HARQ机制如何工作？", "reference_answer": "HARQ在MAC层实现，结合FEC和ARQ。下行异步HARQ：基站通过PDCCH调度重传，UE反馈ACK/NACK。上行同步HARQ：固定时序关系。HARQ进程支持多个并行(下行最大16进程)，采用CC( Chase Combining)或IR(Incremental Redundancy)合并。", "key_points": ["HARQ", "异步/同步", "CC/IR合并", "ACK/NACK", "多进程"], "competence_areas": ["network_protocol", "communication_principle"]}
     ], "tags": ["3GPP", "协议栈", "RRC", "HARQ"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_huawei_004", "company": "华为", "position": "无线网络优化工程师", "interview_type": "HR面", "difficulty": "中等",
     "description": "华为无线网络优化工程师HR面试，考察综合素质",
     "questions": [
         {"question": "请做一个简短的自我介绍，包括你的专业背景和职业规划", "reference_answer": "结构化表达：姓名+学校+专业方向+核心项目/实习经历+求职动机+职业规划。控制在2-3分钟，突出与岗位匹配的优势。", "key_points": ["结构化表达", "时间控制", "突出匹配", "职业规划"], "competence_areas": ["teamwork"]},
         {"question": "如果你和同事在技术方案上产生分歧，你会如何处理？", "reference_answer": "先倾听对方观点，找到分歧点；用数据和实验验证而非主观判断；寻求第三方专家意见；若无法达成一致则按上级决策执行并保留建议。体现沟通能力和团队协作意识。", "key_points": ["倾听", "数据驱动", "寻求共识", "尊重决策"], "competence_areas": ["teamwork", "innovation"]}
     ], "tags": ["HR面", "自我介绍", "团队协作"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_zte_001", "company": "中兴", "position": "基站研发工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "中兴基站研发工程师技术面试",
     "questions": [
         {"question": "请简述5G基站的BBU和AAU/RRU架构演进", "reference_answer": "传统D-RAN：BBU+RRU通过CPRI光纤连接。5G C-RAN：CU-DU分离架构，CU集中部署，DU分布式。AAU集成天线+射频，前传接口从CPRI演进到eCPRI，支持功能灵活分割。", "key_points": ["BBU/RRU", "CU-DU分离", "AAU", "eCPRI", "前传接口"], "competence_areas": ["equipment_operation", "communication_principle"]},
         {"question": " Massive MIMO的预编码技术有哪些？各自优缺点？", "reference_answer": "数字预编码：精度高但复杂度大、成本高；模拟预编码：低成本但只支持单流；混合预编码：折中方案，基带数字+RF模拟两阶段预编码，兼顾性能和复杂度。", "key_points": ["数字预编码", "模拟预编码", "混合预编码", "复杂度"], "competence_areas": ["modulation", "antenna_design"]},
         {"question": "基站天线端口功率如何分配和管理？", "reference_answer": "通过BBU配置参考信号功率(CRS/DMRS)，按端口分配功率(2port/4port/8port)。使用功率平衡：确保各端口输出功率一致，通过VSWR监测和ALC自动功率控制保护功放。", "key_points": ["参考信号功率", "端口配置", "VSWR", "ALC"], "competence_areas": ["rf_engineering", "equipment_operation"]}
     ], "tags": ["基站", "BBU", "MIMO", "天线"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_zte_002", "company": "中兴", "position": "传输网工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "中兴传输网工程师技术面试",
     "questions": [
         {"question": "请比较OTN和PTN技术的应用场景和区别", "reference_answer": "OTN(光传送网)：面向大颗粒业务，DWDM波分复用，适合骨干/城域核心。PTN(分组传送网)：面向IP化小颗粒业务，MPLS-TP，适合城域接入/回传。OTN强在带宽和可靠性，PTN强在灵活统计复用。", "key_points": ["OTN", "PTN", "波分复用", "MPLS-TP", "应用场景"], "competence_areas": ["network_protocol", "equipment_operation"]},
         {"question": "SDH的STM-N帧结构是怎样的？段开销有什么作用？", "reference_answer": "STM-N帧：9行×270N列，含段开销(SOH)、管理单元指针(AU-PTR)、信息净荷(Payload)。SOH含RSOH(再生段开销)和MSOH(复用段开销)，用于OAM功能：性能监测、故障定位、保护倒换。", "key_points": ["STM-N帧", "段开销", "AU指针", "净荷", "OAM"], "competence_areas": ["network_protocol"]}
     ], "tags": ["OTN", "PTN", "SDH", "传输网"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_zte_003", "company": "中兴", "position": "核心网工程师", "interview_type": "技术面", "difficulty": "困难",
     "description": "中兴核心网工程师技术面试",
     "questions": [
         {"question": "请描述5G核心网(5GC)的服务化架构和主要网元功能", "reference_answer": "5GC采用SBA服务化架构，主要网元：AMF(接入和移动性管理)、SMF(会话管理)、UPF(用户面)、PCF(策略控制)、UDM(统一数据管理)、AUSF(认证)、NRF(网络存储库)、NSSF(切片选择)。接口以HTTP/2 API实现服务化通信。", "key_points": ["SBA架构", "AMF/SMF/UPF", "服务化接口", "NRF", "网络切片"], "competence_areas": ["network_protocol"]},
         {"question": "5G网络切片如何实现？端到端切片包含哪些维度？", "reference_answer": "切片通过NSSAI标识，包含：RAN切片(无线资源隔离)、TN切片(传输网VPN隔离)、CN切片(核心网NF实例隔离)。按eMBB/URLLC/mMTC三大场景定制。通过NSSF选择切片，PCF下发策略，端到端QoS保障。", "key_points": ["NSSAI", "RAN/TN/CN切片", "NSSF", "eMBB/URLLC/mMTC", "QoS"], "competence_areas": ["network_protocol", "innovation"]}
     ], "tags": ["5GC", "核心网", "SBA", "网络切片"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_zte_004", "company": "中兴", "position": "基站研发工程师", "interview_type": "HR面", "difficulty": "简单",
     "description": "中兴基站研发工程师HR面试",
     "questions": [
         {"question": "你为什么选择中兴？对我们公司有什么了解？", "reference_answer": "展示对公司业务(通信设备、5G)、企业文化(狼性文化)、行业地位的了解。结合个人发展需求说明匹配度。避免泛泛而谈，体现做过调研。", "key_points": ["公司调研", "业务了解", "文化匹配", "职业发展"], "competence_areas": ["teamwork"]},
         {"question": "描述一个你在项目中遇到的最大困难和解决过程", "reference_answer": "STAR法则：Situation(背景)、Task(任务)、Action(行动)、Result(结果)。选择有挑战性的技术问题，展示分析问题和解决问题的能力。", "key_points": ["STAR法则", "技术挑战", "解决过程", "结果量化"], "competence_areas": ["troubleshooting", "teamwork"]}
     ], "tags": ["HR面", "中兴", "STAR法则"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_datang_001", "company": "大唐移动", "position": "无线接入工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "大唐移动无线接入工程师技术面试",
     "questions": [
         {"question": "请解释OFDM正交性的原理和循环前缀(CP)的作用", "reference_answer": "OFDM正交性：子载波间隔Δf=1/T(符号时长)，保证频谱零点对齐，子载波间无干扰。CP作用：复制符号尾部到头部，消除ISI(符号间干扰)和ICI(子载波间干扰)，条件是CP长度大于信道最大时延扩展。", "key_points": ["正交性", "子载波间隔", "循环前缀", "ISI", "ICI"], "competence_areas": ["communication_principle", "modulation"]},
         {"question": "QPSK和QAM调制的星座图有什么区别？如何选择？", "reference_answer": "QPSK：4个星座点，每符号2比特，抗干扰强但频谱效率低。16QAM：16点4比特，64QAM：6比特，频谱效率高但要求高SNR。选择依据：信道条件好用高阶QAM，差用低阶。自适应编码调制(AMC)根据CQI动态切换。", "key_points": ["星座图", "频谱效率", "SNR要求", "AMC", "CQI"], "competence_areas": ["modulation"]}
     ], "tags": ["OFDM", "QAM", "调制", "循环前缀"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_datang_002", "company": "大唐移动", "position": "测试工程师", "interview_type": "技术面", "difficulty": "简单",
     "description": "大唐移动测试工程师技术面试",
     "questions": [
         {"question": "频谱分析仪的使用方法和常见测量项有哪些？", "reference_answer": "设置中心频率、RBW/VBW、参考电平、检波方式。常见测量：功率谱密度、占用带宽、ACLR、杂散辐射、谐波。注意RBW影响噪声底和分辨率，VBW影响视频平滑。", "key_points": ["RBW", "VBW", "ACLR", "占用带宽", "杂散辐射"], "competence_areas": ["equipment_operation", "troubleshooting"]},
         {"question": "基站现场开通测试流程包含哪些步骤？", "reference_answer": "1.安装检查(馈线/光纤/电源)；2.上电自检；3.本地维护终端(LMT)配置参数；4.小区激活；5.覆盖测试(路测)；6.业务验证(语音/数据)；7.邻区关系配置；8.入网验收。", "key_points": ["安装检查", "LMT配置", "小区激活", "路测", "入网验收"], "competence_areas": ["equipment_operation", "safety_awareness"]}
     ], "tags": ["测试", "频谱仪", "基站开通"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_cmcc_001", "company": "中国移动", "position": "网络运维工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "中国移动网络运维工程师技术面试",
     "questions": [
         {"question": "如何通过网络KPI指标发现和定位网络问题？", "reference_answer": "关键KPI：接入成功率、掉线率、切换成功率、吞吐量、时延。通过网管系统(如华为U2020)监控指标变化，设定阈值告警。问题定位：从小区级→站点级→区域级逐层分析，结合MR数据、信令跟踪、路测定位根因。", "key_points": ["KPI指标", "接入成功率", "掉线率", "切换成功率", "网管系统"], "competence_areas": ["troubleshooting", "equipment_operation"]},
         {"question": "请描述一个你处理过的网络故障案例或你理解的故障处理流程", "reference_answer": "故障处理流程：1.告警接收与初步判断；2.影响范围评估；3.故障定位(从核心到接入、从硬件到软件)；4.应急处置(倒换/重启/隔离)；5.根因分析；6.修复验证；7.复盘总结。体现系统性思维。", "key_points": ["告警处理", "影响评估", "故障定位", "应急处置", "复盘总结"], "competence_areas": ["troubleshooting"]}
     ], "tags": ["KPI", "网络运维", "故障处理"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_cmcc_002", "company": "中国移动", "position": "网络运维工程师", "interview_type": "HR面", "difficulty": "简单",
     "description": "中国移动网络运维工程师HR面试",
     "questions": [
         {"question": "网络运维岗位需要7×24值班，你如何看待这个问题？", "reference_answer": "表达理解岗位性质(网络运维的特殊性)、适应倒班安排、身体健康管理计划、家庭沟通安排。体现责任心和适应能力。", "key_points": ["值班认知", "责任心", "适应性", "健康管理"], "competence_areas": ["safety_awareness", "teamwork"]},
         {"question": "你觉得自己最大的优点和需要改进的地方是什么？", "reference_answer": "优点：与岗位相关的(学习能力/抗压能力/团队协作)。缺点：真实但非致命(如经验不足正在弥补/追求细节有时耗时)，给出改进措施。", "key_points": ["自我认知", "岗位匹配", "改进措施", "真诚"], "competence_areas": ["teamwork"]}
     ], "tags": ["HR面", "中国移动", "值班", "自我评价"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_ct_001", "company": "中国电信", "position": "宽带接入工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "中国电信宽带接入工程师技术面试",
     "questions": [
         {"question": "PON技术的EPON和GPON有什么区别？目前FTTH常用哪种？", "reference_answer": "EPON：上下行1.25Gbps，线路编码8B/10B，效率低。GPON：下行2.5G/上行1.25G，使用GEM封装，效率高QoS好。目前FTTH主用GPON及演进(10G GPON/XGSPON)。中国电信此前主推EPON，现全面转向GPON/10GPON。", "key_points": ["EPON", "GPON", "GEM封装", "10G PON", "FTTH"], "competence_areas": ["network_protocol", "equipment_operation"]},
         {"question": "用户报障宽带不能上网，排查思路是什么？", "reference_answer": "1.确认故障范围(单用户/多用户)；2.检查ONU注册状态和光功率(收发)；3.查看VLAN/IP分配；4.Ping测试到BRAS；5.检查认证(RADIUS)；6.测速和网页测试。从物理层到应用层逐层排查。", "key_points": ["ONU状态", "光功率", "VLAN", "BRAS", "RADIUS认证"], "competence_areas": ["troubleshooting"]}
     ], "tags": ["PON", "GPON", "FTTH", "宽带接入"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_cucc_001", "company": "中国联通", "position": "数据通信工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "中国联通数据通信工程师技术面试",
     "questions": [
         {"question": "请解释OSPF协议的工作原理和LSA类型", "reference_answer": "OSPF链路状态协议：通过Hello发现邻居→建立邻接→交换DD→LSR/LSU同步LSDB→SPF计算最短路径。LSA类型：Type1 Router-LSA、Type2 Network-LSA、Type3 Summary-LSA(ABR)、Type4 ASBR Summary、Type5 External、Type7 NSSA。", "key_points": ["链路状态", "邻接关系", "LSDB", "SPF算法", "LSA类型"], "competence_areas": ["network_protocol"]},
         {"question": "VPN技术在运营商网络中如何实现？MPLS L3VPN的工作流程？", "reference_answer": "MPLS L3VPN：CE通过PE接入，PE为每个VPN维护VRF路由表。CE→PE走eBGP/OSPF；PE间通过MP-BGP交换VPNv4路由(带RD/RT)；MPLS标签转发。入口PE压入两层标签(VPN标签+LSP标签)，PHP弹出外层。", "key_points": ["VRF", "MP-BGP", "RD/RT", "VPNv4", "标签栈"], "competence_areas": ["network_protocol"]}
     ], "tags": ["OSPF", "MPLS VPN", "数据通信", "路由协议"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_eric_001", "company": "爱立信", "position": "RF Optimization Engineer", "interview_type": "技术面", "difficulty": "困难",
     "description": "爱立信RF Optimization Engineer技术面试(英文)",
     "questions": [
         {"question": "How do you approach RF interference analysis in a dense urban 5G network?", "reference_answer": "Approach: 1. Collect MR/scanner data to identify interference patterns; 2. Analyze PCI collision/confusion (Mod3/Mod6); 3. Check neighbor cell list completeness; 4. Evaluate cross-border interference (TDD special subframe config); 5. Use IRC receiver algorithms; 6. Optimize antenna tilt/azimuth and power; 7. Implement inter-frequency load balancing.", "key_points": ["PCI planning", "Mod3 interference", "IRC receiver", "antenna tilt", "cross-border"], "competence_areas": ["rf_engineering", "troubleshooting"]},
         {"question": "Explain the concept of beam management in 5G NR and how it impacts coverage optimization", "reference_answer": "5G NR beam management: SSB beam sweeping for initial access, CSI-RS beams for fine measurement, PDSCH/PUSCH beam pairing for data. Beam-level coverage optimization: adjust digital beam weights, switch between wide/narrow beams per traffic, monitor beam failure and trigger beam failure recovery (BFR). Impact: precise coverage shaping, higher antenna gain, but more complex optimization vs LTE.", "key_points": ["SSB beam", "CSI-RS beam", "beam pairing", "BFR", "digital weights"], "competence_areas": ["antenna_design", "rf_engineering"]}
     ], "tags": ["5G NR", "RF optimization", "beam management", "interference"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_nokia_001", "company": "诺基亚", "position": "基带工程师", "interview_type": "技术面", "difficulty": "中等",
     "description": "诺基亚基带工程师技术面试",
     "questions": [
         {"question": "FPGA和DSP在通信基带处理中各自的优势和应用场景？", "reference_answer": "FPGA：并行处理能力强，适合高速实时信号处理(FFT/滤波/CRC)、接口处理(前传)。DSP：灵活可编程，适合复杂算法(MIMO检测/信道编译码)。实际系统两者配合：FPGA做前端高速预处理，DSP做后端算法。", "key_points": ["FPGA并行", "DSP可编程", "FFT", "MIMO检测", "分工配合"], "competence_areas": ["digital_signal", "equipment_operation"]},
         {"question": "数字下变频(DDC)的原理和实现步骤？", "reference_answer": "DDC将高频数字信号变到基带：1.数字混频(乘NCO产生的正余弦)；2.CIC抽取滤波(大比例降采样)；3.HB半带滤波(2倍抽取)；4.FIR整形滤波。在FPGA中常用多级抽取降低资源占用。", "key_points": ["数字混频", "NCO", "CIC滤波", "HB滤波", "多级抽取"], "competence_areas": ["digital_signal"]}
     ], "tags": ["FPGA", "DSP", "DDC", "基带处理"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_huawei_005", "company": "华为", "position": "通信协议开发工程师", "interview_type": "HR面", "difficulty": "中等",
     "description": "华为通信协议开发工程师HR面试",
     "questions": [
         {"question": "华为的工作节奏比较快，压力较大，你如何应对工作压力？", "reference_answer": "展示具体方法：时间管理(优先级排序)、情绪调节(运动/倾诉)、技术提升(减少不确定性)、寻求团队支持。避免说'我没压力'这种不真实回答。", "key_points": ["压力管理", "时间管理", "情绪调节", "团队支持"], "competence_areas": ["teamwork"]},
         {"question": "如果分配给你的工作任务不是你感兴趣的，你会怎么办？", "reference_answer": "表达态度：先做好本职工作、从中发现学习价值、主动了解业务背景寻找兴趣点、通过业绩争取更多机会。体现职业素养和积极心态。", "key_points": ["职业素养", "积极心态", "学习价值", "主动争取"], "competence_areas": ["teamwork", "innovation"]}
     ], "tags": ["HR面", "华为", "压力管理", "职业素养"], "created_at": "2026-10-10 10:00:00", "created_by": "system"},

    {"id": "case_cmcc_003", "company": "中国移动", "position": "网络规划工程师", "interview_type": "综合面", "difficulty": "困难",
     "description": "中国移动网络规划工程师综合面试",
     "questions": [
         {"question": "如果你负责一个新城区的5G网络规划，你会从哪些方面入手？", "reference_answer": "1.需求分析(人口密度/业务类型/流量预测)；2.覆盖规划(链路预算/站间距/天线选型)；3.容量规划(小区吞吐量/PRB利用率)；4.频率规划(N3/N78/n41频段/SA/NSA)；5.邻区规划(ANR自动邻区)；6.PCI规划；7.传输规划(IPRAN前传带宽)；8.机房/电源/配套。", "key_points": ["链路预算", "站间距", "容量规划", "频率规划", "PCI规划", "传输规划"], "competence_areas": ["communication_principle", "rf_engineering", "equipment_operation"]},
         {"question": "如何平衡5G网络建设的覆盖和容量？在投资有限的情况下如何取舍？", "reference_answer": "分层覆盖策略：宏站解决连续覆盖(低频段广覆盖)，微站/室分补充热点容量。投资优先级：1.核心商圈/交通枢纽(高价值区域先建)；2.覆盖盲区消除(保障基础服务)；3.容量扩容(按需扩容)。用ROI评估投资效益，结合分期建设策略。", "key_points": ["分层覆盖", "宏微结合", "投资优先级", "ROI", "分期建设"], "competence_areas": ["innovation", "safety_awareness"]}
     ], "tags": ["网络规划", "5G规划", "综合面", "覆盖容量"], "created_at": "2026-10-10 10:00:00", "created_by": "system"}
]


@app.route('/students/<string:student_id>/update-conversation', methods=['POST'])
def update_student_conversation(student_id):
    """更新学生对话记录（用于分析）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    data = request.get_json()
    message = data.get('message', '')
    is_question = data.get('is_question', True)
    
    update_student_profile(student_id, message, is_question)
    return jsonify({'success': True})


@app.route('/student-report-page')
def student_report_page():
    """学生分析报告页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('student_report.html')


@app.route('/class-notification-page')
def class_notification_page():
    """班级管理与通知页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('class_notification.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """下载上传的文件"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    # 处理Windows路径分隔符问题
    filename = filename.replace('/', os.sep).replace('\\', os.sep)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    # 安全检查：确保文件在UPLOAD_FOLDER目录内
    file_path = os.path.abspath(file_path)
    upload_folder_abspath = os.path.abspath(UPLOAD_FOLDER)
    
    if not file_path.startswith(upload_folder_abspath):
        return jsonify({'error': '访问被拒绝'}), 403
    
    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404
    
    # 使用send_file直接发送文件，避免send_from_directory的路径问题
    from flask import send_file
    return send_file(file_path, as_attachment=True)


@app.route('/images/<path:filename>')
def serve_image(filename):
    """内联显示图片（不下载）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    # 处理Windows路径分隔符问题
    filename = filename.replace('/', os.sep).replace('\\', os.sep)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    
    # 安全检查：确保文件在UPLOAD_FOLDER目录内
    file_path = os.path.abspath(file_path)
    upload_folder_abspath = os.path.abspath(UPLOAD_FOLDER)
    
    if not file_path.startswith(upload_folder_abspath):
        return jsonify({'error': '访问被拒绝'}), 403
    
    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404
    
    # 检测文件类型，设置正确的Content-Type
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    content_type = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'bmp': 'image/bmp'
    }.get(ext, 'image/jpeg')
    
    from flask import send_file
    return send_file(file_path, mimetype=content_type)


@app.route('/reload-knowledge', methods=['POST'])
def reload_knowledge():
    """重新加载知识库"""
    global knowledge_content, SYSTEM_PROMPT_FAST, SYSTEM_PROMPT_DEEP
    knowledge_content = load_knowledge()
    
    # 更新提示词
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
    
    return jsonify({'status': 'success', 'message': '知识库已重新加载'})


try:
    from api_public import public_api
    app.register_blueprint(public_api, url_prefix='/api')
    print("公共API模块加载成功")
except ImportError:
    print("公共API模块未加载（可选）")


# ====================== 招聘信息模块 ======================
try:
    import job_crawler
    import job_scheduler
    JOB_MODULE_AVAILABLE = True
    print("招聘信息模块加载成功")
except ImportError as e:
    JOB_MODULE_AVAILABLE = False
    print(f"招聘信息模块加载失败: {e}")


# ====================== 前沿知识更新模块（教学方案模块4） ======================
try:
    import frontier_crawler
    import frontier_scheduler
    FRONTIER_MODULE_AVAILABLE = True
    print("前沿知识更新模块加载成功")
except ImportError as e:
    FRONTIER_MODULE_AVAILABLE = False
    print(f"前沿知识更新模块加载失败: {e}")

# ====================== 哈希链可信成长档案（模块6 能力评价与证书） ======================
try:
    import credential_chain
    CREDENTIAL_MODULE_AVAILABLE = True
    print("哈希链可信成长档案模块加载成功")
except ImportError as e:
    credential_chain = None
    CREDENTIAL_MODULE_AVAILABLE = False
    print(f"哈希链可信成长档案模块加载失败: {e}")

# ====================== 知识库 RAG 向量检索 ======================
try:
    import rag_retriever
    RAG_MODULE_AVAILABLE = True
    print("知识库 RAG 向量检索模块加载成功")
except ImportError as e:
    rag_retriever = None
    RAG_MODULE_AVAILABLE = False
    print(f"知识库 RAG 向量检索模块加载失败: {e}")

# ====================== 安全与隐私合规模块 ======================
try:
    import security
    SECURITY_MODULE_AVAILABLE = True
    print("安全与隐私合规模块加载成功")
except ImportError as e:
    security = None
    SECURITY_MODULE_AVAILABLE = False
    print(f"安全与隐私合规模块加载失败: {e}")

# ====================== 因果故障链 + 难度自适应 ======================
try:
    import fault_chain
    FAULT_CHAIN_AVAILABLE = True
    print("因果故障链模块加载成功")
except ImportError as e:
    fault_chain = None
    FAULT_CHAIN_AVAILABLE = False
    print(f"因果故障链模块加载失败: {e}")

# ====================== 多故障并发优先级决策 ======================
try:
    import multi_fault
    MULTI_FAULT_AVAILABLE = True
    print("多故障并发决策模块加载成功")
except ImportError as e:
    multi_fault = None
    MULTI_FAULT_AVAILABLE = False
    print(f"多故障并发决策模块加载失败: {e}")


# ====================== RAG 检索控制台 ======================
@app.route('/rag-console')
def rag_console_page():
    """RAG 检索控制台：查看索引状态、对比向量召回与关键词召回效果"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('rag_console.html')


@app.route('/api/rag/status', methods=['GET'])
def api_rag_status():
    """索引状态"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not RAG_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': 'RAG 模块未加载'}), 503
    status = rag_retriever.index_status()
    status['success'] = True
    status['full_kb_chars'] = len(knowledge_content or '')
    return jsonify(status)


@app.route('/api/rag/rebuild', methods=['POST'])
def api_rag_rebuild():
    """重建知识库向量索引（教师）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师可以重建索引'}), 403
    if not RAG_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': 'RAG 模块未加载'}), 503
    try:
        result = rag_retriever.build_index(force=True)
    except Exception as e:  # noqa: BLE001
        return jsonify({'success': False, 'error': f'索引重建失败: {e}'}), 500
    result.update(rag_retriever.index_status())
    if SECURITY_MODULE_AVAILABLE:
        security.audit('rag_rebuild', target='data/rag_index.json',
                       detail=f"重建索引：{result.get('chunks', 0)} 个切片 / {result.get('dim', 0)} 维")
    return jsonify(result)


@app.route('/api/rag/search', methods=['GET', 'POST'])
def api_rag_search():
    """RAG 检索：同时返回向量混合召回与纯关键词召回结果，便于对比验证"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not RAG_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': 'RAG 模块未加载'}), 503

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        query = (data.get('query') or '').strip()
        top_k = int(data.get('top_k') or rag_retriever.TOP_K)
    else:
        query = (request.args.get('query') or request.args.get('q') or '').strip()
        top_k = int(request.args.get('top_k') or rag_retriever.TOP_K)
    if not query:
        return jsonify({'success': False, 'error': '请输入检索内容'}), 400
    top_k = max(1, min(top_k, 20))

    if not rag_retriever.load_index():
        return jsonify({'success': False, 'error': '索引尚未建立，请先重建索引'}), 409

    try:
        rag_hits = rag_retriever.search(query, top_k=top_k)
    except Exception as e:  # noqa: BLE001
        return jsonify({'success': False, 'error': f'检索失败: {e}'}), 500
    keyword_hits = rag_retriever.keyword_baseline(query, top_k=top_k)

    used = sum(len(c['text']) for c in rag_hits)
    total = len(knowledge_content or '')
    return jsonify({
        'success': True,
        'query': query,
        'top_k': top_k,
        'rag_hits': rag_hits,
        'keyword_hits': keyword_hits,
        'meta': {
            'rag_count': len(rag_hits),
            'keyword_count': len(keyword_hits),
            'used_chars': used,
            'total_chars': total,
            'compress_ratio': round(1 - used / total, 3) if total else 0,
            'degraded': bool(rag_hits and rag_hits[0].get('degraded')),
        },
    })


# ====================== 安全与审计 ======================
@app.route('/audit-log-page')
def audit_log_page():
    """操作审计看板（教师）：查高危操作的执行人、时间、来源 IP 与改动前后"""
    if not session.get('authenticated'):
        return render_template('login.html')
    if session.get('role') != 'teacher':
        return redirect('/')
    return render_template('audit_log.html')


@app.route('/api/security/summary', methods=['GET'])
def api_security_summary():
    """合规概览：凭据哈希状态 + 审计统计"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '权限不足：该操作仅限老师'}), 403
    if not SECURITY_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '安全模块未加载'}), 503
    return jsonify({
        'success': True,
        'credential': security.credential_status(),
        'audit': security.audit_stats(),
        'actions': [{'action': k, 'label': v} for k, v in security.AUDIT_ACTIONS.items()],
    })


@app.route('/api/security/audit', methods=['GET'])
def api_security_audit():
    """查询审计记录（教师）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '权限不足：该操作仅限老师'}), 403
    if not SECURITY_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '安全模块未加载'}), 503
    try:
        limit = max(1, min(int(request.args.get('limit') or 100), 500))
    except ValueError:
        limit = 100
    records = security.read_audit(limit=limit,
                                  action=(request.args.get('action') or '').strip(),
                                  keyword=(request.args.get('keyword') or '').strip())
    return jsonify({'success': True, 'total': len(records), 'records': records})


@app.route('/job-recruitment-page')
def job_recruitment_page():
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('job_recruitment.html')


@app.route('/api/jobs', methods=['GET'])
def api_get_jobs():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载', 'jobs': []})

    keyword = request.args.get('keyword')
    location = request.args.get('location')
    salary_min = request.args.get('salary_min', type=int)
    experience = request.args.get('experience')
    education = request.args.get('education')
    source = request.args.get('source')
    only_new = request.args.get('only_new', 'false').lower() == 'true'
    only_hot = request.args.get('only_hot', 'false').lower() == 'true'
    only_favorite = request.args.get('only_favorite', 'false').lower() == 'true'

    jobs = job_crawler.load_job_recruitments()
    filtered = job_crawler.filter_jobs(
        jobs, keyword, location, salary_min, experience,
        education, source, only_new, only_hot, only_favorite
    )

    config = job_crawler.load_job_config()

    return jsonify({
        'success': True,
        'jobs': filtered,
        'total': len(filtered),
        'last_fetch_time': config.get('last_fetch_time')
    })


@app.route('/api/jobs/statistics', methods=['GET'])
def api_job_statistics():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    jobs = job_crawler.load_job_recruitments()
    stats = job_crawler.get_job_statistics(jobs)
    config = job_crawler.load_job_config()
    stats['last_fetch_time'] = config.get('last_fetch_time')

    return jsonify({'success': True, **stats})


@app.route('/api/jobs/<job_id>', methods=['GET'])
def api_get_job_detail(job_id):
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    jobs = job_crawler.load_job_recruitments()
    job = next((j for j in jobs if j['id'] == job_id), None)

    if job:
        job_crawler.mark_job_viewed(job_id)

    return jsonify({'success': job is not None, 'job': job})


@app.route('/api/jobs/<job_id>/favorite', methods=['POST'])
def api_toggle_favorite(job_id):
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    job = job_crawler.toggle_job_favorite(job_id)
    return jsonify({
        'success': job is not None,
        'job': job,
        'message': '操作成功' if job else '岗位不存在'
    })


@app.route('/api/jobs/<job_id>/apply', methods=['POST'])
def api_apply_job(job_id):
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    job = job_crawler.mark_job_applied(job_id)
    return jsonify({
        'success': job is not None,
        'job': job,
        'message': '投递成功' if job else '岗位不存在'
    })


@app.route('/api/jobs/export', methods=['GET'])
def api_export_jobs():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    jobs = job_crawler.load_job_recruitments()
    stats = job_crawler.get_job_statistics(jobs)
    config = job_crawler.load_job_config()

    return jsonify({
        'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(jobs),
        'statistics': stats,
        'config': {
            'keywords': config.get('keywords', []),
            'locations': config.get('locations', []),
            'last_fetch_time': config.get('last_fetch_time')
        },
        'jobs': jobs
    })


@app.route('/api/job-scheduler/status', methods=['GET'])
def api_scheduler_status():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载', 'is_running': False})

    status = job_scheduler.job_scheduler.get_status()
    return jsonify({'success': True, **status})


@app.route('/api/job-scheduler/fetch-now', methods=['POST'])
def api_scheduler_fetch_now():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    try:
        jobs = job_scheduler.job_scheduler.fetch_now()
        return jsonify({
            'success': True,
            'message': f'抓取完成，共获取{len(jobs)}条招聘信息',
            'count': len(jobs)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job-scheduler/auto-fetch', methods=['POST'])
def api_scheduler_auto_fetch():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    job_scheduler.job_scheduler.set_auto_fetch(enabled)

    return jsonify({
        'success': True,
        'enabled': enabled,
        'message': f'自动抓取已{"开启" if enabled else "关闭"}'
    })


@app.route('/api/job-scheduler/interval', methods=['POST'])
def api_scheduler_interval():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    data = request.get_json() or {}
    hours = max(1, int(data.get('hours', 6)))
    job_scheduler.job_scheduler.update_interval(hours)

    return jsonify({
        'success': True,
        'interval_hours': hours,
        'message': f'抓取间隔已更新为每{hours}小时'
    })


@app.route('/api/job-config', methods=['GET'])
def api_get_job_config():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})
    config = job_crawler.load_job_config()
    config['enterprise_sites'] = [{'id': s['id'], 'name': s['name'], 'url': s['url']}
                                   for s in job_crawler.ENTERPRISE_SITES]
    config['third_party_apis'] = [{'id': a['id'], 'name': a['name'], 'url': a['url'],
                                    'needs_key': a['needs_key'], 'free_quota': a.get('free_quota', 0)}
                                   for a in job_crawler.THIRD_PARTY_APIS]
    return jsonify({'success': True, 'config': config})


@app.route('/api/job-config', methods=['POST'])
def api_update_job_config():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})

    data = request.get_json() or {}
    config = job_crawler.load_job_config()

    if 'fetch_mode' in data:
        config['fetch_mode'] = data['fetch_mode']
    if 'third_party_api_key' in data:
        config['third_party_api_key'] = data['third_party_api_key']
    if 'third_party_api_provider' in data:
        config['third_party_api_provider'] = data['third_party_api_provider']
    if 'enterprise_sites_enabled' in data:
        config['enterprise_sites_enabled'] = data['enterprise_sites_enabled']
    if 'enterprise_fetch_enabled' in data:
        config['enterprise_fetch_enabled'] = data['enterprise_fetch_enabled']
    if 'api_fetch_enabled' in data:
        config['api_fetch_enabled'] = data['api_fetch_enabled']
    if 'keywords' in data:
        config['keywords'] = data['keywords']
    if 'locations' in data:
        config['locations'] = data['locations']

    job_crawler.save_job_config(config)
    return jsonify({'success': True, 'message': '配置已更新', 'config': config})


@app.route('/api/recruitment-websites', methods=['GET'])
def api_get_recruitment_websites():
    if not JOB_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '招聘模块未加载'})
    websites = job_crawler.RECRUITMENT_WEBSITES
    return jsonify({'success': True, 'websites': websites, 'total': len(websites)})


# ====================== 职业问卷与每周任务 API ======================

@app.route('/api/survey', methods=['GET'])
def api_get_survey():
    """获取问卷题目"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    return jsonify({'success': True, 'questions': SURVEY_QUESTIONS})


@app.route('/api/survey/submit', methods=['POST'])
def api_submit_survey():
    """提交问卷，返回岗位推荐"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json() or {}
    answers = data.get('answers', {})

    # 统计各岗位得分
    scores = {job: 0 for job in JOB_REQUIREMENTS.keys()}
    for qid, answer in answers.items():
        question = next((q for q in SURVEY_QUESTIONS if q['id'] == qid), None)
        if not question:
            continue
        selected = answer if isinstance(answer, list) else [answer]
        for opt_value in selected:
            opt = next((o for o in question['options'] if o['value'] == opt_value), None)
            if opt:
                for job, weight in opt.get('weights', {}).items():
                    scores[job] = scores.get(job, 0) + weight

    # 排序推荐
    sorted_jobs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    recommendations = []
    for job_name, score in sorted_jobs:
        detail = CAREER_DETAILS.get(job_name, {})
        recommendations.append({
            'job_name': job_name,
            'score': score,
            'icon': detail.get('icon', ''),
            'description': detail.get('description', ''),
            'salary_range': detail.get('salary_range', ''),
            'match_level': '高' if score >= 8 else ('中' if score >= 5 else '低')
        })

    # 保存问卷结果到学生档案
    student_no = session.get('student_no', '')
    if student_no:
        students = load_students()
        student = next((s for s in students if s.get('student_no') == student_no), None)
        if student:
            student['survey_completed'] = True
            student['survey_answers'] = answers
            student['survey_result'] = recommendations[:4]
            save_students(students)

    return jsonify({
        'success': True,
        'recommendations': recommendations,
        'top_recommendation': recommendations[0] if recommendations else None
    })


@app.route('/api/career/target', methods=['GET'])
def api_get_career_target():
    """获取当前目标岗位"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)

    if not student:
        return jsonify({'error': '学生不存在'}), 404

    target_job = student.get('target_job', '')
    survey_completed = student.get('survey_completed', False)

    return jsonify({
        'success': True,
        'target_job': target_job,
        'survey_completed': survey_completed,
        'survey_result': student.get('survey_result', []),
        'available_jobs': list(CAREER_DETAILS.keys())
    })


@app.route('/api/career/target', methods=['POST'])
def api_set_career_target():
    """设置目标岗位 - 支持自定义岗位名称"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json() or {}
    target_job = data.get('target_job', '').strip()

    if not target_job:
        return jsonify({'success': False, 'message': '请输入目标岗位名称'})

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)

    if not student:
        return jsonify({'error': '学生不存在'}), 404

    student['target_job'] = target_job
    student['target_set_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_students(students)

    # 如果是系统预设岗位，返回详细信息；否则生成通用信息
    if target_job in CAREER_DETAILS:
        detail = CAREER_DETAILS[target_job]
    else:
        # 自定义岗位：生成通用信息
        detail = {
            'icon': '💼',
            'description': f'您选择了自定义岗位：{target_job}',
            'skills': ['信号与系统', '通信原理', '数字信号处理', '网络协议', '调制技术'],
            'salary_range': '根据具体能力和经验而定',
            'career_path': f'为{target_job}定制的发展路径',
            'learning_focus': ['基础摸底', '专项提升', '实战训练']
        }

    return jsonify({
        'success': True,
        'message': f'目标岗位已设置为：{target_job}',
        'target_job': target_job,
        'career_detail': detail,
        'is_custom': target_job not in CAREER_DETAILS
    })


@app.route('/api/weekly-tasks', methods=['GET'])
def api_get_weekly_tasks():
    """获取本周任务卡 - 分阶段策略"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)

    if not student:
        return jsonify({'error': '学生不存在'}), 404

    target_job = student.get('target_job', '')
    if not target_job:
        return jsonify({'success': True, 'need_target': True, 'message': '请先设置目标岗位'})

    # 计算当前周数
    target_set_time = student.get('target_set_time', '')
    if target_set_time:
        try:
            set_date = datetime.strptime(target_set_time[:10], "%Y-%m-%d")
            week_num = ((datetime.now() - set_date).days // 7) + 1
        except:
            week_num = 1
    else:
        week_num = 1

    if week_num > 52:
        week_num = 52

    week_key = f"week_{week_num}"
    weekly_tasks = student.get('weekly_tasks', {})

    # 支持查看已生成的历史周任务（?week=week_1），仅允许查看已存在的周，不会新建
    view_week = (request.args.get('week') or '').strip()
    if view_week and re.fullmatch(r'week_\d{1,2}', view_week) and view_week in weekly_tasks:
        week_num = int(view_week.split('_')[1])
        week_key = view_week

    # 判断阶段
    stage = ""
    weak_areas = []
    analysis_summary = ""

    if week_num <= 2:
        stage = "basic"
    else:
        # 第3周起：先检查是否有学习数据
        has_learning_data = any(
            student.get('competence_analysis', {}).get(area['id'], {}).get('count', 0) > 0
            for area in COMPETENCE_AREAS
        )
        if not has_learning_data:
            stage = "basic"
            analysis_summary = "您还没有学习记录，建议先完成基础摸底任务"
        else:
            stage = "targeted"
            # 计算薄弱环节
            job_req = JOB_REQUIREMENTS.get(target_job, {})
            if not job_req:
                job_req = {}
                for area in COMPETENCE_AREAS:
                    job_req[area['id']] = 0.6

            gaps = []
            for area in COMPETENCE_AREAS:
                area_id = area['id']
                if area_id in job_req:
                    score = student.get('competence_analysis', {}).get(area_id, {}).get('score', 0)
                    gap = job_req[area_id] - score
                    gaps.append({
                        'area_id': area_id,
                        'area_name': area['name'],
                        'current': round(score, 2),
                        'required': job_req[area_id],
                        'gap': round(gap, 2)
                    })
            gaps.sort(key=lambda x: x['gap'], reverse=True)
            weak_areas = gaps[:4]
            analysis_summary = f"根据您前{week_num - 1}周的学习数据，系统分析出您的薄弱环节为：{', '.join(g['area_name'] for g in weak_areas[:3])}"

    # 如果本周任务已存在，直接返回
    if week_key in weekly_tasks:
        current_week = weekly_tasks[week_key]
        completed = sum(1 for t in current_week['tasks'] if t.get('completed'))
        current_week['completed_tasks'] = completed
        current_week['stage'] = stage
        current_week['analysis_summary'] = analysis_summary
        current_week['weak_areas'] = weak_areas
        student['weekly_tasks'] = weekly_tasks
        save_students(students)
    else:
        # 生成新一周的任务
        tasks = []

        if stage == "basic":
            # 基础阶段：用BASIC_WEEKLY_TASKS
            basic_templates = BASIC_WEEKLY_TASKS.get(week_num, BASIC_WEEKLY_TASKS.get(1, []))
            for tmpl in basic_templates:
                tasks.append({
                    'id': f"task_{week_num}_basic_{len(tasks)}",
                    'title': tmpl['title'],
                    'detail': tmpl['detail'],
                    'estimated_time': tmpl['estimated_time'],
                    'area': tmpl.get('area', ''),
                    'area_id': tmpl.get('area_id', ''),
                    'current_score': 0,
                    'required_score': 0,
                    'gap': 0,
                    'completed': False
                })
        else:
            # 精准提升阶段：基于薄弱环节
            job_req = JOB_REQUIREMENTS.get(target_job, {})
            if not job_req:
                job_req = {}
                for area in COMPETENCE_AREAS:
                    job_req[area['id']] = 0.6

            student_scores = {}
            for area in COMPETENCE_AREAS:
                student_scores[area['id']] = student.get('competence_analysis', {}).get(area['id'], {}).get('score', 0)

            # 取差距最大的3个领域
            gaps = []
            for area in COMPETENCE_AREAS:
                area_id = area['id']
                if area_id in job_req:
                    gap = job_req[area_id] - student_scores.get(area_id, 0)
                    gaps.append({
                        'area_id': area_id,
                        'area_name': area['name'],
                        'current': round(student_scores.get(area_id, 0), 2),
                        'required': job_req[area_id],
                        'gap': round(gap, 2)
                    })

            gaps.sort(key=lambda x: x['gap'], reverse=True)

            # ===== 艾宾浩斯遗忘曲线增强 =====
            # 计算每个领域的遗忘率，优先推荐即将遗忘的知识
            for g in gaps:
                area_id = g['area_id']
                comp_data = student.get('competence_analysis', {}).get(area_id, {})
                last_learned = comp_data.get('last_learned', '')
                score = comp_data.get('score', 0.5)
                count = comp_data.get('count', 0)

                # 艾宾浩斯遗忘曲线：R = e^(-t/S)
                # t=间隔天数, S=记忆稳定性(与练习次数正相关)
                forget_rate = 0
                if last_learned and count > 0:
                    try:
                        t = max(0, (datetime.now() - datetime.strptime(last_learned[:10], "%Y-%m-%d")).days)
                        stability = max(1, count * 2.5)  # 每次学习增加稳定性
                        forget_rate = round(1 - math.exp(-t / stability), 3)
                    except:
                        forget_rate = 0
                g['forget_rate'] = forget_rate
                g['priority_score'] = round(g['gap'] * 0.6 + forget_rate * 0.4, 3)

            # 综合排序：差距×0.6 + 遗忘率×0.4
            gaps.sort(key=lambda x: x['priority_score'], reverse=True)
            focus_areas = gaps[:3]
            # 加1个优势领域保持
            if len(gaps) > 3:
                focus_areas.append(gaps[-1])

            for area in focus_areas:
                templates = WEEKLY_TASK_TEMPLATES.get(area['area_id'], [])
                for tmpl in templates:
                    tasks.append({
                        'id': f"task_{week_num}_{area['area_id']}_{len(tasks)}",
                        'title': tmpl['title'],
                        'detail': tmpl['detail'],
                        'estimated_time': tmpl['estimated_time'],
                        'area': area['area_name'],
                        'area_id': area['area_id'],
                        'current_score': area['current'],
                        'required_score': area['required'],
                        'gap': area['gap'],
                        'forget_rate': area.get('forget_rate', 0),
                        'priority_score': area.get('priority_score', 0),
                        'review': area.get('forget_rate', 0) > 0.3,
                        'completed': False
                    })

        weekly_tasks[week_key] = {
            'week_num': week_num,
            'generated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'target_job': target_job,
            'tasks': tasks,
            'total_tasks': len(tasks),
            'completed_tasks': 0,
            'stage': stage,
            'analysis_summary': analysis_summary,
            'weak_areas': weak_areas
        }
        student['weekly_tasks'] = weekly_tasks
        save_students(students)
        current_week = weekly_tasks[week_key]

    # 构建返回数据
    career_detail = CAREER_DETAILS.get(target_job, {
        'icon': '💼',
        'description': f'目标岗位：{target_job}',
        'skills': [],
        'salary_range': '',
        'career_path': '',
        'learning_focus': []
    })

    return jsonify({
        'success': True,
        'week_num': week_num,
        'target_job': target_job,
        'career_detail': career_detail,
        'tasks': current_week['tasks'],
        'total_tasks': current_week['total_tasks'],
        'completed_tasks': current_week.get('completed_tasks', 0),
        'generated_at': current_week['generated_at'],
        'all_weeks': sorted(weekly_tasks.keys()),
        'stage': stage,
        'stage_label': '基础摸底阶段' if stage == 'basic' else '精准提升阶段',
        'analysis_summary': current_week.get('analysis_summary', analysis_summary),
        'weak_areas': current_week.get('weak_areas', weak_areas),
        'needs_analysis': stage == 'targeted'
    })


@app.route('/api/weekly-tasks/<task_id>/detail', methods=['GET'])
def api_get_task_detail(task_id):
    """获取任务详情：关联PPT、知识库、学习建议"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    task = None
    weekly_tasks = student.get('weekly_tasks', {})
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            if t['id'] == task_id:
                task = t
                break
        if task:
            break

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    area_id = task.get('area_id', '')
    area_name = task.get('area', '')

    # 1. 查找相关PPT
    ppt_list = []
    if area_id in AREA_KNOWLEDGE_MAP:
        keywords = AREA_KNOWLEDGE_MAP[area_id]
        for kw in keywords[:2]:
            results = search_ppt_by_keyword(kw)
            for r in results:
                if r not in ppt_list:
                    ppt_list.append(r)

    # 2. 查找相关知识图谱
    knowledge_info = []
    kg = KNOWLEDGE_GRAPH
    if area_id in AREA_KNOWLEDGE_MAP:
        for kw in AREA_KNOWLEDGE_MAP[area_id]:
            for concept, info in kg.items():
                if kw in concept or any(kw in kp for kp in info.get('key_points', [])):
                    knowledge_info.append({
                        'concept': concept,
                        'description': info.get('description', ''),
                        'key_points': info.get('key_points', []),
                        'related': info.get('related', [])
                    })
                    if len(knowledge_info) >= 3:
                        break
            if len(knowledge_info) >= 3:
                break

    # 3. 检查知识库中是否有相关内容
    kb_content = load_knowledge()
    kb_has_content = False
    kb_relevant = False
    if kb_content:
        kb_has_content = True
        if area_id in AREA_KNOWLEDGE_MAP:
            for kw in AREA_KNOWLEDGE_MAP[area_id]:
                if kw in kb_content:
                    kb_relevant = True
                    break

    # 4. 学习建议
    study_suggestion = STUDY_SUGGESTIONS.get(area_id, '建议系统学习相关领域的基础知识。')

    # 5. AI对话历史分析
    conversation_count = 0
    ai_proficiency = 0.5
    conv_history = student.get('conversation_history', [])
    if conv_history and area_id in AREA_KNOWLEDGE_MAP:
        relevant_count = 0
        for conv in conv_history:
            msg = conv.get('message', '')
            for kw in AREA_KNOWLEDGE_MAP[area_id]:
                if kw in msg:
                    relevant_count += 1
                    break
        conversation_count = relevant_count
        if len(conv_history) > 0:
            ai_proficiency = min(1.0, relevant_count / max(len(conv_history), 1) + 0.3)

    has_ppt = len(ppt_list) > 0
    has_knowledge = len(knowledge_info) > 0 or kb_relevant

    return jsonify({
        'success': True,
        'task': task,
        'has_ppt': has_ppt,
        'has_knowledge': has_knowledge,
        'ppt_list': ppt_list[:5],
        'knowledge_info': knowledge_info,
        'kb_has_content': kb_has_content,
        'kb_relevant': kb_relevant,
        'study_suggestion': study_suggestion,
        'area_id': area_id,
        'area_name': area_name,
        'conversation_count': conversation_count,
        'ai_proficiency': round(ai_proficiency, 2)
    })


@app.route('/api/weekly-tasks/<task_id>/quiz', methods=['GET'])
def api_get_task_quiz(task_id):
    """获取任务相关的测验题目"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    task = None
    weekly_tasks = student.get('weekly_tasks', {})
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            if t['id'] == task_id:
                task = t
                break
        if task:
            break

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    area_id = task.get('area_id', '')
    questions = QUIZ_BANKS.get(area_id, [])

    if not questions:
        return jsonify({
            'success': True,
            'has_quiz': False,
            'message': '该领域暂无测验题目，请直接完成任务',
            'area_id': area_id
        })

    quiz_questions = []
    for q in questions[:5]:
        quiz_questions.append({
            'id': q['id'],
            'question': q['question'],
            'options': q['options'],
            'analysis': q.get('analysis', '')
        })

    # 检查是否已有测验记录
    quiz_attempts = student.get('quiz_attempts', {}).get(task_id, {})
    already_passed = quiz_attempts.get('passed', False)
    attempt_count = quiz_attempts.get('attempt_count', 0)

    # 动态故障注入：根据领域随机选择一个故障场景
    import random
    fault_scenario = None
    fault_scenarios = FAULT_SCENARIOS.get(area_id, [])
    if fault_scenarios:
        # 如果已有记录，使用相同的故障场景；否则随机选取一个
        existing_fault = quiz_attempts.get('fault_scenario_id')
        if existing_fault:
            fault_scenario = next((f for f in fault_scenarios if f['id'] == existing_fault), None)
        if not fault_scenario:
            fault_scenario = random.choice(fault_scenarios) if fault_scenarios else None

    # 前置自检清单
    pre_checklist = []
    if fault_scenario:
        pre_checklist = fault_scenario.get('pre_checklist', [])

    return jsonify({
        'success': True,
        'has_quiz': True,
        'questions': quiz_questions,
        'total_questions': len(quiz_questions),
        'pass_score': int(len(quiz_questions) * 0.6),
        'task_id': task_id,
        'attempt_count': attempt_count,
        'already_passed': already_passed,
        'area_id': area_id,
        'fault_scenario': fault_scenario,
        'pre_checklist': pre_checklist,
        'need_pre_check': len(pre_checklist) > 0 and not already_passed
    })


@app.route('/api/weekly-tasks/<task_id>/quiz', methods=['POST'])
def api_submit_task_quiz(task_id):
    """提交测验答案并评分"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json() or {}
    answers = data.get('answers', {})

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    task = None
    week_key_found = None
    weekly_tasks = student.get('weekly_tasks', {})
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            if t['id'] == task_id:
                task = t
                week_key_found = week_key
                break
        if task:
            break

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    area_id = task.get('area_id', '')
    questions = QUIZ_BANKS.get(area_id, [])
    if not questions:
        return jsonify({'success': True, 'passed': True, 'score': 100, 'message': '该领域无需测验'})

    # ========== 前置自检校验 ==========
    pre_check_answers = data.get('pre_check', {})
    fault_scenario_id = data.get('fault_scenario_id', '')
    fault_scenarios = FAULT_SCENARIOS.get(area_id, [])
    submitted_fault = next((f for f in fault_scenarios if f['id'] == fault_scenario_id), None) if fault_scenario_id else None

    if submitted_fault:
        checklist = submitted_fault.get('pre_checklist', [])
        failed_checks = []
        for chk in checklist:
            if chk.get('required', True) and not pre_check_answers.get(chk['id'], False):
                failed_checks.append(chk['text'])

        if failed_checks:
            return jsonify({
                'success': False,
                'pre_check_failed': True,
                'message': '前置自检未通过，以下检查项未确认：',
                'failed_checks': failed_checks,
                'fault_scenario': submitted_fault
            })

    # 评分
    correct = 0
    results = []
    for q in questions[:5]:
        user_answer = answers.get(q['id'])
        is_correct = user_answer == q['answer']
        if is_correct:
            correct += 1
        results.append({
            'id': q['id'],
            'correct': is_correct,
            'user_answer': user_answer,
            'correct_answer': q['answer'],
            'analysis': q.get('analysis', '')
        })

    total = len(questions[:5])
    score = int(correct / total * 100)
    pass_score = 60
    passed = score >= pass_score

    # 安全/伦理评估：如果未通过必要的自检项（可选项未勾选），扣分
    safety_score = 100
    if submitted_fault:
        for chk in submitted_fault.get('pre_checklist', []):
            if not chk.get('required', True) and not pre_check_answers.get(chk['id'], False):
                safety_score -= 10
        safety_score = max(0, safety_score)

    # 综合评分：知识得分 * 0.8 + 安全得分 * 0.2
    final_score = int(score * 0.8 + safety_score * 0.2)
    if final_score < pass_score and score >= pass_score:
        # 如果安全分低导致综合不及格，给出提示
        pass_score = pass_score  # keep
        passed = final_score >= pass_score
        safety_warning = "安全操作规范未完全遵守，综合评分降低" if safety_score < 100 else None
    else:
        passed = score >= pass_score
        safety_warning = "安全操作规范未完全遵守" if safety_score < 100 else None

    # 更新测验记录
    if 'quiz_attempts' not in student:
        student['quiz_attempts'] = {}
    if task_id not in student['quiz_attempts']:
        student['quiz_attempts'][task_id] = {'attempt_count': 0, 'passed': False, 'best_score': 0}

    quiz_rec = student['quiz_attempts'][task_id]
    quiz_rec['attempt_count'] = quiz_rec.get('attempt_count', 0) + 1
    quiz_rec['last_score'] = score
    quiz_rec['final_score'] = final_score
    quiz_rec['safety_score'] = safety_score
    if submitted_fault:
        quiz_rec['fault_scenario_id'] = submitted_fault['id']
        quiz_rec['fault_scenario_name'] = submitted_fault['name']
    if final_score > quiz_rec.get('best_score', 0):
        quiz_rec['best_score'] = final_score
    if passed:
        quiz_rec['passed'] = True
        quiz_rec['passed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 更新能力分析（基于测验表现）
    if passed:
        if 'competence_analysis' not in student:
            student['competence_analysis'] = {area['id']: {'count': 0, 'score': 0.0} for area in COMPETENCE_AREAS}

        current = student['competence_analysis'].get(area_id, {'count': 0, 'score': 0.0})
        count = current.get('count', 0)
        current_score = current.get('score', 0.0)

        # 基础分：根据通过次数调整
        attempt_count = quiz_rec['attempt_count']
        if attempt_count == 1:
            base_score = 0.8
        elif attempt_count == 2:
            base_score = 0.65
        elif attempt_count <= 3:
            base_score = 0.5
        else:
            base_score = 0.35

        # AI对话因子
        ai_factor = 0.0
        conv_history = student.get('conversation_history', [])
        if conv_history and area_id in AREA_KNOWLEDGE_MAP:
            relevant_kw = AREA_KNOWLEDGE_MAP[area_id]
            relevant_msgs = sum(1 for c in conv_history if any(kw in c.get('message', '') for kw in relevant_kw))
            ai_factor = min(0.2, relevant_msgs * 0.02)

        # 安全/伦理因子
        safety_factor = (safety_score / 100) * 0.2

        new_score = min(1.0, base_score + ai_factor + safety_factor)

        student['competence_analysis'][area_id] = {
            'count': count + 1,
            'score': round((current_score * count + new_score) / (count + 1), 3),
            'last_quiz_score': score,
            'last_final_score': final_score,
            'last_safety_score': safety_score,
            'quiz_attempts': attempt_count,
            'ai_conversations': relevant_msgs if conv_history else 0,
            'fault_scenario': submitted_fault['name'] if submitted_fault else None
        }

    # 如果通过，将任务标记为可完成
    task['quiz_passed'] = passed
    task['quiz_score'] = final_score
    task['quiz_raw_score'] = score
    task['quiz_safety_score'] = safety_score
    task['quiz_attempts'] = quiz_rec['attempt_count']
    task['fault_scenario_id'] = submitted_fault['id'] if submitted_fault else None
    task['fault_scenario_name'] = submitted_fault['name'] if submitted_fault else None

    if week_key_found:
        weekly_tasks[week_key_found]['completed_tasks'] = sum(
            1 for t in weekly_tasks[week_key_found]['tasks'] if t.get('completed')
        )

    save_students(students)

    proficiency_level = "入门"
    if final_score >= 90:
        proficiency_level = "精通"
    elif final_score >= 75:
        proficiency_level = "熟练"
    elif final_score >= 60:
        proficiency_level = "掌握"

    # 构建返回消息
    score_msg = f'测验得分：{final_score}分'
    if safety_score < 100:
        score_msg += f'（安全规范扣分：{100 - safety_score}分）'
    score_msg += f'（及格线：{pass_score}分）'

    # 失败锁定机制：连续失败3次以上，锁定5分钟
    locked = False
    lock_remaining = 0
    if not passed and quiz_rec['attempt_count'] >= 3:
        if 'task_locks' not in student:
            student['task_locks'] = {}
        student['task_locks'][task_id] = {
            'locked': True,
            'locked_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'reason': f'连续失败{quiz_rec["attempt_count"]}次，需冷却后重试'
        }
        save_students(students)
        locked = True
        lock_remaining = 300  # 5分钟

    return jsonify({
        'success': True,
        'passed': passed,
        'score': score,
        'final_score': final_score,
        'safety_score': safety_score,
        'total': total,
        'correct': correct,
        'results': results,
        'attempt_count': quiz_rec['attempt_count'],
        'proficiency_level': proficiency_level,
        'message': score_msg,
        'next_step': '可以完成任务了' if passed else '请复习相关知识后重新挑战',
        'fault_scenario': submitted_fault,
        'safety_warning': safety_warning,
        'locked': locked,
        'lock_remaining_seconds': lock_remaining,
        'lock_message': f'连续失败{quiz_rec["attempt_count"]}次，操作已锁定{lock_remaining}秒，请复习后重试' if locked else None
    })


@app.route('/api/weekly-tasks/<task_id>/complete', methods=['POST'])
def api_complete_weekly_task(task_id):
    """标记任务完成/取消完成 - 需通过测验才能完成"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json() or {}
    completed = data.get('completed', True)

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)

    if not student:
        return jsonify({'error': '学生不存在'}), 404

    weekly_tasks = student.get('weekly_tasks', {})
    task_found = False
    for week_key, week_data in weekly_tasks.items():
        for task in week_data.get('tasks', []):
            if task['id'] == task_id:
                # 检查是否通过测验（有题库的领域需要先通过测验）
                area_id = task.get('area_id', '')
                has_quiz = area_id in QUIZ_BANKS and len(QUIZ_BANKS[area_id]) > 0

                if completed and has_quiz:
                    quiz_attempts = student.get('quiz_attempts', {}).get(task_id, {})
                    quiz_passed = quiz_attempts.get('passed', False)
                    if not quiz_passed:
                        return jsonify({
                            'success': False,
                            'need_quiz': True,
                            'message': '请先完成该任务的测验并通过',
                            'task_id': task_id
                        })

                task['completed'] = completed
                task_found = True
                break
        if task_found:
            week_data['completed_tasks'] = sum(1 for t in week_data['tasks'] if t.get('completed'))
            break

    if not task_found:
        return jsonify({'success': False, 'message': '任务不存在'})

    save_students(students)

    return jsonify({
        'success': True,
        'message': '任务已完成' if completed else '任务已取消完成',
        'task_id': task_id,
        'completed': completed
    })


# ====================== 自动工程报告 ======================
@app.route('/api/weekly-tasks/<task_id>/report', methods=['GET'])
def api_task_report(task_id):
    """生成自动工程报告：根因分析 + 操作日志 + 能力评估"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    # 查找任务
    task = None
    week_key_found = None
    weekly_tasks = student.get('weekly_tasks', {})
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            if t['id'] == task_id:
                task = t
                week_key_found = week_key
                break
        if task:
            break

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    area_id = task.get('area_id', '')
    area_name = task.get('area', '')
    quiz_attempts = student.get('quiz_attempts', {}).get(task_id, {})

    # 故障场景信息
    fault_name = quiz_attempts.get('fault_scenario_name') or task.get('fault_scenario_name', '未注入故障')
    fault_scenarios = FAULT_SCENARIOS.get(area_id, [])
    fault_detail = next((f for f in fault_scenarios if f['name'] == fault_name), None)

    # 操作日志重建
    operation_log = []
    if quiz_attempts:
        operation_log.append({
            'time': quiz_attempts.get('passed_at', ''),
            'action': '前置自检',
            'result': '通过' if quiz_attempts.get('passed') else '未通过',
            'detail': f"故障场景：{fault_name}"
        })
        operation_log.append({
            'time': quiz_attempts.get('passed_at', ''),
            'action': '测验答题',
            'result': f"得分 {quiz_attempts.get('final_score', quiz_attempts.get('last_score', 0))}分",
            'detail': f"尝试次数：{quiz_attempts.get('attempt_count', 0)}"
        })
        if quiz_attempts.get('passed'):
            operation_log.append({
                'time': quiz_attempts.get('passed_at', ''),
                'action': '任务完成',
                'result': '完成',
                'detail': f"综合评分：{quiz_attempts.get('final_score', 0)}"
            })

    # 根因分析
    root_cause = ""
    if fault_detail:
        root_cause = f"故障「{fault_name}」的根因分析：{fault_detail['description']}"
        if area_id == 'signal_system':
            root_cause += " 根因可能是馈线接头密封不良导致进水，或射频模块老化导致增益下降。建议检查防水胶带和馈线VSWR指标。"
        elif area_id == 'communication_principle':
            root_cause += " 根因可能是光纤断纤或光模块故障，建议使用OTDR定位断点并更换光模块。"
        elif area_id == 'rf_engineering':
            root_cause += " 根因可能是天线驻波比恶化或PA模块增益下降，建议使用VSWR测试仪和频谱仪逐级排查。"
        elif area_id == 'network_protocol':
            root_cause += " 根因可能是路由配置错误或链路环路，建议检查路由表和OSPF邻居状态。"
        else:
            root_cause += " 建议结合设备告警日志和现场测量数据进一步定位。"

    # 能力评估
    competence = student.get('competence_analysis', {}).get(area_id, {})
    proficiency = "入门"
    comp_score = competence.get('score', 0)
    if comp_score >= 0.8:
        proficiency = "精通"
    elif comp_score >= 0.6:
        proficiency = "熟练"
    elif comp_score >= 0.4:
        proficiency = "掌握"

    # AI对话分析
    conv_history = student.get('conversation_history', [])
    relevant_kw = AREA_KNOWLEDGE_MAP.get(area_id, [])
    ai_conversations = sum(1 for c in conv_history if any(kw in c.get('message', '') for kw in relevant_kw)) if relevant_kw else 0

    # 安全评分
    safety_score = quiz_attempts.get('safety_score', 100)
    safety_assessment = "操作规范，安全意识良好" if safety_score >= 90 else \
                        "基本遵守安全规范，但存在改进空间" if safety_score >= 70 else \
                        "安全意识不足，需要加强培训"

    report = {
        'success': True,
        'task_id': task_id,
        'task_title': task.get('title', ''),
        'area_name': area_name,
        'area_id': area_id,
        'student_name': student.get('name', ''),
        'generated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'fault_scenario': {
            'name': fault_name,
            'description': fault_detail['description'] if fault_detail else '',
            'level': fault_detail['level'] if fault_detail else 'info'
        },
        'operation_log': operation_log,
        'root_cause_analysis': root_cause,
        'capability_assessment': {
            'proficiency': proficiency,
            'competence_score': round(comp_score, 3),
            'quiz_attempts': quiz_attempts.get('attempt_count', 0),
            'best_score': quiz_attempts.get('best_score', 0),
            'final_score': quiz_attempts.get('final_score', 0),
            'safety_score': safety_score,
            'safety_assessment': safety_assessment,
            'ai_conversations': ai_conversations
        },
        'competency_profile': calculate_competency_profile(student),
        'recommendation': STUDY_SUGGESTIONS.get(area_id, '继续加强该领域学习。')
    }

    # 保存报告到学生记录
    if 'task_reports' not in student:
        student['task_reports'] = {}
    student['task_reports'][task_id] = report
    save_students(students)

    return jsonify(report)


# ====================== 岗位胜任力画像 ======================
@app.route('/api/competency-profile', methods=['GET'])
def api_competency_profile():
    """获取学员5维岗位胜任力画像"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    profile = calculate_competency_profile(student)

    # 任务完成统计
    weekly_tasks = student.get('weekly_tasks', {})
    completed_count = 0
    total_count = 0
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            total_count += 1
            if t.get('completed'):
                completed_count += 1

    # 学习建议
    learning_path = []
    if profile['weaknesses']:
        learning_path.append({
            'type': '补短板',
            'description': f"优先提升「{profile['weaknesses'][0]['dimension']}」，建议参加相关培训和项目实战"
        })
    if profile['overall_score'] < 0.6:
        learning_path.append({
            'type': '强化基础',
            'description': '系统复习基础知识，完成基础摸底任务，巩固核心概念'
        })
    if completed_count > 0:
        learning_path.append({
            'type': '实战积累',
            'description': f'已完成 {completed_count} 个任务，继续推进精准提升任务'
        })

    return jsonify({
        'success': True,
        'student_name': student.get('name', ''),
        'student_no': student_no,
        'target_job': profile['target_job'],
        'competency_profile': profile,
        'progress': {
            'completed_tasks': completed_count,
            'total_tasks': total_count,
            'completion_rate': round(completed_count / total_count, 3) if total_count > 0 else 0
        },
        'learning_path': learning_path,
        'position_competency_map': POSITION_COMPETENCY_MAP
    })


# ====================== 双师协同：项目设计 / 情感联结 / 价值引导 ======================

# 伦理案例辩论库（用于价值引导 + 情感联结）
ETHICS_CASES = {
    "comm_case_1": {
        "id": "comm_case_1",
        "title": "紧急割接中的伦理抉择",
        "category": "工程伦理",
        "level": "高级",
        "description": "您负责的核心光缆需要紧急割接，但割接窗口恰逢业务高峰期。如果按计划割接将影响数千用户的通信，推迟割接又可能导致故障扩大。请从工程伦理和职业责任角度分析此场景。",
        "questions": [
            "从用户权益角度，应该如何权衡？",
            "从企业责任角度，应该如何决策？",
            "作为工程师，你的底线是什么？",
            "有哪些技术方案可以降低风险？"
        ],
        "teacher_guidance": "引导学员思考：1) 风险识别与评估；2) 利益相关者分析；3) 应急预案设计；4) 沟通与汇报策略"
    },
    "comm_case_2": {
        "id": "comm_case_2",
        "title": "数据隐私与安全漏洞",
        "category": "网络安全",
        "level": "中级",
        "description": "您发现系统存在一个已知安全漏洞，修复需要停机4小时。但上级要求在业务高峰后再修复，这期间可能被攻击。请讨论此情境的伦理与责任。",
        "questions": [
            "工程师的首要职责是什么？",
            "如何平衡业务影响与安全风险？",
            "如果拒绝执行，应该走什么流程？"
        ],
        "teacher_guidance": "引导学员思考：1) 安全红线；2) 沟通策略；3) 风险缓解措施；4) 文档与记录"
    },
    "comm_case_3": {
        "id": "comm_case_3",
        "title": "设备采购中的利益冲突",
        "category": "职业伦理",
        "level": "高级",
        "description": "您的亲属是某设备供应商的销售经理，公司正在采购相关设备。您被任命为评标委员会成员。请分析此情境。",
        "questions": [
            "是否应该主动申请回避？",
            "如何确保评标过程的公平性？",
            "如何处理好家庭与职业的关系？"
        ],
        "teacher_guidance": "引导学员思考：1) 利益冲突识别；2) 回避制度；3) 透明化流程；4) 个人品牌建设"
    }
}

# 项目设计模板库
PROJECT_DESIGNS = {
    "proj_1": {
        "id": "proj_1",
        "title": "5G 基站部署与优化实战",
        "area": "基站工程",
        "difficulty": "中级",
        "duration_weeks": 4,
        "description": "团队项目：在给定区域内完成 5G 基站的规划、部署、调试和优化工作。涵盖天馈系统、射频配置、参数优化、性能验证等环节。",
        "deliverables": ["站点选址报告", "RF 配置文件", "路测数据", "KPI 优化方案"],
        "competency_targets": ["technical", "project_management", "teamwork"],
        "teacher_interventions": ["规划评审", "中期检查", "结项答辩"]
    },
    "proj_2": {
        "id": "proj_2",
        "title": "核心网故障应急演练",
        "area": "核心网工程",
        "difficulty": "高级",
        "duration_weeks": 2,
        "description": "模拟核心网重大故障场景，要求学员团队在限定时间内完成故障定位、应急切换、业务恢复和根因分析。",
        "deliverables": ["应急预案", "故障处理记录", "根因分析报告", "改进建议"],
        "competency_targets": ["troubleshooting", "safety_awareness", "project_management"],
        "teacher_interventions": ["场景注入", "关键节点干预", "复盘指导"]
    },
    "proj_3": {
        "id": "proj_3",
        "title": "网络安全渗透测试实战",
        "area": "网络安全",
        "difficulty": "高级",
        "duration_weeks": 3,
        "description": "授权范围内的网络安全渗透测试项目。学员团队需完成信息收集、漏洞扫描、漏洞利用、权限提升等环节，并输出加固建议。",
        "deliverables": ["渗透测试报告", "漏洞清单", "POC 代码", "加固方案"],
        "competency_targets": ["technical", "safety_awareness", "innovation"],
        "teacher_interventions": ["范围确认", "风险预警", "报告评审"]
    }
}


@app.route('/api/double-teacher/ethics-cases', methods=['GET'])
def api_ethics_cases():
    """获取伦理案例库（价值引导）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    return jsonify({'success': True, 'cases': list(ETHICS_CASES.values())})


@app.route('/api/double-teacher/ethics-cases/<case_id>', methods=['GET'])
def api_ethics_case_detail(case_id):
    """获取单个伦理案例详情"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    case = ETHICS_CASES.get(case_id)
    if not case:
        return jsonify({'error': '案例不存在'}), 404
    return jsonify({'success': True, 'case': case})


@app.route('/api/double-teacher/ethics-cases/<case_id>/submit', methods=['POST'])
def api_ethics_case_submit(case_id):
    """提交案例辩论回答，AI分析思维质量"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json()
    answers = data.get('answers', [])
    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    case = ETHICS_CASES.get(case_id)
    if not case:
        return jsonify({'error': '案例不存在'}), 404

    # AI思维质量分析
    analysis = {
        'score': 0,
        'dimensions': {
            'user_perspective': 0,
            'responsibility': 0,
            'feasibility': 0,
            'ethics_awareness': 0
        },
        'feedback': []
    }

    full_text = ' '.join(answers)
    kw_user = ['用户', '权益', '客户', '影响', '公众']
    kw_resp = ['责任', '义务', '职责', '底线', '原则', '担当']
    kw_feasible = ['方案', '措施', '可行', '实施', '流程', '预案', '应急']
    kw_ethics = ['伦理', '道德', '公平', '正义', '合规', '合法']

    user_kw = sum(1 for w in kw_user if w in full_text)
    resp_kw = sum(1 for w in kw_resp if w in full_text)
    feas_kw = sum(1 for w in kw_feasible if w in full_text)
    ethics_kw = sum(1 for w in kw_ethics if w in full_text)

    analysis['dimensions']['user_perspective'] = min(100, user_kw * 20)
    analysis['dimensions']['responsibility'] = min(100, resp_kw * 20)
    analysis['dimensions']['feasibility'] = min(100, feas_kw * 20)
    analysis['dimensions']['ethics_awareness'] = min(100, ethics_kw * 20)

    for dim, val in analysis['dimensions'].items():
        if val < 40:
            analysis['feedback'].append(f"「{dim}」维度较弱，建议多从该角度思考问题")
        elif val >= 60:
            analysis['feedback'].append(f"「{dim}」维度表现良好")

    analysis['score'] = round(sum(analysis['dimensions'].values()) / 4)

    # 保存辩论记录
    if 'ethics_debates' not in student:
        student['ethics_debates'] = {}
    student['ethics_debates'][case_id] = {
        'answers': answers,
        'analysis': analysis,
        'submitted_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_students(students)

    return jsonify({'success': True, 'analysis': analysis, 'teacher_guidance': case.get('teacher_guidance', '')})


@app.route('/api/double-teacher/projects', methods=['GET'])
def api_project_designs():
    """获取项目设计库"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    return jsonify({'success': True, 'projects': list(PROJECT_DESIGNS.values())})


@app.route('/api/double-teacher/student/<student_no>/emotion-profile', methods=['GET'])
def api_emotion_profile(student_no):
    """获取学生情感档案（AI情感分析）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    # 基于对话历史的情感分析
    conv_history = student.get('conversation_history', [])
    total_msgs = len(conv_history)
    sentiment_scores = []
    emotion_signals = {
        'confusion': 0,     # 困惑
        'frustration': 0,   # 挫败
        'curiosity': 0,     # 好奇
        'confidence': 0,    # 自信
        'fatigue': 0        # 疲劳
    }

    confusion_kw = ['不懂', '不明白', '什么意思', '怎么理解', '困惑', '懵']
    frustration_kw = ['太难', '不会', '做不出来', '失败', '崩溃', '搞不定', '卡住']
    curiosity_kw = ['为什么', '怎么回事', '原理', '讲讲', '解释', '深入', '更多']
    confidence_kw = ['明白了', '懂了', '知道了', '搞定', '完成', '通过', '满分']
    fatigue_kw = ['累', '疲劳', '坚持', '困难', '压力', '焦虑', '紧张']

    for msg in conv_history:
        text = msg.get('message', '')
        if not text:
            continue
        if any(w in text for w in confusion_kw):
            emotion_signals['confusion'] += 1
        if any(w in text for w in frustration_kw):
            emotion_signals['frustration'] += 1
        if any(w in text for w in curiosity_kw):
            emotion_signals['curiosity'] += 1
        if any(w in text for w in confidence_kw):
            emotion_signals['confidence'] += 1
        if any(w in text for w in fatigue_kw):
            emotion_signals['fatigue'] += 1

    total_signals = sum(emotion_signals.values()) or 1
    emotion_ratios = {k: round(v / total_signals, 3) for k, v in emotion_signals.items()}

    # 风险预警判断
    alerts = []
    if emotion_ratios['frustration'] > 0.4:
        alerts.append({'level': 'high', 'type': 'frustration', 'msg': '挫败情绪较集中，建议老师介入心理疏导'})
    if emotion_ratios['fatigue'] > 0.3:
        alerts.append({'level': 'medium', 'type': 'fatigue', 'msg': '学习疲劳信号明显，建议调整学习节奏'})
    if emotion_ratios['confusion'] > 0.3 and total_msgs > 10:
        alerts.append({'level': 'medium', 'type': 'confusion', 'msg': '持续存在知识盲点，建议老师进行专题辅导'})
    if student.get('quiz_attempts', {}):
        fail_count = sum(1 for q in student.get('quiz_attempts', {}).values() if q.get('last_score', 0) < 60)
        if fail_count >= 3:
            alerts.append({'level': 'high', 'type': 'failure', 'msg': f'近 {fail_count} 次测验未及格，存在学习瓶颈'})

    # 潜在优势识别
    potentials = []
    comp = student.get('competence_analysis', {})
    for area in COMPETENCE_AREAS:
        score = comp.get(area['id'], {}).get('score', 0)
        if score >= 0.7:
            potentials.append({'area': area['name'], 'score': round(score, 2)})

    profile = {
        'student_no': student_no,
        'student_name': student.get('name', ''),
        'total_messages': total_msgs,
        'emotion_distribution': emotion_ratios,
        'emotion_signals': emotion_signals,
        'alerts': alerts,
        'potentials': potentials,
        'recommended_actions': generate_recommendations(alerts, potentials, student)
    }

    return jsonify({'success': True, 'profile': profile})


def generate_recommendations(alerts, potentials, student):
    """生成双师协同干预建议"""
    actions = []
    for alert in alerts:
        if alert['type'] == 'frustration':
            actions.append({
                'type': 'teacher_intervention',
                'priority': 'high',
                'action': '情绪疏导谈话',
                'detail': '安排老师进行一对一线上/线下谈话，了解学习困扰并给予鼓励'
            })
        elif alert['type'] == 'confusion':
            actions.append({
                'type': 'teacher_intervention',
                'priority': 'medium',
                'action': '专题辅导',
                'detail': '老师针对学生困惑领域进行集中辅导，重新讲解核心概念'
            })
        elif alert['type'] == 'fatigue':
            actions.append({
                'type': 'path_adjustment',
                'priority': 'medium',
                'action': '学习节奏调整',
                'detail': '适当减少任务量，增加复习巩固环节，关注学生身心健康'
            })
        elif alert['type'] == 'failure':
            actions.append({
                'type': 'joint_intervention',
                'priority': 'high',
                'action': '双师联合介入',
                'detail': 'AI 生成个性化复习方案 + 老师进行心理建设和方法指导'
            })

    for p in potentials[:2]:
        actions.append({
            'type': 'potential_mining',
            'priority': 'low',
            'action': f'深挖优势：{p["area"]}',
            'detail': f'学生在「{p["area"]}」表现突出（{p["score"]*100:.0f}分），可安排进阶项目或竞赛挑战'
        })

    if not actions:
        actions.append({
            'type': 'maintain',
            'priority': 'low',
            'action': '保持当前节奏',
            'detail': '学生学习状态良好，AI + 老师持续观察，定期反馈'
        })

    return actions


@app.route('/api/double-teacher/takeover', methods=['POST'])
def api_teacher_takeover():
    """一键接管：老师介入学生学习"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可使用此功能'}), 401

    data = request.get_json()
    student_no = data.get('student_no', '')
    reason = data.get('reason', '')
    intervention_type = data.get('type', 'emotional')
    note = data.get('note', '')

    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    if 'teacher_interventions' not in student:
        student['teacher_interventions'] = []

    intervention = {
        'teacher': session.get('user_id', session.get('teacher_no', '')),
        'teacher_name': session.get('user_name', ''),
        'type': intervention_type,
        'reason': reason,
        'note': note,
        'status': 'active',
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    student['teacher_interventions'].append(intervention)
    student['active_intervention'] = intervention
    save_students(students)

    return jsonify({
        'success': True,
        'intervention': intervention,
        'message': f'老师已接管学生 {student_no} 的学习支持'
    })


@app.route('/api/double-teacher/takeover/<student_no>/close', methods=['POST'])
def api_close_takeover(student_no):
    """关闭接管"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可使用此功能'}), 401

    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    if student.get('active_intervention'):
        student['active_intervention']['status'] = 'closed'
        student['active_intervention']['closed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 归档到历史
    if 'teacher_interventions' in student and student['teacher_interventions']:
        last = student['teacher_interventions'][-1]
        if last['status'] == 'active':
            last['status'] = 'closed'
            last['closed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    student.pop('active_intervention', None)
    save_students(students)

    return jsonify({'success': True, 'message': '老师已结束接管，学生回归 AI 指导模式'})


@app.route('/api/double-teacher/ai-agent/config', methods=['GET', 'POST'])
def api_ai_agent_config():
    """定制专属教学智能体（老师配置自己的 AI 助手风格）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    teacher_id = session.get('user_id', session.get('teacher_no', ''))
    configs = load_teacher_agent_configs()

    if request.method == 'POST':
        data = request.get_json()
        configs[teacher_id] = {
            'teacher_id': teacher_id,
            'teacher_name': session.get('user_name', ''),
            'agent_name': data.get('agent_name', '智学AI助教'),
            'teaching_style': data.get('teaching_style', 'supportive'),  # supportive|strict|socratic|encouraging
            'subject_focus': data.get('subject_focus', []),
            'response_length': data.get('response_length', 'medium'),  # short|medium|detailed
            'humor_level': data.get('humor_level', 'moderate'),  # low|moderate|high
            'custom_persona': data.get('custom_persona', ''),
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_teacher_agent_configs(configs)
        return jsonify({'success': True, 'config': configs[teacher_id]})

    config = configs.get(teacher_id, {
        'teacher_id': teacher_id,
        'agent_name': '智学AI助教',
        'teaching_style': 'supportive',
        'subject_focus': [],
        'response_length': 'medium',
        'humor_level': 'moderate',
        'custom_persona': ''
    })
    return jsonify({'success': True, 'config': config})


# AI 助教配置文件路径
AGENT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'agent_configs.json')


def load_teacher_agent_configs():
    try:
        if os.path.exists(AGENT_CONFIG_FILE):
            with open(AGENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception:
        return {}


def save_teacher_agent_configs(configs):
    try:
        os.makedirs(os.path.dirname(AGENT_CONFIG_FILE), exist_ok=True)
        atomic_save_json(AGENT_CONFIG_FILE, configs)
    except Exception as e:
        print(f"AI 助教配置保存失败: {e}")


@app.route('/api/double-teacher/dashboard', methods=['GET'])
def api_double_teacher_dashboard():
    """教师驾驶舱：数据驱动教学看板"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    students = load_students()
    total_students = len(students)

    # 班级统计
    class_stats = {}
    risk_alerts = []
    emotion_summary = {}

    for student in students:
        cls = student.get('class_name', '未分班')
        if cls not in class_stats:
            class_stats[cls] = {
                'student_count': 0,
                'avg_score': 0,
                'completion_rate': 0
            }
        class_stats[cls]['student_count'] += 1

        # 计算班级平均分
        comp = student.get('competence_analysis', {})
        if comp:
            scores = [v.get('score', 0) for v in comp.values()]
            avg = sum(scores) / len(scores) if scores else 0
            class_stats[cls]['avg_score'] += avg

        # 完成率
        weekly = student.get('weekly_tasks', {})
        total_t = 0
        done_t = 0
        for wk in weekly.values():
            for t in wk.get('tasks', []):
                total_t += 1
                if t.get('completed'):
                    done_t += 1
        class_stats[cls]['completion_rate'] += (done_t / total_t) if total_t > 0 else 0

    # 计算平均
    for cls in class_stats:
        cs = class_stats[cls]
        if cs['student_count'] > 0:
            cs['avg_score'] = round(cs['avg_score'] / cs['student_count'], 3)
            cs['completion_rate'] = round(cs['completion_rate'] / cs['student_count'], 3)

    # 风险预警收集
    for student in students:
        # 失败锁定
        locks = student.get('task_locks', {})
        locked_tasks = [tid for tid, lock in locks.items() if lock.get('locked')]
        if locked_tasks:
            risk_alerts.append({
                'student_no': student.get('student_no'),
                'student_name': student.get('name'),
                'type': 'failure_lock',
                'level': 'high',
                'msg': f'{student.get("name")} 有 {len(locked_tasks)} 个任务被锁定'
            })

        # 连续测验不及格
        quiz = student.get('quiz_attempts', {})
        fail_count = sum(1 for q in quiz.values() if q.get('last_score', 0) < 60)
        if fail_count >= 3:
            risk_alerts.append({
                'student_no': student.get('student_no'),
                'student_name': student.get('name'),
                'type': 'quiz_failure',
                'level': 'high',
                'msg': f'{student.get("name")} 连续 {fail_count} 次测验不及格'
            })

        # 长时间未学习
        if student.get('target_set_time'):
            try:
                days_since = (datetime.now() - datetime.strptime(student.get('target_set_time', '')[:10], "%Y-%m-%d")).days
                if days_since > 14 and fail_count > 0:
                    risk_alerts.append({
                        'student_no': student.get('student_no'),
                        'student_name': student.get('name'),
                        'type': 'learning_stagnation',
                        'level': 'medium',
                        'msg': f'{student.get("name")} 学习停滞超过 {days_since} 天'
                    })
            except:
                pass

    return jsonify({
        'success': True,
        'total_students': total_students,
        'class_stats': class_stats,
        'risk_alerts': risk_alerts[:20],  # 最多返回20条
        'alert_count': len(risk_alerts),
        'agent_configs': list(load_teacher_agent_configs().keys())
    })


def _student_metrics(student):
    """计算单个学生的能力分(0-100)、周任务完成率、提问数"""
    comp = student.get('competence_analysis', {})
    if comp:
        scores = [v.get('score', 0) for v in comp.values()]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    else:
        avg_score = 0.0

    weekly = student.get('weekly_tasks', {})
    total_t = done_t = 0
    for wk in weekly.values():
        for t in wk.get('tasks', []):
            total_t += 1
            if t.get('completed'):
                done_t += 1
    completion = round(done_t / total_t * 100, 1) if total_t > 0 else 0.0

    return {
        'id': student.get('id', ''),
        'name': student.get('name', '未命名'),
        'student_no': student.get('student_no', ''),
        'avg_score': avg_score,
        'completion_rate': completion,
        'total_questions': student.get('total_questions', 0),
        'last_login': student.get('last_login', ''),
        'created_at': student.get('created_at', '')
    }


@app.route('/api/double-teacher/class-detail', methods=['GET'])
def api_double_teacher_class_detail():
    """教师驾驶舱：查看某个班级的学生明细"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    class_name = request.args.get('class_name', '')
    students = load_students()
    members = [s for s in students if s.get('class_name', '未分班') == class_name]
    details = [_student_metrics(s) for s in members]

    # 按最近登录时间倒序（未登录的排最后）
    details.sort(key=lambda d: d.get('last_login') or '', reverse=True)

    avg_score = round(sum(d['avg_score'] for d in details) / len(details), 1) if details else 0.0
    avg_completion = round(sum(d['completion_rate'] for d in details) / len(details), 1) if details else 0.0
    total_questions = sum(d['total_questions'] for d in details)

    return jsonify({
        'success': True,
        'class_name': class_name,
        'student_count': len(details),
        'avg_score': avg_score,
        'avg_completion': avg_completion,
        'total_questions': total_questions,
        'students': details
    })


@app.route('/api/double-teacher/class-ai-analysis', methods=['GET'])
def api_double_teacher_class_ai_analysis():
    """教师驾驶舱：对整个班级进行AI综合分析并提供教学建议"""
    if not session.get('authenticated') or session.get('role') != 'teacher':
        return jsonify({'error': '仅老师可访问'}), 401

    class_name = request.args.get('class_name', '')
    students = load_students()
    members = [s for s in students if s.get('class_name', '未分班') == class_name]

    if not members:
        return jsonify({'success': False, 'error': '该班级暂无学生'})

    # 汇总班级数据
    total_q = sum(s.get('total_questions', 0) for s in members)
    # 12维平均掌握度
    class_comp = {}
    for area in COMPETENCE_AREAS:
        aid = area['id']
        scores = []
        for s in members:
            comp = s.get('competence_analysis', {})
            d = comp.get(aid, {})
            if d.get('count', 0) > 0:
                scores.append(d.get('score', 0))
        avg = round(sum(scores) / len(scores) * 100) if scores else 0
        class_comp[area['name']] = {'avg_pct': avg, 'interacted': len(scores), 'total': len(members)}

    # 找出班级薄弱领域（平均分最低的3个）
    sorted_weak = sorted(class_comp.items(), key=lambda x: x[1]['avg_pct'])[:5]
    # 找出班级优势领域（平均分最高的3个）
    sorted_strong = sorted(class_comp.items(), key=lambda x: x[1]['avg_pct'], reverse=True)[:5]

    # 学习活跃度分布
    active = sum(1 for s in members if s.get('total_questions', 0) > 0)
    inactive = len(members) - active

    # 构建每个学生的简短摘要
    student_summaries = []
    for s in members:
        comp = s.get('competence_analysis', {})
        comp_scores = [(a['name'], comp.get(a['id'], {}).get('score', 0) * 100) for a in COMPETENCE_AREAS]
        comp_scores.sort(key=lambda x: x[1])
        weakest = comp_scores[0][0] if comp_scores else '无'
        student_summaries.append(
            f"- {s.get('name','未命名')}（{s.get('student_no','无学号')}）：提问{s.get('total_questions',0)}次，最薄弱：{weakest}"
        )
    student_text = '\n'.join(student_summaries)

    weak_text = '\n'.join(f"- {k}：平均掌握度 {v['avg_pct']}%（{v['interacted']}/{v['total']}人有互动）" for k, v in sorted_weak)
    strong_text = '\n'.join(f"- {k}：平均掌握度 {v['avg_pct']}%（{v['interacted']}/{v['total']}人有互动）" for k, v in sorted_strong)

    prompt = f"""你是一名通信工程专业的资深教学督导。请根据以下班级整体数据，给出班级学情分析和具体教学建议。

【班级概况】
班级：{class_name}
学生总数：{len(members)}
累计提问总数：{total_q}
活跃学生（有提问）：{active} 人
未活跃学生：{inactive} 人

【班级各维度平均掌握度（薄弱领域 Top5）】
{weak_text}

【班级各维度平均掌握度（优势领域 Top5）】
{strong_text}

【班级学生个体摘要】
{student_text}

请输出结构化分析，严格按以下格式返回（不要添加多余说明）：

【班级学情概述】
（用2-3句话概括班级整体学习状态、活跃度、知识掌握情况）

【共性问题】
（列出2-4个班级普遍存在的知识薄弱点或学习问题，结合数据说明）

【教学建议】
（给出4-6条具体可执行的教学建议，针对共性问题，要结合通信工程专业特点，例如：哪些知识点需要重点复习、是否需要安排专项练习、如何提升学生互动积极性等）

【重点关注学生】
（列出需要重点关注的学生及原因，如长期未活跃、某维度掌握度极低等）

【后续教学重点】
（用1-2句话说明下一阶段教学应重点关注的方向）"""

    system_content = '你是通信工程专业的资深教学督导，擅长根据班级整体学情数据给出精准、实用的教学建议。分析要客观，建议要具体可执行。'

    return analysis_sse_generator(system_content, prompt, max_tokens=1500)


# ====================== 口语化交互排障 ======================
@app.route('/api/weekly-tasks/<task_id>/troubleshoot', methods=['POST'])
def api_troubleshoot(task_id):
    """口语化交互排障：用户用自然语言描述故障，AI辅助定位"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    # 查找任务
    task = None
    weekly_tasks = student.get('weekly_tasks', {})
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            if t['id'] == task_id:
                task = t
                break
        if task:
            break

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    area_id = task.get('area_id', '')
    area_name = task.get('area', '')
    data = request.get_json() or {}
    user_desc = data.get('description', '')

    if not user_desc.strip():
        return jsonify({'error': '请描述故障现象'}), 400

    # 获取该领域的故障场景作为参考
    fault_scenarios = FAULT_SCENARIOS.get(area_id, [])
    fault_ref = "\n".join([f"- {f['name']}: {f['description']}" for f in fault_scenarios])

    # 构建AI提示词
    system_prompt = f"""你是一位资深通信工程师排障助手。用户正在处理「{area_name}」领域的故障。
当前领域可能涉及的故障场景：
{fault_ref}

请根据用户用自然语言描述的故障现象，给出：
1. 故障定位：最可能的故障点和原因
2. 排查步骤：建议的排查方法（最多3步）
3. 安全提示：操作前需要注意的安全事项

回答要简洁、专业、可操作。用中文回答。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_desc}
    ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
        "model": MODEL_FLASH,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 1500,
        "stream": False,
        "enable_thinking": False
    }

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        result = resp.json()
        ai_reply = result.get('choices', [{}])[0].get('message', {}).get('content', '排障分析生成失败')

        # 保存排障对话到学生记录
        if 'troubleshoot_history' not in student:
            student['troubleshoot_history'] = {}
        if task_id not in student['troubleshoot_history']:
            student['troubleshoot_history'][task_id] = []
        student['troubleshoot_history'][task_id].append({
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'user_description': user_desc,
            'ai_analysis': ai_reply
        })
        save_students(students)

        return jsonify({
            'success': True,
            'analysis': ai_reply,
            'area_name': area_name,
            'fault_scenarios': [f['name'] for f in fault_scenarios]
        })
    except Exception as e:
        # 降级：基于规则的关键词匹配
        analysis = f"【基于规则的初步分析】\n"
        analysis += f"您描述的故障现象：{user_desc}\n\n"

        # 关键词匹配
        kw_map = AREA_KNOWLEDGE_MAP.get(area_id, [])
        matched_faults = []
        for f in fault_scenarios:
            for kw in kw_map:
                if kw in user_desc or kw in f['description']:
                    matched_faults.append(f)
                    break

        if matched_faults:
            analysis += "可能匹配的故障场景：\n"
            for f in matched_faults:
                analysis += f"  • {f['name']}：{f['description']}\n"
            analysis += f"\n建议排查步骤：\n"
            analysis += "1. 先检查告警日志确认故障范围\n"
            analysis += "2. 使用测试仪器定位故障点\n"
            analysis += "3. 按操作规范进行修复并验证\n"
        else:
            analysis += "未能自动匹配故障场景，建议：\n"
            analysis += "1. 检查设备指示灯和告警面板\n"
            analysis += "2. 查看系统日志定位异常\n"
            analysis += "3. 联系资深工程师协助排查\n"

        analysis += "\n⚠️ 操作前请确保已断开相关电源并做好安全防护。"

        return jsonify({
            'success': True,
            'analysis': analysis,
            'area_name': area_name,
            'fault_scenarios': [f['name'] for f in fault_scenarios],
            'fallback': True
        })


# ====================== 失败锁定机制 ======================
@app.route('/api/weekly-tasks/<task_id>/lock-status', methods=['GET'])
def api_lock_status(task_id):
    """检查任务是否被锁定（前置自检未通过或测验失败次数过多）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    quiz_attempts = student.get('quiz_attempts', {}).get(task_id, {})
    attempt_count = quiz_attempts.get('attempt_count', 0)
    passed = quiz_attempts.get('passed', False)

    # 锁定规则：连续失败3次以上且未通过，锁定5分钟冷却
    locked = False
    lock_reason = ""
    lock_remaining = 0

    if not passed and attempt_count >= 3:
        last_attempt_str = quiz_attempts.get('passed_at', '')
        # 检查是否有锁定记录
        lock_info = student.get('task_locks', {}).get(task_id, {})
        if lock_info.get('locked', False):
            locked = True
            lock_reason = lock_info.get('reason', '操作权限已被锁定')
            locked_at = lock_info.get('locked_at', '')
            try:
                locked_time = datetime.strptime(locked_at, "%Y-%m-%d %H:%M:%S")
                elapsed = (datetime.now() - locked_time).total_seconds()
                cooldown = 300  # 5分钟冷却
                lock_remaining = max(0, int(cooldown - elapsed))
                if lock_remaining == 0:
                    # 冷却结束，解锁
                    locked = False
                    if 'task_locks' not in student:
                        student['task_locks'] = {}
                    student['task_locks'][task_id] = {'locked': False}
                    save_students(students)
            except:
                locked = False

    return jsonify({
        'success': True,
        'locked': locked,
        'lock_reason': lock_reason if locked else '',
        'lock_remaining_seconds': lock_remaining,
        'attempt_count': attempt_count,
        'passed': passed
    })


@app.route('/api/weekly-tasks/<task_id>/unlock', methods=['POST'])
def api_unlock_task(task_id):
    """解锁任务（管理员或冷却结束后自动调用）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    if 'task_locks' not in student:
        student['task_locks'] = {}
    student['task_locks'][task_id] = {'locked': False, 'unlocked_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    save_students(students)

    return jsonify({'success': True, 'message': '任务已解锁'})


# ====================== 闭环评价（事故复盘 + AI施压模拟） ======================
@app.route('/api/weekly-tasks/<task_id>/evaluation', methods=['POST'])
def api_task_evaluation(task_id):
    """闭环评价：事故复盘 + AI施压模拟考核"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    student_no = session.get('student_no', '')
    students = load_students()
    student = next((s for s in students if s.get('student_no') == student_no), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    # 查找任务
    task = None
    weekly_tasks = student.get('weekly_tasks', {})
    for week_key, week_data in weekly_tasks.items():
        for t in week_data.get('tasks', []):
            if t['id'] == task_id:
                task = t
                break
        if task:
            break

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    area_id = task.get('area_id', '')
    area_name = task.get('area', '')
    quiz_attempts = student.get('quiz_attempts', {}).get(task_id, {})
    fault_name = quiz_attempts.get('fault_scenario_name', '')
    fault_scenarios = FAULT_SCENARIOS.get(area_id, [])
    fault_detail = next((f for f in fault_scenarios if f['name'] == fault_name), None)

    data = request.get_json() or {}
    mode = data.get('mode', 'review')  # review or stress_test
    user_response = data.get('response', '')

    if mode == 'stress_test':
        # AI施压模拟：AI扮演考官提出尖锐问题，用户回答后AI评估
        stress_question = data.get('question', '')
        system_prompt = f"""你是一位严格的通信工程考核官，正在对学员进行压力面试。
学员正在处理「{area_name}」领域的故障「{fault_name}」。
故障描述：{fault_detail['description'] if fault_detail else '未知故障'}

学员之前的安全操作评分：{quiz_attempts.get('safety_score', 100)}/100
学员之前的知识评分：{quiz_attempts.get('final_score', 0)}/100

请根据学员的回答进行评价，包括：
1. 回答评分（0-100）
2. 不足之处
3. 改进建议

评价要严格、专业、有针对性。用中文回答。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"考官问题：{stress_question}\n\n学员回答：{user_response}"}
        ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        payload = {
            "model": MODEL_FLASH,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 1000,
            "stream": False,
            "enable_thinking": False
        }

        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
            result = resp.json()
            ai_reply = result.get('choices', [{}])[0].get('message', {}).get('content', '评价生成失败')
            return jsonify({
                'success': True,
                'mode': 'stress_test',
                'evaluation': ai_reply,
                'question': stress_question
            })
        except Exception as e:
            return jsonify({
                'success': True,
                'mode': 'stress_test',
                'evaluation': 'AI评估服务暂时不可用，但您的回答已记录。考官建议：在处理该类故障时，需要更全面地考虑安全规范和操作步骤的完整性。',
                'question': stress_question,
                'fallback': True
            })

    else:
        # 事故复盘模式
        review_data = {
            'success': True,
            'mode': 'review',
            'task_title': task.get('title', ''),
            'area_name': area_name,
            'fault_scenario': {
                'name': fault_name,
                'description': fault_detail['description'] if fault_detail else '',
                'level': fault_detail['level'] if fault_detail else 'info'
            },
            'timeline': [],
            'root_cause': '',
            'lessons_learned': [],
            'improvement_actions': []
        }

        # 构建时间线
        if quiz_attempts:
            review_data['timeline'].append({
                'phase': '故障注入',
                'event': f'系统注入故障「{fault_name}」',
                'detail': fault_detail['description'] if fault_detail else ''
            })
            review_data['timeline'].append({
                'phase': '前置自检',
                'event': '安全操作规范确认',
                'detail': f"安全评分：{quiz_attempts.get('safety_score', 100)}/100"
            })
            review_data['timeline'].append({
                'phase': '知识测验',
                'event': f"答题得分：{quiz_attempts.get('final_score', 0)}/100",
                'detail': f"尝试 {quiz_attempts.get('attempt_count', 0)} 次"
            })

        # 根因分析
        if fault_detail:
            review_data['root_cause'] = fault_detail['description']

        # 经验教训
        safety_score = quiz_attempts.get('safety_score', 100)
        attempt_count = quiz_attempts.get('attempt_count', 0)
        final_score = quiz_attempts.get('final_score', 0)

        if safety_score < 100:
            review_data['lessons_learned'].append('安全操作规范执行不够严格，部分建议检查项未确认')
        if attempt_count > 1:
            review_data['lessons_learned'].append(f'知识掌握不够扎实，经过 {attempt_count} 次尝试才通过')
        if final_score >= 90 and safety_score == 100 and attempt_count == 1:
            review_data['lessons_learned'].append('表现优异，一次通过且安全操作规范完整')
        if not review_data['lessons_learned']:
            review_data['lessons_learned'].append('整体表现合格，建议继续巩固相关知识点')

        # 改进建议
        review_data['improvement_actions'].append('定期复习「{}」领域知识，保持技能熟练度'.format(area_name))
        if safety_score < 100:
            review_data['improvement_actions'].append('加强安全操作培训，养成确认每项检查的习惯')
        if attempt_count > 2:
            review_data['improvement_actions'].append('针对薄弱知识点进行专项学习')

        # 生成AI施压模拟问题
        stress_questions = []
        if fault_detail:
            stress_questions.append(f"如果「{fault_name}」在凌晨3点复发，且备件用完，你会如何应急处理？")
            stress_questions.append(f"在处理该故障时，如果同时出现另一个紧急告警，你如何排优先级？")
            stress_questions.append(f"请详细解释该故障的根因机理，以及为什么你的修复方案是有效的？")

        review_data['stress_test_questions'] = stress_questions

        # 保存评价记录
        if 'task_evaluations' not in student:
            student['task_evaluations'] = {}
        student['task_evaluations'][task_id] = review_data
        save_students(students)

        return jsonify(review_data)


@app.route('/survey-page')
def survey_page():
    """问卷页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('survey.html')


@app.route('/weekly-tasks-page')
def weekly_tasks_page():
    """每周任务卡页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('weekly_tasks.html')


# 启动时初始化招聘调度器（后台线程，不阻塞Flask启动）
def init_job_scheduler_async():
    if JOB_MODULE_AVAILABLE:
        try:
            import threading
            import fcntl
            # 用文件锁确保只有一个 gunicorn worker 启动调度器，避免并发写文件
            lock_file = open(os.path.join(DATA_DIR, '.scheduler.lock'), 'w')
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                print("[调度器] 另一个 worker 已持有锁，跳过启动")
                return

            def _init():
                _time.sleep(2)
                job_scheduler.init_scheduler()
            threading.Thread(target=_init, daemon=True).start()
            print("[调度器] 本 worker 获得锁，调度器已启动")
        except ImportError:
            # Windows 下没有 fcntl，直接启动（开发环境单 worker）
            import threading
            def _init():
                _time.sleep(2)
                job_scheduler.init_scheduler()
            threading.Thread(target=_init, daemon=True).start()
        except Exception as e:
            print(f"招聘调度器初始化失败: {e}")


import time as _time
init_job_scheduler_async()


# ====================== AI模拟面试 + 面试案例知识库路由 ======================

@app.route('/mock-interview-page')
def mock_interview_page():
    """AI模拟面试页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    resp = app.make_response(render_template('mock_interview.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/interview-cases-page')
def interview_cases_page():
    """面试案例知识库页面"""
    if not session.get('authenticated'):
        return render_template('login.html')
    return render_template('interview_cases.html')


# ---------- 面试案例知识库 API ----------

@app.route('/api/interview-cases')
def api_interview_cases_list():
    """案例列表（支持筛选）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    cases = load_interview_cases()
    company = request.args.get('company', '')
    position = request.args.get('position', '')
    itype = request.args.get('interview_type', '')
    keyword = request.args.get('keyword', '').strip()
    if company:
        cases = [c for c in cases if c.get('company') == company]
    if position:
        cases = [c for c in cases if c.get('position') == position]
    if itype:
        cases = [c for c in cases if c.get('interview_type') == itype]
    if keyword:
        cases = [c for c in cases if keyword in c.get('description', '') or keyword in c.get('position', '') or
                 keyword in c.get('company', '') or any(keyword in t for t in c.get('tags', []))]
    result = []
    for c in cases:
        result.append({
            'id': c.get('id'), 'company': c.get('company'), 'position': c.get('position'),
            'interview_type': c.get('interview_type'), 'difficulty': c.get('difficulty'),
            'description': c.get('description'), 'tags': c.get('tags', []),
            'question_count': len(c.get('questions', [])), 'created_at': c.get('created_at', '')
        })
    return jsonify({'success': True, 'cases': result, 'total': len(result)})


@app.route('/api/interview-cases/seed', methods=['POST'])
def api_interview_cases_seed():
    """教师初始化/重置预置案例"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    save_interview_cases(SEED_INTERVIEW_CASES)
    return jsonify({'success': True, 'message': f'已初始化 {len(SEED_INTERVIEW_CASES)} 个预置案例'})


@app.route('/api/interview-cases/<case_id>')
def api_interview_case_detail(case_id):
    """案例详情"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    case = next((c for c in load_interview_cases() if c.get('id') == case_id), None)
    if not case:
        return jsonify({'error': '案例不存在'}), 404
    return jsonify({'success': True, 'case': case})


@app.route('/api/interview-cases', methods=['POST'])
def api_interview_case_create():
    """教师新增案例"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    body = request.get_json() or {}
    cases = load_interview_cases()
    new_case = {
        'id': f"case_{uuid.uuid4().hex[:8]}",
        'company': body.get('company', '').strip(),
        'position': body.get('position', '').strip(),
        'interview_type': body.get('interview_type', '技术面'),
        'difficulty': body.get('difficulty', '中等'),
        'description': body.get('description', ''),
        'questions': body.get('questions', []),
        'tags': body.get('tags', []),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'created_by': session.get('username', 'teacher'),
    }
    cases.append(new_case)
    save_interview_cases(cases)
    return jsonify({'success': True, 'case': new_case})


@app.route('/api/interview-cases/<case_id>', methods=['PUT'])
def api_interview_case_update(case_id):
    """教师修改案例"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    body = request.get_json() or {}
    cases = load_interview_cases()
    case = next((c for c in cases if c.get('id') == case_id), None)
    if not case:
        return jsonify({'error': '案例不存在'}), 404
    for k in ['company', 'position', 'interview_type', 'difficulty', 'description', 'questions', 'tags']:
        if k in body:
            case[k] = body[k]
    case['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_interview_cases(cases)
    return jsonify({'success': True, 'case': case})


@app.route('/api/interview-cases/<case_id>', methods=['DELETE'])
def api_interview_case_delete(case_id):
    """教师删除案例"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    cases = load_interview_cases()
    new_cases = [c for c in cases if c.get('id') != case_id]
    if len(new_cases) == len(cases):
        return jsonify({'error': '案例不存在'}), 404
    save_interview_cases(new_cases)
    return jsonify({'success': True})


# ---------- 模拟面试 API ----------

@app.route('/api/mock-interview/start', methods=['POST'])
def api_mock_interview_start():
    """开始面试（SSE流式返回面试官开场白）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    # 允许 teacher/admin 也能参加（便于体验/演示），非 student 角色使用默认占位
    student_no = session.get('student_no', '') if session.get('role') == 'student' else '0000000000000'
    student_name = session.get('student_name', '') if session.get('role') == 'student' else session.get('student_name') or '访客'
    interviewer_is_teacher = session.get('role') != 'student'
    body = request.get_json() or {}
    company = body.get('company', '自定义企业')
    position = body.get('position', '通信工程师')
    interview_type = body.get('interview_type', '技术面')
    difficulty = body.get('difficulty', '中等')
    comp = _get_student_competence_vector(student_no)
    case_list = _get_cases_for_interview(company, position, interview_type)
    case_questions = []
    for c in case_list:
        case_questions.extend(c.get('questions', []))
    system_prompt = _build_interviewer_system_prompt(
        student_name, company, position, interview_type, difficulty,
        comp.get('vector', {}), {
            'projects': comp.get('projects', []),
            'certifications': comp.get('certifications', []),
            'internship': comp.get('internship')
        }, case_questions)
    interview_id = f"int_{uuid.uuid4().hex[:8]}"
    records = load_interview_records()
    record = {
        'id': interview_id, 'student_no': student_no, 'student_name': student_name,
        'target_company': company, 'target_position': position,
        'interview_type': interview_type, 'difficulty': difficulty,
        'status': 'in_progress', 'messages': [],
        'system_prompt': system_prompt, 'case_questions': case_questions,
        'started_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    records.append(record)
    save_interview_records(records)
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": "请开始面试。"}]
    payload = {"model": MODEL_FLASH, "messages": messages, "temperature": 0.7, "max_tokens": 800, "stream": True, "enable_thinking": False}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

    def generate(interview_id=interview_id):
        yield f"data: {json.dumps({'interview_id': interview_id}, ensure_ascii=False)}\n\n"
        full_response = ""
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
            if resp.status_code != 200:
                yield f"data: {json.dumps({'error': f'AI请求失败: {resp.status_code}'}, ensure_ascii=False)}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                try:
                    chunk_json = json.loads(data)
                    choices = chunk_json.get('choices') or []
                    if choices:
                        chunk = choices[0].get('delta', {}).get('content', '')
                        if chunk:
                            full_response += chunk
                            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    continue
        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'AI请求超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'AI请求出错: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            if full_response:
                recs = load_interview_records()
                for r in recs:
                    if r['id'] == interview_id:
                        r['messages'].append({'role': 'interviewer', 'content': full_response,
                                              'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                        break
                save_interview_records(recs)
            yield "data: [DONE]\n\n"

    return Response(generate(), content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})


@app.route('/api/mock-interview/chat', methods=['POST'])
def api_mock_interview_chat():
    """面试对话（SSE流式返回面试官回复）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    body = request.get_json() or {}
    interview_id = body.get('interview_id', '')
    student_message = body.get('message', '').strip()
    if not student_message:
        return jsonify({'error': '消息不能为空'}), 400
    records = load_interview_records()
    record = next((r for r in records if r['id'] == interview_id), None)
    if not record:
        return jsonify({'error': '面试记录不存在'}), 404
    # 老师/访客：允许操作自己 start 的记录（匹配默认占位学号）
    my_no = session.get('student_no', '') if session.get('role') == 'student' else '0000000000000'
    if record.get('student_no') != my_no and session.get('role') != 'teacher':
        return jsonify({'error': '无权操作'}), 403
    if record['status'] != 'in_progress':
        return jsonify({'error': '面试已结束'}), 400
    record['messages'].append({'role': 'student', 'content': student_message,
                               'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
    save_interview_records(records)
    system_prompt = record.get('system_prompt', '')
    messages = [{"role": "system", "content": system_prompt}]
    for msg in record['messages']:
        if msg['role'] == 'interviewer':
            messages.append({"role": "assistant", "content": msg['content']})
        elif msg['role'] == 'student':
            messages.append({"role": "user", "content": msg['content']})
    payload = {"model": MODEL_FLASH, "messages": messages, "temperature": 0.7, "max_tokens": 800, "stream": True, "enable_thinking": False}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

    def generate(interview_id=interview_id):
        full_response = ""
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
            if resp.status_code != 200:
                yield f"data: {json.dumps({'error': f'AI请求失败: {resp.status_code}'}, ensure_ascii=False)}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                try:
                    chunk_json = json.loads(data)
                    choices = chunk_json.get('choices') or []
                    if choices:
                        chunk = choices[0].get('delta', {}).get('content', '')
                        if chunk:
                            full_response += chunk
                            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    continue
        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'AI请求超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'AI请求出错: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            if full_response:
                recs = load_interview_records()
                for r in recs:
                    if r['id'] == interview_id:
                        r['messages'].append({'role': 'interviewer', 'content': full_response,
                                              'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
                        break
                save_interview_records(recs)
            yield "data: [DONE]\n\n"

    return Response(generate(), content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})


@app.route('/api/mock-interview/end', methods=['POST'])
def api_mock_interview_end():
    """结束面试（SSE流式生成评分报告）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    body = request.get_json() or {}
    interview_id = body.get('interview_id', '')
    records = load_interview_records()
    record = next((r for r in records if r['id'] == interview_id), None)
    if not record:
        return jsonify({'error': '面试记录不存在'}), 404
    # 老师也能结束
    my_no = session.get('student_no', '') if session.get('role') == 'student' else '0000000000000'
    if record.get('student_no') != my_no and session.get('role') != 'teacher':
        return jsonify({'error': '无权操作'}), 403
    if record['status'] != 'in_progress':
        return jsonify({'error': '面试已结束'}), 400
    record['status'] = 'scoring'
    save_interview_records(records)
    system_prompt, user_prompt = _build_scoring_prompt(
        record['messages'], record['target_company'], record['target_position'],
        record['interview_type'], record.get('case_questions', []),
        _get_student_competence_vector(record['student_no']).get('vector', {}))
    payload = {"model": MODEL_FLASH,
               "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
               "temperature": 0.3, "max_tokens": 1500, "stream": True, "enable_thinking": False}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

    def generate(interview_id=interview_id):
        full_response = ""
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
            if resp.status_code != 200:
                yield f"data: {json.dumps({'error': f'AI评分请求失败: {resp.status_code}'}, ensure_ascii=False)}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                try:
                    chunk_json = json.loads(data)
                    choices = chunk_json.get('choices') or []
                    if choices:
                        chunk = choices[0].get('delta', {}).get('content', '')
                        if chunk:
                            full_response += chunk
                            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    continue
        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'AI评分超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'AI评分出错: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            if full_response:
                recs = load_interview_records()
                for r in recs:
                    if r['id'] == interview_id:
                        r['status'] = 'completed'
                        r['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        r['score_report'] = full_response
                        try:
                            json_match = re.search(r'\{.*\}', full_response, re.S)
                            if json_match:
                                result = json.loads(json_match.group())
                                r['score'] = result.get('score')
                                r['strengths'] = result.get('strengths', [])
                                r['weaknesses'] = result.get('weaknesses', [])
                                r['suggestions'] = result.get('suggestions', [])
                                r['competence_scores'] = result.get('competence_scores', {})
                        except Exception as e:
                            print(f"评分解析失败: {e}")
                        break
                save_interview_records(recs)
            yield "data: [DONE]\n\n"

    return Response(generate(), content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})


@app.route('/api/mock-interview/records')
def api_mock_interview_records():
    """面试记录列表"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    role = session.get('role', '')
    records = load_interview_records()
    if role == 'student':
        student_no = session.get('student_no', '')
        records = [r for r in records if r.get('student_no') == student_no]
    result = []
    for r in records:
        result.append({
            'id': r.get('id'), 'student_name': r.get('student_name'),
            'target_company': r.get('target_company'), 'target_position': r.get('target_position'),
            'interview_type': r.get('interview_type'), 'difficulty': r.get('difficulty'),
            'status': r.get('status'), 'score': r.get('score'),
            'rounds': len([m for m in r.get('messages', []) if m.get('role') == 'student']),
            'started_at': r.get('started_at', ''), 'completed_at': r.get('completed_at', '')
        })
    result.reverse()
    return jsonify({'success': True, 'records': result, 'total': len(result)})


@app.route('/api/mock-interview/records/<record_id>')
def api_mock_interview_record_detail(record_id):
    """面试记录详情"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    record = next((r for r in load_interview_records() if r.get('id') == record_id), None)
    if not record:
        return jsonify({'error': '记录不存在'}), 404
    if session.get('role') == 'student' and record.get('student_no') != session.get('student_no'):
        return jsonify({'error': '无权查看'}), 403
    return jsonify({'success': True, 'record': record})


@app.route('/api/mock-interview/records/<record_id>', methods=['DELETE'])
def api_mock_interview_record_delete(record_id):
    """删除面试记录"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    records = load_interview_records()
    record = next((r for r in records if r.get('id') == record_id), None)
    if not record:
        return jsonify({'error': '记录不存在'}), 404
    if session.get('role') == 'student' and record.get('student_no') != session.get('student_no'):
        return jsonify({'error': '无权删除'}), 403
    records = [r for r in records if r.get('id') != record_id]
    save_interview_records(records)
    return jsonify({'success': True})


# 初始化预置面试案例
def _init_interview_data():
    if not os.path.exists(INTERVIEW_CASES_FILE):
        save_interview_cases(SEED_INTERVIEW_CASES)
        print(f"[面试案例] 初始化预置 {len(SEED_INTERVIEW_CASES)} 个案例")
    if not os.path.exists(INTERVIEW_RECORDS_FILE):
        save_interview_records([])

_init_interview_data()


# ====================== 前沿知识实时更新模块（教学方案模块4） ======================
# 功能：权威信源抓取 → AI教学难度分级 → 前沿争议标注 → 教师审核入库 → 动态老化淘汰
def _frontier_guard():
    """统一入口校验：未登录返回 None，其余返回 role"""
    if not session.get('authenticated'):
        return None
    return session.get('role', 'student')


def _frontier_append_to_knowledge(item: Dict) -> bool:
    """把审核通过的前沿内容写入知识库（复用既有知识库链路与提示词刷新）"""
    try:
        versions = item.get('difficulty_versions') or {}
        tags = '、'.join(item.get('tags') or [])
        entry = (
            f"\n\n{'='*50}\n"
            f"【前沿知识·模块4】{item.get('title', '')}\n"
            f"来源：{item.get('source_name', '')} {item.get('published_at', '')}　标签：{tags}\n"
            f"{'='*50}\n"
            f"【本科通识版】{versions.get('undergrad', '')}\n"
            f"【工程师实战版】{versions.get('engineer', '')}\n"
        )
        if item.get('is_frontier_dispute') and item.get('discussion_question'):
            entry += (f"【前沿争议】{item.get('dispute_reason', '')}\n"
                      f"【开放讨论题】{item.get('discussion_question')}\n")
        with open(KNOWLEDGE_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        update_system_prompt()   # 重新加载知识库并刷新系统提示词
        return True
    except Exception as e:
        print(f"[前沿知识] 写入知识库失败: {e}")
        return False


@app.route('/frontier-update-page')
def frontier_update_page():
    """前沿知识更新看板（教师审核 / 学生浏览已发布内容）"""
    if not session.get('authenticated'):
        return render_template('login.html')
    if FRONTIER_MODULE_AVAILABLE:
        frontier_scheduler.autostart()   # 首次访问时懒启动定时抓取
    return render_template('frontier_update.html')


@app.route('/api/frontier/list', methods=['GET'])
def api_frontier_list():
    """前沿知识列表（学生仅可见已发布内容）"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载', 'items': []}), 503

    role = session.get('role', 'student')
    status = request.args.get('status', '')
    source_id = request.args.get('source_id', '')
    tag = request.args.get('tag', '')
    keyword = (request.args.get('keyword') or '').strip()
    only_dispute = request.args.get('dispute') == '1'

    items = frontier_crawler.load_frontier_items()
    if role != 'teacher':
        items = [i for i in items if i.get('status') == 'approved']
    elif status:
        items = [i for i in items if i.get('status') == status]
    if source_id:
        items = [i for i in items if i.get('source_id') == source_id]
    if tag:
        items = [i for i in items if tag in (i.get('tags') or [])]
    if only_dispute:
        items = [i for i in items if i.get('is_frontier_dispute')]
    if keyword:
        kw = keyword.lower()
        items = [i for i in items
                 if kw in (i.get('title') or '').lower()
                 or kw in (i.get('summary_raw') or '').lower()
                 or any(kw in t.lower() for t in (i.get('tags') or []))]

    # 排序：未过期内容在前；同组内按发布时间倒序
    items = sorted(items, key=lambda x: x.get('published_at', ''), reverse=True)
    items = sorted(items, key=lambda x: bool(x.get('expired')))
    return jsonify({'success': True, 'items': items, 'total': len(items)})


@app.route('/api/frontier/stats', methods=['GET'])
def api_frontier_stats():
    """前沿知识看板统计"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503
    items = frontier_crawler.load_frontier_items()
    role = session.get('role', 'student')
    stats = frontier_crawler.get_stats(items)
    if role != 'teacher':
        approved = [i for i in items if i.get('status') == 'approved']
        stats = frontier_crawler.get_stats(approved)
    return jsonify({'success': True, 'stats': stats,
                    'sources': [{'id': s['id'], 'name': s['name'], 'category': s['category']}
                                for s in frontier_crawler.FRONTIER_SOURCES]})


@app.route('/api/frontier/<item_id>', methods=['GET'])
def api_frontier_detail(item_id):
    """前沿知识详情"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503
    item = next((i for i in frontier_crawler.load_frontier_items() if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': '内容不存在'}), 404
    if session.get('role') != 'teacher' and item.get('status') != 'approved':
        return jsonify({'error': '无权查看'}), 403
    return jsonify({'success': True, 'item': item})


@app.route('/api/frontier/<item_id>/review', methods=['POST'])
def api_frontier_review(item_id):
    """教师审核：批准（自动入知识库）/ 驳回"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可审核'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503

    data = request.get_json() or {}
    action = data.get('action', '')
    note = data.get('note', '')
    if action not in ('approve', 'reject'):
        return jsonify({'error': 'action 仅支持 approve / reject'}), 400

    items = frontier_crawler.load_frontier_items()
    item = next((i for i in items if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': '内容不存在'}), 404

    item['review_note'] = note
    item['reviewed_by'] = session.get('student_name') or 'teacher'
    item['reviewed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    added_to_kb = False
    if action == 'approve':
        item['status'] = 'approved'
        added_to_kb = _frontier_append_to_knowledge(item)
        item['added_to_kb'] = added_to_kb
    else:
        item['status'] = 'rejected'
        item['expired'] = False
        item['weight'] = 0.0

    frontier_crawler.save_frontier_items(items)
    return jsonify({
        'success': True, 'status': item['status'], 'added_to_kb': added_to_kb,
        'message': ('已批准并同步至知识库' if added_to_kb else
                    ('已批准（知识库写入失败，请重试）' if action == 'approve' else '已驳回'))
    })


@app.route('/api/frontier/<item_id>/revise', methods=['POST'])
def api_frontier_revise(item_id):
    """教师在线修订内容与分级讲稿"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可修订'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503

    data = request.get_json() or {}
    items = frontier_crawler.load_frontier_items()
    item = next((i for i in items if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': '内容不存在'}), 404

    if 'title' in data and data['title'].strip():
        item['title'] = data['title'].strip()
    versions = item.setdefault('difficulty_versions', {})
    if data.get('undergrad'):
        versions['undergrad'] = data['undergrad']
    if data.get('engineer'):
        versions['engineer'] = data['engineer']
    if data.get('content'):
        item['content'] = data['content']
    if data.get('tags'):
        item['tags'] = [t.strip() for t in data['tags'] if t.strip()]
    if data.get('is_frontier_dispute') is not None:
        item['is_frontier_dispute'] = bool(data['is_frontier_dispute'])
    if data.get('dispute_reason') is not None:
        item['dispute_reason'] = data['dispute_reason']
    if data.get('discussion_question') is not None:
        item['discussion_question'] = data['discussion_question']

    item['graded_by'] = 'teacher'
    item['reviewed_by'] = session.get('student_name') or 'teacher'
    item['reviewed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 已入库内容修订后重新同步知识库
    sync_note = ''
    if item.get('status') == 'approved' and item.get('added_to_kb'):
        _frontier_append_to_knowledge(item)
        sync_note = '，已同步修订内容到知识库'

    frontier_crawler.save_frontier_items(items)
    return jsonify({'success': True, 'item': item, 'message': f'修订已保存{sync_note}'})


@app.route('/api/frontier/<item_id>/regrade', methods=['POST'])
def api_frontier_regrade(item_id):
    """重新做 AI 教学难度分级"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503

    items = frontier_crawler.load_frontier_items()
    item = next((i for i in items if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': '内容不存在'}), 404

    grade = frontier_crawler.grade_item(item.get('title', ''), item.get('summary_raw', ''), use_ai=True)
    item['difficulty_versions'] = {
        'undergrad': grade.get('undergrad', ''),
        'engineer': grade.get('engineer', ''),
    }
    item['tags'] = grade.get('tags', item.get('tags', []))
    item['key_points'] = grade.get('key_points', item.get('key_points', []))
    item['is_frontier_dispute'] = bool(grade.get('is_frontier_dispute'))
    item['dispute_reason'] = grade.get('dispute_reason', '')
    item['discussion_question'] = grade.get('discussion_question', '')
    item['content'] = grade.get('undergrad', item.get('content', ''))
    item['graded_by'] = grade.get('graded_by', 'rule')
    frontier_crawler.save_frontier_items(items)
    return jsonify({'success': True, 'item': item, 'graded_by': item['graded_by']})


@app.route('/api/frontier/<item_id>/discard', methods=['POST'])
def api_frontier_discard(item_id):
    """老化淘汰：把过期/失效内容从教学链路中剔除"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503

    data = request.get_json() or {}
    items = frontier_crawler.load_frontier_items()
    item = next((i for i in items if i.get('id') == item_id), None)
    if not item:
        return jsonify({'error': '内容不存在'}), 404

    item['status'] = 'discarded'
    item['discard_reason'] = data.get('reason', '内容老化淘汰')
    item['weight'] = 0.0
    item['reviewed_by'] = session.get('student_name') or 'teacher'
    item['reviewed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    frontier_crawler.save_frontier_items(items)
    return jsonify({'success': True, 'message': '已淘汰，不再参与教学推送'})


@app.route('/api/frontier/discussions', methods=['GET'])
def api_frontier_discussions():
    """前沿争议开放讨论题（学生可见，用于辩证思考训练）"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载', 'discussions': []}), 503

    items = frontier_crawler.load_frontier_items()
    role = session.get('role', 'student')
    if role != 'teacher':
        items = [i for i in items if i.get('status') == 'approved']
    discussions = [{
        'id': i.get('id'),
        'title': i.get('title'),
        'source_name': i.get('source_name'),
        'published_at': i.get('published_at'),
        'tags': i.get('tags', []),
        'dispute_reason': i.get('dispute_reason', ''),
        'discussion_question': i.get('discussion_question', ''),
        'undergrad': (i.get('difficulty_versions') or {}).get('undergrad', ''),
        'engineer': (i.get('difficulty_versions') or {}).get('engineer', ''),
    } for i in items if i.get('is_frontier_dispute') and i.get('discussion_question')]
    discussions.sort(key=lambda x: x.get('published_at', ''), reverse=True)
    return jsonify({'success': True, 'discussions': discussions, 'total': len(discussions)})


@app.route('/api/frontier/fetch-now', methods=['POST'])
def api_frontier_fetch_now():
    """立即抓取一次（教师触发）"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可触发抓取'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503
    try:
        stats = frontier_scheduler.frontier_scheduler.fetch_now()
        return jsonify({'success': True, 'stats': stats, 'message': f"抓取完成：新增 {stats.get('added', 0)} 条"})
    except Exception as e:
        return jsonify({'success': False, 'error': f'抓取失败: {e}'}), 500


@app.route('/api/frontier/refresh-status', methods=['POST'])
def api_frontier_refresh_status():
    """内容生命周期扫描：标记过期并降权"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可操作'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503
    config = frontier_crawler.load_frontier_config()
    items = frontier_crawler.load_frontier_items()
    changed = frontier_crawler.refresh_freshness(items, int(config.get('freshness_days', 180)))
    frontier_crawler.save_frontier_items(items)
    aging = [i for i in items if i.get('expired') and i.get('status') not in ('discarded', 'rejected')]
    return jsonify({'success': True, 'changed': changed, 'aging_count': len(aging),
                    'message': f'生命周期扫描完成，{len(aging)} 条内容已进入待淘汰队列'})


@app.route('/api/frontier/scheduler/status', methods=['GET'])
def api_frontier_scheduler_status():
    """定时抓取状态"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503
    frontier_scheduler.autostart()
    return jsonify({'success': True, 'status': frontier_scheduler.frontier_scheduler.get_status()})


@app.route('/api/frontier/config', methods=['GET'])
def api_frontier_get_config():
    """读取抓取配置"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503
    return jsonify({'success': True, 'config': frontier_crawler.load_frontier_config(),
                    'sources': [{'id': s['id'], 'name': s['name'], 'category': s['category'],
                                 'url': s['url']} for s in frontier_crawler.FRONTIER_SOURCES]})


@app.route('/api/frontier/config', methods=['POST'])
def api_frontier_update_config():
    """教师更新抓取配置与老化阈值"""
    if not _frontier_guard():
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可修改配置'}), 403
    if not FRONTIER_MODULE_AVAILABLE:
        return jsonify({'success': False, 'error': '前沿知识模块未加载'}), 503

    data = request.get_json() or {}
    config = frontier_crawler.load_frontier_config()
    if 'auto_fetch_enabled' in data:
        config['auto_fetch_enabled'] = bool(data['auto_fetch_enabled'])
    if 'ai_grading_enabled' in data:
        config['ai_grading_enabled'] = bool(data['ai_grading_enabled'])
    if 'freshness_days' in data:
        try:
            config['freshness_days'] = max(7, int(data['freshness_days']))
        except (TypeError, ValueError):
            pass
    if 'max_items_per_source' in data:
        try:
            config['max_items_per_source'] = max(1, int(data['max_items_per_source']))
        except (TypeError, ValueError):
            pass
    if data.get('sources'):
        valid_ids = [s['id'] for s in frontier_crawler.FRONTIER_SOURCES]
        config['sources'] = [s for s in data['sources'] if s in valid_ids]
    if 'fetch_interval_hours' in data:
        try:
            hours = max(1, int(data['fetch_interval_hours']))
            config['fetch_interval_hours'] = hours
            frontier_scheduler.frontier_scheduler.update_interval(hours)
        except (TypeError, ValueError):
            pass

    frontier_crawler.save_frontier_config(config)
    frontier_scheduler.frontier_scheduler.set_auto_fetch(config.get('auto_fetch_enabled', True))
    return jsonify({'success': True, 'config': config, 'message': '配置已保存'})


# 初始化前沿知识数据文件（首次运行含预置内容，无网络也能演示）
if FRONTIER_MODULE_AVAILABLE:
    frontier_crawler.init_frontier_data()


# ====================== 语音播报（多模态学习交互） ======================
TTS_API_URL = "https://api.siliconflow.cn/v1/audio/speech"
TTS_MODEL = "FunAudioLLM/CosyVoice2-0.5B"
TTS_DEFAULT_VOICE = "FunAudioLLM/CosyVoice2-0.5B:alex"


def _clean_for_speech(text: str, limit: int = 1200) -> str:
    """清理 Markdown 与链接标记，避免朗读出符号"""
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)        # 图片
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)     # 链接只保留文字
    text = re.sub(r'```[\s\S]*?```', ' 代码片段 ', text)      # 代码块
    text = re.sub(r'[#*`>|~_]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


@app.route('/api/tts/speak', methods=['POST'])
def api_tts_speak():
    """把 AI 回答合成语音（SiliconFlow 语音合成，返回 mp3 音频流）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    data = request.get_json() or {}
    text = _clean_for_speech(data.get('text') or '')
    if not text:
        return jsonify({'error': '文本为空或无法朗读'}), 400

    try:
        payload = {
            "model": TTS_MODEL,
            "input": text,
            "voice": data.get('voice') or TTS_DEFAULT_VOICE,
            "response_format": "mp3",
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
        resp = requests.post(TTS_API_URL, headers=headers, json=payload, timeout=90)
        if resp.status_code != 200:
            print(f"[语音播报] 合成失败: {resp.status_code} {resp.text[:200]}")
            return jsonify({'error': f'语音合成失败（{resp.status_code}）'}), 502
        if not resp.content:
            return jsonify({'error': '语音合成返回空音频'}), 502
        return Response(resp.content, mimetype='audio/mpeg', headers={
            'Cache-Control': 'no-store',
            'Content-Length': str(len(resp.content)),
        })
    except Exception as e:
        print(f"[语音播报] 合成异常: {e}")
        return jsonify({'error': f'语音合成异常: {e}'}), 500


# ====================== 哈希链可信成长档案接口 ======================

def _credential_lookup_profile(student_no, fallback_name=''):
    """从学生库读取姓名/班级/专业/胜任力摘要

    优先按学号匹配；对历史数据（学生记录未存学号）退化为按姓名匹配。
    """
    info = {'name': '', 'class_name': '', 'major': '', 'ability_summary': ''}
    try:
        with open(STUDENTS_FILE, 'r', encoding='utf-8') as f:
            students = json.load(f)
        if not isinstance(students, list):
            students = []
        matched = None
        for s in students:
            if isinstance(s, dict) and str(s.get('student_no') or '') == str(student_no):
                matched = s
                break
        if matched is None and fallback_name:
            for s in students:
                if not isinstance(s, dict) or s.get('student_no'):
                    continue
                if (s.get('name') or s.get('student_name')) == fallback_name:
                    matched = s
                    break
        if matched is not None:
            info['name'] = matched.get('name') or matched.get('student_name') or ''
            info['class_name'] = matched.get('class_name') or matched.get('class') or ''
            info['major'] = matched.get('major') or matched.get('professional') or ''
            ca = matched.get('competence_analysis')
            if isinstance(ca, dict) and ca:
                top = sorted(ca.items(), key=lambda x: -float(x[1] or 0))[:3]
                info['ability_summary'] = "、".join(f"{k}({v})" for k, v in top)
    except Exception as e:
        print(f"[成长档案] 读取学生信息失败: {e}")
    return info


def _credential_resolve_target():
    """解析本次操作的目标学生，返回 (student_no, profile, error)"""
    body = request.get_json(silent=True) or {}
    if session.get('role') == 'teacher':
        student_no = (str(request.args.get('student_no') or '')
                      or str(body.get('student_no') or '')).strip()
        if not student_no:
            return '', {}, '教师操作需指定 student_no'
        fallback_name = str(request.args.get('student_name') or body.get('student_name') or '').strip()
        profile = _credential_lookup_profile(student_no, fallback_name)
        if not profile['name']:
            profile['name'] = fallback_name
        return student_no, profile, None
    student_no = str(session.get('student_no') or '').strip()
    if not student_no:
        return '', {}, '当前账号未绑定学号，无法使用成长档案'
    profile = _credential_lookup_profile(student_no, session.get('student_name', ''))
    if not profile['name']:
        profile['name'] = session.get('student_name', '')
    return student_no, profile, None


@app.route('/credential-chain')
def credential_chain_page():
    """成长档案与可信证书页面（学生 / 教师）"""
    if not session.get('authenticated'):
        return redirect('/')
    if not CREDENTIAL_MODULE_AVAILABLE:
        return "成长档案模块未加载", 503
    return render_template('credential_chain.html',
                           record_types=credential_chain.RECORD_TYPES)


@app.route('/api/credential/list')
def api_credential_list():
    """成长档案记录列表 + 链概览"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    student_no, profile, error = _credential_resolve_target()
    if error:
        return jsonify({'error': error}), 400
    rec_type = (request.args.get('type') or '').strip()
    return jsonify({
        'success': True,
        'student_no': student_no,
        'profile': {
            'name': profile.get('name', ''),
            'class_name': profile.get('class_name', ''),
            'major': profile.get('major', ''),
        },
        'records': credential_chain.get_records(student_no, rec_type),
        'summary': credential_chain.get_chain_summary(student_no),
        'record_types': credential_chain.RECORD_TYPES,
    })


@app.route('/api/credential/append', methods=['POST'])
def api_credential_append():
    """追加成长记录并上链（教师录入 / 学生提交）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    student_no, profile, error = _credential_resolve_target()
    if error:
        return jsonify({'error': error}), 400

    data = request.get_json() or {}
    is_teacher = session.get('role') == 'teacher'
    source = 'teacher_manual' if is_teacher else 'student_self'
    ret = credential_chain.append_record(
        student_no,
        profile.get('name') or session.get('student_name', ''),
        str(data.get('type') or '').strip(),
        str(data.get('title') or '').strip(),
        str(data.get('detail') or '').strip(),
        value=data.get('value'),
        source=source,
        created_at=str(data.get('created_at') or '').strip(),
        student_class=profile.get('class_name', ''),
    )
    if not ret.get('ok'):
        return jsonify({'error': ret.get('error', '追加失败')}), 400
    if SECURITY_MODULE_AVAILABLE:
        security.audit('credential_append', target=f"student:{student_no}",
                       detail=f"上链「{data.get('title', '')}」（类型 {ret.get('record', {}).get('type', '')}，"
                              f"序号 {ret.get('seq')}，来源 {source}）",
                       after={'title': data.get('title', ''), 'seq': ret.get('seq')})
    return jsonify({'success': True, 'message': f"已上链（链内第 {ret.get('seq')} 条）",
                    'record': ret.get('record')})


@app.route('/api/credential/sync', methods=['POST'])
def api_credential_sync():
    """把已有业务数据（学习行为/错题/作业/面试/自评/能力测评）同步上链"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    student_no, profile, error = _credential_resolve_target()
    if error:
        return jsonify({'error': error}), 400
    ret = credential_chain.sync_from_sources(
        student_no, profile.get('name') or session.get('student_name', ''),
        student_class=profile.get('class_name', ''))
    ret['success'] = True
    ret['summary'] = credential_chain.get_chain_summary(student_no)
    return jsonify(ret)


@app.route('/api/credential/verify')
def api_credential_verify():
    """重新校验成长档案哈希链完整性"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    student_no, _profile, error = _credential_resolve_target()
    if error:
        return jsonify({'error': error}), 400
    result = credential_chain.verify_chain(student_no)
    result['success'] = True
    return jsonify(result)


@app.route('/api/credential/certificate', methods=['POST'])
def api_credential_certificate():
    """签发可信成长证书（同一链头复用已有证书）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    student_no, profile, error = _credential_resolve_target()
    if error:
        return jsonify({'error': error}), 400
    ret = credential_chain.make_certificate(
        student_no,
        extra_snapshot={
            'major': profile.get('major', ''),
            'ability_summary': profile.get('ability_summary', ''),
        })
    if not ret.get('ok'):
        return jsonify({'error': ret.get('error', '签发失败')}), 400
    ret['success'] = True
    if SECURITY_MODULE_AVAILABLE:
        cert = ret.get('certificate') or {}
        security.audit('credential_certificate', target=f"cert:{cert.get('certificate_id', '')}",
                       detail=f"为学生 {student_no} 签发可信成长证书"
                              f"（{'复用已有' if ret.get('reused') else '新签发'}，"
                              f"上链 {cert.get('record_count', 0)} 条）",
                       after={'certificate_id': cert.get('certificate_id', ''), 'student_no': student_no})
    return jsonify(ret)


@app.route('/api/credential/certificates')
def api_credential_certificates():
    """证书列表"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    student_no, _profile, error = _credential_resolve_target()
    if error:
        return jsonify({'error': error}), 400
    certs = credential_chain.get_student_certificates(student_no)
    return jsonify({'success': True, 'certificates': certs, 'count': len(certs)})


@app.route('/api/credential/overview')
def api_credential_overview():
    """教师端总览：所有学生链情况"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'teacher':
        return jsonify({'error': '仅教师可查看全局概览'}), 403
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    return jsonify({
        'success': True,
        'overview': credential_chain.stats_overview(),
        'chains': credential_chain.list_chains(),
    })


@app.route('/verify/<certificate_id>')
def credential_public_verify_page(certificate_id):
    """证书公开验真页（企业/第三方，无需登录）"""
    if not CREDENTIAL_MODULE_AVAILABLE:
        return "成长档案模块未加载", 503
    return render_template('certificate_verify.html', certificate_id=certificate_id)


@app.route('/api/credential/public-verify/<certificate_id>')
def api_credential_public_verify(certificate_id):
    """证书公开验真接口（脱敏数据 + 实时链校验）"""
    if not CREDENTIAL_MODULE_AVAILABLE:
        return jsonify({'error': '成长档案模块未加载'}), 503
    return jsonify(credential_chain.verify_certificate(certificate_id))


# 初始化成长档案数据文件
if CREDENTIAL_MODULE_AVAILABLE:
    credential_chain.init_credential_data()

# 初始化 RAG 向量索引（缺失/过期时后台重建，不阻塞启动）
if RAG_MODULE_AVAILABLE:
    try:
        _rag_init = rag_retriever.ensure_index(async_mode=True)
        print(f"[RAG] 启动检查：{_rag_init.get('message', '')}")
    except Exception as e:  # noqa: BLE001
        print(f"[RAG] 启动初始化失败: {e}")

# 初始化凭据库：把历史明文密码迁移为哈希（幂等）
if SECURITY_MODULE_AVAILABLE:
    try:
        _cred = security.init_credentials(TEACHER_ACCOUNTS, ACCESS_PASSWORD)
        print(f"[Security] 凭据库就绪：教师账号 {_cred['teachers']} 个，明文已全部哈希化")
        security.audit('password_migrate', target='data/credentials.json',
                       detail=f"启动校验凭据库，本次迁移 {_cred['migrated']} 条明文凭据",
                       actor='system', role='system', ip='localhost')
    except Exception as e:  # noqa: BLE001
        print(f"[Security] 凭据初始化失败: {e}")


# ====================== 因果故障链 + 难度自适应 ======================

@app.route('/fault-chain')
def fault_chain_page():
    """因果故障链排查实训页"""
    if not session.get('authenticated'):
        return render_template('login.html')
    if not FAULT_CHAIN_AVAILABLE:
        return "因果故障链模块未加载", 503
    return render_template('fault_chain.html',
                           role=session.get('role', 'student'),
                           levels=fault_chain.LEVEL_RULES)


@app.route('/api/fault-chain/domains', methods=['GET'])
def api_fault_chain_domains():
    """故障域列表 + 当前学生在各域的难度等级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    student_no = session.get('student_no', '')
    levels = fault_chain.get_student_levels(student_no) if student_no else {}
    domains = []
    for d, chain in fault_chain.CAUSAL_CHAINS.items():
        lv = levels.get(d, {}).get('level', 1)
        domains.append({
            'domain': d, 'label': chain['domain_label'], 'title': chain['title'],
            'symptom_brief': chain['symptom']['alarm'],
            'level': lv, 'level_label': fault_chain.LEVELS[lv],
            'level_rules': fault_chain.LEVEL_RULES[lv],
        })
    return jsonify({'success': True, 'domains': domains,
                    'levels': fault_chain.LEVELS, 'level_rules': fault_chain.LEVEL_RULES})


@app.route('/api/fault-chain/start', methods=['POST'])
def api_fault_chain_start():
    """开局：注入故障表象（学生）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'student':
        return jsonify({'error': '仅学生可参与故障排查实训'}), 403
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    domain = body.get('domain', '')
    level = int(body.get('level') or 0)
    ret = fault_chain.start_session(session.get('student_no', ''),
                                    session.get('student_name', ''), domain, level)
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    if SECURITY_MODULE_AVAILABLE and not ret.get('resumed'):
        security.audit('fault_chain_start', target=domain,
                       detail=f"开局「{ret['session']['title']}」，难度 {ret['session']['level_label']}")
    return jsonify({'success': True, 'resumed': ret.get('resumed', False),
                    'session': ret['session']})


@app.route('/api/fault-chain/test', methods=['POST'])
def api_fault_chain_test():
    """执行测试动作：确认分支展开 / 剪除分支"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    ret = fault_chain.perform_test(session.get('student_no', ''),
                                   body.get('session_id', ''), body.get('test_id', ''))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    return jsonify({'success': True, 'result': ret['result'], 'text': ret['text'],
                    'newly_revealed': ret.get('newly_revealed', []),
                    'session': ret['session']})


@app.route('/api/fault-chain/hint', methods=['POST'])
def api_fault_chain_hint():
    """获取提示（入门免费；工程师扣分；专家禁用）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    ret = fault_chain.use_hint(session.get('student_no', ''), body.get('session_id', ''))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    return jsonify({'success': True, 'hints': ret['hints'],
                    'hints_used': ret['hints_used'], 'penalty_each': ret['penalty_each'],
                    'session': ret['session']})


@app.route('/api/fault-chain/diagnose', methods=['POST'])
def api_fault_chain_diagnose():
    """提交根因诊断 + 处置方案 → 评分 + 难度变形"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    root_ids = body.get('root_ids') or []
    fix_ids = body.get('fix_ids') or []
    ret = fault_chain.diagnose(session.get('student_no', ''),
                               body.get('session_id', ''), root_ids, fix_ids)
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    sess = ret['session']
    if SECURITY_MODULE_AVAILABLE:
        security.audit('fault_chain_diagnose', target=sess['domain'],
                       detail=f"诊断得分 {ret['score']}（{ret['grade']}），"
                              f"误诊 {sess['misdiagnoses']} 次，测试 {len(sess['tests_done'])} 次")
        # 难度变形（升/降级）单独审计
        sug = sess.get('suggestion')
        if sug:
            security.audit('fault_chain_morph', target=sess['domain'],
                           detail=sug['text'], before={'level': sug['before']},
                           after={'level': sug['after']})
    return jsonify({'success': True, 'score': ret['score'], 'grade': ret['grade'],
                    'verdict': ret['verdict'], 'session': sess})


@app.route('/api/fault-chain/state', methods=['GET'])
def api_fault_chain_state():
    """会话状态查询"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    ret = fault_chain.get_session(session.get('student_no', ''),
                                  request.args.get('session_id', ''))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 404
    return jsonify({'success': True, 'session': ret['session']})


@app.route('/api/fault-chain/abandon', methods=['POST'])
def api_fault_chain_abandon():
    """放弃当前会话"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    ret = fault_chain.abandon_session(session.get('student_no', ''), body.get('session_id', ''))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    return jsonify({'success': True})


@app.route('/api/fault-chain/history', methods=['GET'])
def api_fault_chain_history():
    """成绩历史：学生看自己，教师看全部 + 概览"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    if session.get('role') == 'teacher':
        return jsonify({'success': True, 'history': fault_chain.get_history(),
                        'overview': fault_chain.stats_overview()})
    return jsonify({'success': True,
                    'history': fault_chain.get_history(session.get('student_no', ''))})


@app.route('/api/fault-chain/chat', methods=['POST'])
def api_fault_chain_chat():
    """AI 带教导师（SSE 流式，ground 在当前故障链状态，不泄露答案）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not FAULT_CHAIN_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    session_id = body.get('session_id', '')
    user_msg = (body.get('message') or '').strip()
    if not user_msg:
        return jsonify({'error': '消息不能为空'}), 400
    sess = fault_chain.get_session_raw(session_id)
    if not sess or sess.get('student_no') != session.get('student_no'):
        return jsonify({'error': '会话不存在或无权操作'}), 403

    tutor_ctx = fault_chain.build_tutor_context(sess)
    system_prompt = ("你是通信工程现场带教导师，正在带一名学生排查真实故障。\n"
                     "当前故障链状态：\n" + tutor_ctx +
                     "\n\n✨ 本回答由 AI 生成，仅供参考。")
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}]
    payload = {"model": MODEL_FLASH, "messages": messages,
               "temperature": 0.6, "max_tokens": 600, "stream": True, "enable_thinking": False}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

    def generate():
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
            if resp.status_code != 200:
                yield f"data: {json.dumps({'error': f'AI请求失败: {resp.status_code}'}, ensure_ascii=False)}\n\n"
                return
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                try:
                    chunk_json = json.loads(data)
                    choices = chunk_json.get('choices') or []
                    if choices:
                        chunk = choices[0].get('delta', {}).get('content', '')
                        if chunk:
                            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    continue
        except requests.exceptions.Timeout:
            yield f"data: {json.dumps({'error': 'AI请求超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': f'AI请求出错: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return Response(generate(), content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})


# 初始化故障链状态文件
if FAULT_CHAIN_AVAILABLE:
    fault_chain.init_fault_chain_data()


# ====================== 多故障并发优先级决策 ======================

@app.route('/multi-fault-page')
def multi_fault_page():
    """多故障并发优先级决策演练页"""
    if not session.get('authenticated'):
        return render_template('login.html')
    if not MULTI_FAULT_AVAILABLE:
        return "多故障并发决策模块未加载", 503
    return render_template('multi_fault.html',
                           role=session.get('role', 'student'),
                           level_rules=multi_fault.LEVEL_RULES)


@app.route('/api/multi-fault/info', methods=['GET'])
def api_multi_fault_info():
    """当前学生难度等级 + 规则说明"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not MULTI_FAULT_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    student_no = session.get('student_no', '')
    lv = multi_fault.get_student_level(student_no) if student_no else 1
    return jsonify({'success': True, 'level': lv, 'level_label': multi_fault.LEVELS[lv],
                    'levels': multi_fault.LEVELS, 'level_rules': multi_fault.LEVEL_RULES})


@app.route('/api/multi-fault/start', methods=['POST'])
def api_multi_fault_start():
    """开局：动态生成并发故障工单"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if session.get('role') != 'student':
        return jsonify({'error': '仅学生可参与多故障演练'}), 403
    if not MULTI_FAULT_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    level = int(body.get('level') or 0)
    ret = multi_fault.start_session(session.get('student_no', ''),
                                    session.get('student_name', ''), level)
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    if SECURITY_MODULE_AVAILABLE and not ret.get('resumed'):
        security.audit('multi_fault_start', target='multi_fault',
                       detail=f"开局多故障并发演练，难度 {ret['session']['level_label']}")
    return jsonify({'success': True, 'resumed': ret.get('resumed', False),
                    'session': ret['session']})


@app.route('/api/multi-fault/state', methods=['GET'])
def api_multi_fault_state():
    """轮询会话状态（专家级突发事件在开局75秒后通过此接口揭示）"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not MULTI_FAULT_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    ret = multi_fault.get_session(session.get('student_no', ''),
                                  request.args.get('session_id', ''))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    return jsonify({'success': True, 'session': ret['session']})


@app.route('/api/multi-fault/submit', methods=['POST'])
def api_multi_fault_submit():
    """提交排障顺序 + 资源分配，仿真评分"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not MULTI_FAULT_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    session_id = body.get('session_id', '')
    ret = multi_fault.submit(session.get('student_no', ''), session_id,
                             body.get('order') or [], body.get('assignments') or {},
                             body.get('event_action', ''),
                             int(body.get('event_position', -1)))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    if SECURITY_MODULE_AVAILABLE:
        security.audit('multi_fault_submit', target=session_id,
                       detail=f"得分 {ret['score']}（{ret['grade']}），"
                              f"业务损失 {ret['verdict']['student_loss']} / 最优 {ret['verdict']['optimal_loss']}")
        sug = ret.get('suggestion')
        if sug:
            security.audit('multi_fault_morph', target=session.get('student_no', ''),
                           detail=f"难度 {sug['before']}→{sug['after']}（{sug['type']}）")
    return jsonify({'success': True, 'score': ret['score'], 'grade': ret['grade'],
                    'verdict': ret['verdict'], 'suggestion': ret.get('suggestion')})


@app.route('/api/multi-fault/abandon', methods=['POST'])
def api_multi_fault_abandon():
    """放弃当前会话"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not MULTI_FAULT_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    body = request.get_json() or {}
    ret = multi_fault.abandon_session(session.get('student_no', ''), body.get('session_id', ''))
    if not ret.get('ok'):
        return jsonify({'success': False, 'error': ret.get('error')}), 400
    return jsonify({'success': True})


@app.route('/api/multi-fault/history', methods=['GET'])
def api_multi_fault_history():
    """成绩历史：学生看自己，教师看全部 + 概览"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    if not MULTI_FAULT_AVAILABLE:
        return jsonify({'success': False, 'error': '模块未加载'}), 503
    if session.get('role') == 'teacher':
        return jsonify({'success': True, 'history': multi_fault.get_history(),
                        'overview': multi_fault.stats_overview()})
    return jsonify({'success': True,
                    'history': multi_fault.get_history(session.get('student_no', ''))})


# 初始化多故障状态文件
if MULTI_FAULT_AVAILABLE:
    multi_fault.init_multi_fault_data()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False, threaded=True)
