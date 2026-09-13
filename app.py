from flask import Flask, render_template, request, jsonify, Response, session, send_from_directory, redirect
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
MODEL_NAME = "Pro/moonshotai/Kimi-K2.6"

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
        with open(UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
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
        with open(WRONG_QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
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
        with open(LEARNING_RECORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
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
        with open(PPT_METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存PPT元数据失败: {e}")


# ====================== PPT 转图片预览（大文件秒开） ======================
PPT_PREVIEW_DIR = os.path.join(UPLOAD_FOLDER, "previews")
_converting_lock = threading.Lock()
_converting = set()


def convert_pptx_to_images(download_name: str):
    """后台将PPTX逐页转为JPEG图片，转换完成回写元数据 preview_ready/page_count"""
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
            print(f"PPT预览转换跳过，源文件不存在: {download_name}")
            return
        out_dir = os.path.join(PPT_PREVIEW_DIR, stem)
        os.makedirs(out_dir, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            # pptx -> pdf（LibreOffice 无头模式；25.x 不支持 --no-sandbox；profile独立避免并发锁）
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
        metadata = load_ppt_metadata()
        for m in metadata:
            if m.get('download_name') == download_name:
                m['preview_ready'] = True
                m['page_count'] = len(pages)
                m['preview_dir'] = f'previews/{stem}'
        save_ppt_metadata(metadata)
        print(f"PPT预览图转换完成: {download_name} -> {len(pages)}页")
    except Exception as e:
        print(f"PPT预览图转换失败 {download_name}: {e}")
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
    """检查内容是否已存在于知识库中（相似度超过90%）"""
    kb_content = load_knowledge()
    if not kb_content:
        return False
    
    new_hash = hash(new_content.strip())
    
    for existing_entry in kb_content.split('='*50):
        if existing_entry.strip():
            existing_hash = hash(existing_entry.strip())
            similarity = 1 - abs(new_hash - existing_hash) / max(abs(new_hash), abs(existing_hash), 1)
            if similarity > 0.9:
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
        with open(SEARCH_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
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
        with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(students, f, ensure_ascii=False, indent=2)
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
        with open(CLASSES_FILE, "w", encoding="utf-8") as f:
            json.dump(classes, f, ensure_ascii=False, indent=2)
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
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(notifications, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"通知数据保存失败: {e}")


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


def generate_ai_analysis(student: Dict) -> Dict:
    """调用大模型对学生进行综合能力分析，返回优缺点与学习建议"""
    name = student.get('name', '该学生')

    # 1) 对话历史（只取最近30条，避免上下文过长）
    conv_history = student.get('conversation_history') or []
    recent_conv = conv_history[-30:]
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

    # 3) 错题本
    wrong_qs = load_wrong_questions()
    student_wrong = [q for q in wrong_qs if q.get('student_name') == name][-15:]
    wrong_text = '\n'.join(
        f"- [{q.get('knowledge_point','未分类')}] {str(q.get('question',''))[:100]}"
        for q in student_wrong
    ) if student_wrong else '（暂无错题记录）'

    # 4) 学习记录（题目/实训）
    records = load_learning_records()
    student_records = records.get(name, [])[-30:]
    # 按活动类型统计
    type_counts = {}
    for r in student_records:
        t = r.get('activity_type', 'other')
        type_counts[t] = type_counts.get(t, 0) + 1
    rec_summary = '、'.join(f"{t}:{c}次" for t, c in type_counts.items()) or '（暂无学习记录）'
    rec_detail = '\n'.join(
        f"- [{r.get('timestamp','')}] {r.get('activity_type','')} {r.get('knowledge_point','')} 得分:{r.get('score','-')}"
        for r in student_records[-10:]
    )

    total_q = student.get('total_questions', len([m for m in conv_history if m.get('is_question')]))

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

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "你是通信工程专业的资深教学导师，擅长根据学生的学习数据给出精准、实用的能力分析和学习建议。回答要专业但不晦涩，建议要具体可执行。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False
        }
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200:
            result = resp.json()
            if "choices" in result and result["choices"]:
                content = result["choices"][0]["message"]["content"].strip()
                return {'success': True, 'analysis': content, 'student': name}
        return {'success': False, 'error': f'AI分析失败: {resp.status_code}'}
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'AI分析超时，请稍后重试'}
    except Exception as e:
        return {'success': False, 'error': f'AI分析出错: {str(e)}'}


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
def generate_system_prompt(query: str, mode: str = 'fast') -> str:
    """根据用户查询动态生成系统提示词，集成知识图谱上下文和意图识别"""
    kg_results = search_knowledge_graph(query)
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
{knowledge_content if knowledge_content else "（知识库为空）"}
{kg_context}

要求：
1. 优先使用知识库和相关知识点回答
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


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    password = data.get('password', '')
    role = data.get('role', 'student')
    student_no = data.get('student_no', '')
    student_name = data.get('student_name', '')
    class_name = data.get('class_name', '')
    
    if role == 'teacher':
        # 老师登录：需要验证账号密码
        if TEACHER_ACCOUNTS.get(student_name) == password:
            session['authenticated'] = True
            session['role'] = 'teacher'
            session['student_name'] = student_name
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': '老师账号或密码错误'})
    
    # 学生登录：使用统一访问密码
    if password == ACCESS_PASSWORD:
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

        return jsonify({'success': True, 'is_new_user': is_new_user, 'student_name': student_name})
    else:
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
    
    if class_name:
        class_obj['name'] = class_name
    
    save_classes(classes)
    return jsonify({'success': True, 'class': class_obj})


@app.route('/api/classes/<int:class_id>', methods=['DELETE'])
def delete_class(class_id):
    """删除班级"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
    if session.get('role') != 'teacher':
        return jsonify({'error': '只有老师才能删除班级'}), 403
    
    classes = load_classes()
    classes = [c for c in classes if c['id'] != class_id]
    save_classes(classes)
    
    return jsonify({'success': True})


@app.route('/api/classes/<int:class_id>/students', methods=['GET'])
def get_class_students(class_id):
    """获取班级成员列表"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401
    
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
        
        if stream:
            # 流式输出 - 记录所有对话到日志
            return Response(
                stream_generator(headers, messages, temperature, max_tokens, user_message),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache, no-transform',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            # 非流式输出
            payload = {
                "model": MODEL_NAME,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
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
    with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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


def stream_generator(headers, messages, temperature, max_tokens, search_query=None):
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
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
        filename = secure_filename(file.filename)
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
            threading.Thread(target=convert_pptx_to_images, args=(download_name,), daemon=True).start()
        else:
            os.remove(file_path)
        
        history = load_upload_history()
        history.append({
            'id': str(uuid.uuid4()),
            'filename': filename,
            'extracted_length': len(extracted_text),
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'uploader': session.get('username') or session.get('student_name') or 'unknown',
            'status': 'success',
            'chapters': chapters,
            'knowledge_points': knowledge_points
        })
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

    # 合并PPT预览信息（供教师端在线预览使用）
    ppt_by_name = {p['filename']: p for p in load_ppt_metadata()}
    for h in history:
        p = ppt_by_name.get(h.get('filename'))
        if p:
            h['download_name'] = p.get('download_name', '')
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

    # 2. 移除PPT文件、预览图目录和元数据
    meta = load_ppt_metadata()
    removed = [m for m in meta if m.get('filename') == filename]
    save_ppt_metadata([m for m in meta if m.get('filename') != filename])
    for m in removed:
        fpath = os.path.abspath(os.path.join(UPLOAD_FOLDER, m.get('download_name', '')))
        if fpath.startswith(os.path.abspath(UPLOAD_FOLDER)) and os.path.exists(fpath):
            os.remove(fpath)
        pd_rel = m.get('preview_dir', '')
        if pd_rel.startswith('previews/'):
            pdir = os.path.abspath(os.path.join(UPLOAD_FOLDER, pd_rel))
            if pdir.startswith(os.path.abspath(os.path.join(UPLOAD_FOLDER, 'previews'))):
                import shutil
                shutil.rmtree(pdir, ignore_errors=True)

    # 3. 移除上传历史条目
    save_upload_history([h for h in history if h.get('id') != entry_id])

    # 4. 刷新系统提示词中的知识库内容
    update_system_prompt()

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
        with open(CUSTOM_EXERCISE_FILE, "w", encoding="utf-8") as f:
            json.dump(exercises, f, ensure_ascii=False, indent=2)
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
        return redirect('/login-page')
    return render_template('scenario.html')


@app.route('/scenario-demo')
def scenario_demo():
    """剧情演绎演示页面"""
    if not session.get('authenticated'):
        return redirect('/login-page')
    return render_template('scenario_demo.html')


# ====================== AI 自动生成场景实训 ======================

SCENARIO_GEN_PROMPT = """你是一个交互式实训课程设计专家。请根据用户提供的场景主题与要求，生成一套完整的交互式虚拟仿真实训流程。

【最重要】所有内容必须紧扣用户提供的场景主题！不要默认生成基站/5G相关内容。如果用户说的是"数据中心机房设计"，就生成数据中心的内容；如果用户说的是"光纤铺设"，就生成光纤铺设的内容。选项、问题、勘察表字段等都必须与用户主题直接相关。

你必须输出**纯JSON**（不要markdown代码块、不要解释文字），格式如下：
{"steps": [...], "scoreMax": 数字}

steps数组包含5-7个步骤，每个步骤的 type 只能是以下6种之一。严格遵守每种类型的字段格式：

══════ 1. text 类型（背景/说明） ══════
{"type":"text", "title":"步骤标题", "label":"步骤标签", "content":"HTML格式的内容，可用<b>加粗</b>和<br>换行", "nextText":"下一步"}

══════ 2. choice 类型（单选岗位/角色） ══════
{"type":"choice", "title":"步骤标题", "label":"步骤标签", "intro":"HTML引导语", "options":[{"name":"选项名","sub":"描述","good":true,"feedback":"✅ 选对的反馈"}, {"name":"选项名","sub":"描述","feedback":"❌ 选错的反馈"}]}
注意：只有一个选项的 good 为 true。

══════ 3. quiz 类型（多步选择） ══════
{"type":"quiz", "title":"步骤标题", "label":"步骤标签", "subSteps":[
  {"q":"问题文本", "options":[{"name":"选项1","sub":"描述"},{"name":"选项2","sub":"描述"}], "correct": 正确索引(从0开始)},
  {"q":"多选问题", "options":[{"name":"选项1","sub":"描述"},{"name":"选项2","sub":"描述"}], "multi":true, "required": 必选项索引}
]}
注意：subSteps有3-5个，correct是数字索引。每个选项的name和sub必须与用户主题相关。

══════ 4. siteselect 类型（地图选址） ══════
{"type":"siteselect", "title":"步骤标题", "label":"步骤标签", "intro":"HTML引导语", "spots":[
  {"name":"位置1","ok":true,"x":46,"y":38,"feedback":"✅ 正确选址的详细分析"},
  {"name":"位置2","ok":false,"x":78,"y":30,"feedback":"❌ 错误选址的原因分析"}
], "correctIdx":0}
注意：x在5-90之间，y在15-75之间，只有一个 ok 为 true，correctIdx是正确位置的索引。位置名称和分析内容必须与用户主题相关。

══════ 5. survey 类型（勘察表填写） ══════
{"type":"survey", "title":"步骤标题", "label":"步骤标签", "intro":"HTML引导语", "tabs":["标签1","标签2","标签3"], "plan":[[["字段名","参考值"],["字段名","参考值"]],[["字段名","参考值"]],[["字段名","参考值"]]], "fields":[
  {"tab":0,"key":"字段名","type":"input","ph":"占位提示"},
  {"tab":0,"key":"字段名","type":"select","opts":["选项1","选项2"]},
  {"tab":0,"key":"字段名","type":"input","ph":"点击测量","measure":{"device":"laser","icon":"🔴","name":"测量设备名","value":"测量值"}}
]}
注意：tabs有2-3个，plan是二维数组对应每个tab的参考数据，fields中tab索引对应tabs。所有字段名和参考值必须与用户主题相关。

══════ 6. design 类型（最终设计选择） ══════
{"type":"design", "title":"步骤标题", "label":"步骤标签", "intro":"HTML引导语", "groups":[
  {"q":"问题1","options":["选项A","选项B","选项C"],"correct": 正确索引},
  {"q":"问题2","options":["选项A","选项B","选项C"],"correct": 正确索引}
], "result":"最终方案的HTML总结"}
注意：问题和选项必须与用户主题相关。

══════ 评分规则 ══════
scoreMax = quiz的subSteps数(每题1分) + siteselect的2分 + survey中有measure字段的数量(每项1分) + design的groups数(每项1分)

══════ 步骤顺序建议 ══════
text(背景) → choice(岗位选择) → quiz(测试/摸测) → text(参数查询) → siteselect(选址) → survey(勘察表) → design(最终设计)

══════ 重要约束 ══════
1. 【最重要】所有内容必须与用户提供的场景主题紧密相关，严禁默认生成基站/5G内容
2. 每个选项的feedback要详细、有教育意义
3. 内容用<b>标签强调关键词，用<br>换行
4. 输出必须是合法JSON，不要包含注释、不要用单引号
5. 不要输出```json```代码块标记，直接输出JSON原文
"""


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
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4000,
            "stream": False
        }

        print(f"[场景生成] 主题={topic}, 开始调用AI...")
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)

        if resp.status_code != 200:
            print(f"[场景生成] AI请求失败: {resp.status_code} - {resp.text[:300]}")
            return jsonify({'error': f'AI请求失败: {resp.status_code}'}), 500

        answer = resp.json()["choices"][0]["message"]["content"].strip()

        # 去除可能的 ```json / ``` 包裹
        if answer.startswith('```'):
            answer = re.sub(r'^```(?:json)?\s*', '', answer)
            answer = re.sub(r'\s*```$', '', answer)

        try:
            result = json.loads(answer)
        except json.JSONDecodeError:
            # 尝试提取第一个 { 到最后一个 }
            s = answer.find('{')
            e = answer.rfind('}')
            if s >= 0 and e > s:
                result = json.loads(answer[s:e + 1])
            else:
                return jsonify({'error': 'AI返回的JSON格式无法解析', 'raw': answer[:500]}), 500

        steps = result.get('steps', [])
        score_max = result.get('scoreMax', 0)

        if not steps or not isinstance(steps, list):
            return jsonify({'error': 'AI生成的实训步骤为空或格式错误'}), 500

        # 安全校验：确保每个step有type字段
        for i, st in enumerate(steps):
            if not isinstance(st, dict) or 'type' not in st:
                return jsonify({'error': f'第{i + 1}步缺少type字段'}), 500

        print(f"[场景生成] 成功！生成 {len(steps)} 步, 满分 {score_max}")
        return jsonify({'steps': steps, 'scoreMax': score_max})

    except requests.Timeout:
        return jsonify({'error': 'AI请求超时，请重试'}), 504
    except Exception as e:
        print(f"[场景生成] 异常: {e}")
        return jsonify({'error': f'生成失败: {str(e)}'}), 500


@app.route('/exercise-page')
def exercise_page():
    """互动式练习页面"""
    if not session.get('authenticated'):
        return redirect('/login-page')
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
    """一键AI个性化分析：综合对话历史+错题+学习记录，生成优缺点与学习建议"""
    if not session.get('authenticated'):
        return jsonify({'error': '请先登录'}), 401

    students = load_students()
    student = next((s for s in students if s['id'] == student_id), None)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    if session.get('role') != 'teacher' and not _student_belongs_to_session(student):
        return jsonify({'error': '无权查看其他学生的报告'}), 403

    analysis = generate_ai_analysis(student)
    return jsonify(analysis)


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
        with open(AGENT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(configs, f, ensure_ascii=False, indent=2)
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

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": "你是通信工程专业的资深教学督导，擅长根据班级整体学情数据给出精准、实用的教学建议。分析要客观，建议要具体可执行。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2500,
            "stream": False
        }
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200:
            result = resp.json()
            if "choices" in result and result["choices"]:
                content = result["choices"][0]["message"]["content"].strip()
                return jsonify({'success': True, 'analysis': content, 'class_name': class_name})
        return jsonify({'success': False, 'error': f'AI分析失败: {resp.status_code}'})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'AI分析超时，请稍后重试'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'AI分析出错: {str(e)}'})


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
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 1500,
        "stream": False
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
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 1000,
            "stream": False
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
            def _init():
                _time.sleep(2)
                job_scheduler.init_scheduler()
            threading.Thread(target=_init, daemon=True).start()
        except Exception as e:
            print(f"招聘调度器初始化失败: {e}")


import time as _time
init_job_scheduler_async()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
