import json
import os
import random
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

JOB_DATA_FILE = "job_recruitments.json"
JOB_CONFIG_FILE = "job_config.json"

COMMUNICATION_KEYWORDS = [
    "通信工程", "通信", "电信", "通讯", "5G", "4G", "LTE", "NR",
    "无线", "射频", "RF", "天线", "基站", "网络优化", "网优",
    "传输", "核心网", "交换", "数据通信", "光通信", "光纤",
    "华为", "中兴", "爱立信", "诺基亚", "中国移动", "中国联通", "中国电信",
    "FPGA", "DSP", "嵌入式", "硬件工程师", "电子信息",
    "信号处理", "通信原理", "物联网", "车联网", "卫星通信"
]

JOB_SOURCES = [
    {"id": "zhaopin", "name": "智联招聘", "url": "https://www.zhaopin.com"},
    {"id": "51job", "name": "前程无忧", "url": "https://www.51job.com"},
    {"id": "boss", "name": "BOSS直聘", "url": "https://www.zhipin.com"},
    {"id": "liepin", "name": "猎聘网", "url": "https://www.liepin.com"},
    {"id": "lagou", "name": "拉勾网", "url": "https://www.lagou.com"}
]

# 通信企业官网招聘数据源（方案2）
ENTERPRISE_SITES = [
    {
        "id": "huawei",
        "name": "华为招聘官网",
        "url": "https://career.huawei.com",
        "search_url": "https://career.huawei.com/reccampportal/services/portal/portaluser/searchJobList",
        "type": "json_api",
        "keywords_match": ["通信", "无线", "射频", "5G", "网络", "嵌入式", "FPGA", "硬件", "算法", "软件"]
    },
    {
        "id": "zte",
        "name": "中兴招聘官网",
        "url": "https://job.zte.com.cn",
        "search_url": "https://job.zte.com.cn/api/job/list",
        "type": "json_api",
        "keywords_match": ["通信", "无线", "射频", "5G", "嵌入式", "硬件", "软件", "算法"]
    },
    {
        "id": "china_mobile",
        "name": "中国移动招聘",
        "url": "https://hr.10086.cn",
        "search_url": "https://hr.10086.cn/api/jobList",
        "type": "json_api",
        "keywords_match": ["通信", "网络", "5G", "传输", "核心网", "无线"]
    },
    {
        "id": "china_telecom",
        "name": "中国电信招聘",
        "url": "https://www.chinatelecom.com.cn",
        "search_url": "https://www.chinatelecom.com.cn/recruit/joblist",
        "type": "html",
        "keywords_match": ["通信", "网络", "5G", "传输", "云计算"]
    },
    {
        "id": "china_unicom",
        "name": "中国联通招聘",
        "url": "https://hr.chinaunicom.cn",
        "search_url": "https://hr.chinaunicom.cn/api/jobList",
        "type": "json_api",
        "keywords_match": ["通信", "网络", "5G", "传输", "无线"]
    },
    {
        "id": "datang",
        "name": "大唐电信招聘",
        "url": "https://www.datanggroup.cn",
        "search_url": "https://www.datanggroup.cn/careers",
        "type": "html",
        "keywords_match": ["通信", "无线", "芯片", "嵌入式", "5G"]
    },
    {
        "id": "fiberhome",
        "name": "烽火通信招聘",
        "url": "https://www.fiberhome.com",
        "search_url": "https://www.fiberhome.com/careers/jobs",
        "type": "html",
        "keywords_match": ["通信", "光通信", "传输", "网络", "光纤"]
    },
    {
        "id": "hytera",
        "name": "海能达招聘",
        "url": "https://www.hytera.com",
        "search_url": "https://www.hyera.com/cn-cn/careers",
        "type": "html",
        "keywords_match": ["通信", "无线", "射频", "嵌入式", "硬件"]
    }
]

# 通信行业招聘网站导航
RECRUITMENT_WEBSITES = [
    {
        "id": "huawei",
        "name": "华为技术有限公司",
        "logo": "🔴",
        "url": "https://career.huawei.com",
        "search_url": "https://career.huawei.com/reccampportal/portal5/job-list.html",
        "description": "华为校招/社招官网，搜索通信、无线、射频等岗位",
        "tags": ["通信", "5G", "芯片", "云"],
        "type": "企业官网"
    },
    {
        "id": "zte",
        "name": "中兴通讯",
        "logo": "🟦",
        "url": "https://job.zte.com.cn",
        "search_url": "https://job.zte.com.cn/campus/cn/search",
        "description": "中兴通讯招聘官网，搜索通信工程师、无线网络等岗位",
        "tags": ["通信", "网络", "无线", "传输"],
        "type": "企业官网"
    },
    {
        "id": "china_mobile",
        "name": "中国移动",
        "logo": "🟢",
        "url": "https://hr.10086.cn",
        "search_url": "https://hr.10086.cn/recruit/campus",
        "description": "中国移动招聘官网，搜索网络、通信、5G等岗位",
        "tags": ["通信", "网络", "5G", "核心网"],
        "type": "企业官网"
    },
    {
        "id": "china_telecom",
        "name": "中国电信",
        "logo": "🔵",
        "url": "https://campus.chinatelecom.com.cn",
        "search_url": "https://campus.chinatelecom.com.cn/recruit/position",
        "description": "中国电信校招官网，搜索通信、网络、云网等岗位",
        "tags": ["通信", "网络", "5G", "云计算"],
        "type": "企业官网"
    },
    {
        "id": "china_unicom",
        "name": "中国联通",
        "logo": "🔷",
        "url": "https://campus.chinaunicom.com.cn",
        "search_url": "https://campus.chinaunicom.com.cn/recruit",
        "description": "中国联通校招官网，搜索通信、网络、无线等岗位",
        "tags": ["通信", "网络", "5G", "无线"],
        "type": "企业官网"
    },
    {
        "id": "ericsson",
        "name": "爱立信",
        "logo": "🟥",
        "url": "https://www.ericsson.com.cn",
        "search_url": "https://www.ericsson.com.cn/careers",
        "description": "爱立信中国招聘官网，搜索通信网络、5G等岗位",
        "tags": ["通信", "5G", "网络", "基站"],
        "type": "企业官网"
    },
    {
        "id": "nokia",
        "name": "诺基亚",
        "logo": "⚪",
        "url": "https://www.nokia.com/cn-zh",
        "search_url": "https://www.nokia.com/cn-zh/careers",
        "description": "诺基亚中国招聘，搜索通信基础设施岗位",
        "tags": ["通信", "网络", "5G", "光纤"],
        "type": "企业官网"
    },
    {
        "id": "fiberhome",
        "name": "烽火通信",
        "logo": "🟨",
        "url": "https://www.fiberhome.com",
        "search_url": "https://www.fiberhome.com/careers",
        "description": "烽火通信招聘官网，搜索光通信、传输等岗位",
        "tags": ["光通信", "传输", "网络", "光纤"],
        "type": "企业官网"
    },
    {
        "id": "hytera",
        "name": "海能达",
        "logo": "🟧",
        "url": "https://www.hytera.com",
        "search_url": "https://www.hytera.com/cn-cn/careers",
        "description": "海能达通信招聘，搜索对讲机、通信终端等岗位",
        "tags": ["通信", "无线", "射频", "硬件"],
        "type": "企业官网"
    },
    {
        "id": "datang",
        "name": "大唐电信",
        "logo": "🟩",
        "url": "https://www.datanggroup.cn",
        "search_url": "https://www.datanggroup.cn/careers",
        "description": "大唐电信集团招聘，搜索芯片、通信等岗位",
        "tags": ["芯片", "通信", "嵌入式", "5G"],
        "type": "企业官网"
    },
    {
        "id": "h3c",
        "name": "新华三",
        "logo": "🔺",
        "url": "https://www.h3c.com",
        "search_url": "https://www.h3c.com/cn/About_H3C/Careers",
        "description": "新华三技术招聘，搜索网络、通信、云计算等岗位",
        "tags": ["网络", "通信", "云计算", "路由器"],
        "type": "企业官网"
    },
    {
        "id": "ruijie",
        "name": "锐捷网络",
        "logo": "🦌",
        "url": "https://www.ruijie.com.cn",
        "search_url": "https://www.ruijie.com.cn/about/careers",
        "description": "锐捷网络招聘，搜索网络设备、通信等岗位",
        "tags": ["网络", "通信", "交换机", "路由器"],
        "type": "企业官网"
    },
    {
        "id": "zhipin",
        "name": "BOSS直聘",
        "logo": "💼",
        "url": "https://www.zhipin.com",
        "search_url": "https://www.zhipin.com/web/geek/job?query=通信工程&city=100010000",
        "description": "综合招聘平台，搜索通信工程师岗位",
        "tags": ["综合", "通信", "工程师"],
        "type": "综合平台"
    },
    {
        "id": "51job",
        "name": "前程无忧",
        "logo": "📋",
        "url": "https://www.51job.com",
        "search_url": "https://search.51job.com/list/000000,000000,0000,00,9,99,通信工程,2,1.html",
        "description": "前程无忧招聘，搜索通信工程相关岗位",
        "tags": ["综合", "通信", "工程师"],
        "type": "综合平台"
    },
    {
        "id": "liepin",
        "name": "猎聘",
        "logo": "🎯",
        "url": "https://www.liepin.com",
        "search_url": "https://www.liepin.com/zhaopin/?key=通信工程",
        "description": "猎聘网，搜索通信工程师中高端岗位",
        "tags": ["综合", "中高端", "通信"],
        "type": "综合平台"
    },
    {
        "id": "lagou",
        "name": "拉勾网",
        "logo": "🎨",
        "url": "https://www.lagou.com",
        "search_url": "https://www.lagou.com/wn/jobs?kd=通信工程",
        "description": "拉勾网，搜索互联网+通信岗位",
        "tags": ["互联网", "通信", "技术"],
        "type": "综合平台"
    },
    {
        "id": "official_test",
        "name": "国考/省考",
        "logo": "🏛️",
        "url": "http://bm.scs.gov.cn",
        "search_url": "http://bm.scs.gov.cn/kl2026/position/positions",
        "description": "国家公务员局，搜索通信工程相关的公务员岗位",
        "tags": ["公务员", "事业单位", "通信"],
        "type": "公职类"
    }
]

# 聚合数据API配置（企业招聘信息查询 API ID: 852）
JUHE_API_URL = "https://apis.juhe.cn/api_credit/query852"

# 通信行业重点企业列表（用于按企业名查询招聘信息）
COMMUNICATION_COMPANIES = [
    "华为技术有限公司",
    "中兴通讯股份有限公司",
    "中国移动通信集团有限公司",
    "中国电信集团有限公司",
    "中国联合网络通信集团有限公司",
    "爱立信（中国）有限公司",
    "诺基亚通信（上海）有限公司",
    "大唐电信科技股份有限公司",
    "烽火通信科技股份有限公司",
    "上海贝尔股份有限公司",
    "京信通信技术（广州）有限公司",
    "摩比天线技术（深圳）有限公司",
    "国民技术股份有限公司",
    "海能达通信股份有限公司",
    "北京信威通信技术股份有限公司",
    "杭州华三通信技术有限公司",
    "锐捷网络股份有限公司",
    "迈普通信技术股份有限公司",
    "高新兴科技集团股份有限公司",
    "紫光国芯微电子股份有限公司",
    "大疆创新科技有限公司",
    "科大讯飞股份有限公司",
    "海康威视数字技术股份有限公司",
    "大华股份有限公司",
    "启明信息技术股份有限公司"
]

THIRD_PARTY_APIS = [
    {
        "id": "juhe",
        "name": "聚合数据-企业招聘查询",
        "url": JUHE_API_URL,
        "type": "get",
        "needs_key": True,
        "key_param": "key",
        "params": {
            "key": "key",
            "name": "企业名称",
            "nametype": "1",
            "pageIndex": "1"
        },
        "free_quota": 100,
        "description": "通过企业名称查询该企业的招聘信息"
    }
]

MOCK_COMPANIES = [
    "华为技术有限公司", "中兴通讯股份有限公司", "中国移动通信集团",
    "中国电信集团有限公司", "中国联合网络通信集团", "爱立信(中国)有限公司",
    "诺基亚通信(上海)有限公司", "大唐电信科技股份有限公司", "烽火通信科技股份有限公司",
    "上海贝尔股份有限公司", "京信通信技术有限公司", "摩比天线技术有限公司",
    "国民技术股份有限公司", "紫光国芯微电子股份有限公司", "深圳海能达通信股份有限公司",
    "北京信威通信技术股份有限公司", "杭州华三通信技术有限公司", "锐捷网络股份有限公司",
    "迈普通信技术股份有限公司", "高新兴科技集团股份有限公司"
]

MOCK_JOB_TITLES = [
    "通信工程师", "5G无线网络优化工程师", "射频工程师", "核心网工程师",
    "传输工程师", "无线通信算法工程师", "基带工程师", "天线设计工程师",
    "数据通信工程师", "网络规划工程师", "通信测试工程师", "运维工程师",
    "嵌入式开发工程师", "FPGA工程师", "DSP工程师", "硬件工程师",
    "通信协议开发工程师", "物联网工程师", "车联网工程师", "通信项目经理",
    "通信技术支持工程师", "售前工程师", "售后工程师", "解决方案工程师"
]

MOCK_LOCATIONS = [
    "北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉",
    "西安", "重庆", "苏州", "东莞", "天津", "长沙", "郑州", "青岛",
    "大连", "厦门", "宁波", "合肥"
]

MOCK_SALARIES = [
    "8-12K", "10-15K", "12-20K", "15-25K", "18-30K",
    "20-35K", "25-40K", "30-50K", "15-20K·14薪", "20-30K·15薪",
    "30-50K·16薪", "50-80K·15薪"
]

MOCK_EDUCATIONS = ["大专", "本科", "硕士", "博士", "不限"]
MOCK_EXPERIENCES = ["应届毕业生", "1-3年", "3-5年", "5-10年", "10年以上", "不限"]

MOCK_JOB_DESCRIPTIONS = [
    "负责通信网络的规划、设计、优化工作，参与5G/4G网络建设项目；",
    "负责无线通信系统的算法设计与仿真，包括物理层、MAC层协议开发；",
    "负责射频电路设计与调试，包括PA、LNA、混频器等射频器件选型与设计；",
    "负责核心网设备的运维与故障排查，保障网络稳定运行；",
    "负责传输网络的规划与建设，包括SDH、OTN、PTN等设备配置；",
    "负责通信产品的测试验证，制定测试方案，编写测试报告；",
    "负责嵌入式软件的开发与调试，基于ARM/DSP平台进行通信协议栈开发；",
    "负责FPGA逻辑设计与验证，完成通信算法的硬件加速实现；",
    "负责客户技术支持，解决现场通信设备故障，提供技术培训；",
    "负责通信项目的整体管理，协调各方资源，推动项目按时交付。"
]

MOCK_JOB_REQUIREMENTS = [
    "通信工程、电子信息、计算机等相关专业本科及以上学历；",
    "熟悉3GPP协议，了解5G NR/LTE/WCDMA/GSM等通信标准；",
    "熟练使用通信测试仪器：频谱仪、信号源、示波器、网络分析仪等；",
    "精通C/C++/Python编程语言，有嵌入式开发经验者优先；",
    "熟悉TCP/IP协议栈，了解路由器、交换机等网络设备原理；",
    "具备良好的沟通能力和团队协作精神，能够承受一定的工作压力；",
    "有华为、中兴、爱立信等设备商工作经验者优先；",
    "持有通信工程师职业资格证书者优先；",
    "能够适应出差，有现场工程项目经验者优先；",
    "英语四级以上，能够阅读英文技术文档。"
]

DEFAULT_CONFIG = {
    "auto_fetch_enabled": True,
    "fetch_interval_hours": 6,
    "last_fetch_time": None,
    "keywords": COMMUNICATION_KEYWORDS[:10],
    "locations": ["北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉"],
    "sources": [s["id"] for s in JOB_SOURCES],
    "max_jobs_per_fetch": 50,
    "salary_min": None,
    "experience_level": "不限",
    "education_level": "不限",
    "fetch_mode": "all",
    "third_party_api_key": "",
    "third_party_api_provider": "juhe",
    "enterprise_sites_enabled": [s["id"] for s in ENTERPRISE_SITES],
    "enterprise_fetch_enabled": True,
    "api_fetch_enabled": False
}


def load_json_file(filepath: str, default=None):
    if default is None:
        default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default
    return default


def save_json_file(filepath: str, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_job_config() -> Dict:
    config = load_json_file(JOB_CONFIG_FILE, DEFAULT_CONFIG.copy())
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
    return config


def save_job_config(config: Dict):
    save_json_file(JOB_CONFIG_FILE, config)


def load_job_recruitments() -> List[Dict]:
    data = load_json_file(JOB_DATA_FILE, {"jobs": [], "last_updated": None})
    if isinstance(data, list):
        return data
    return data.get("jobs", [])


def save_job_recruitments(jobs: List[Dict]):
    data = {
        "jobs": jobs,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(jobs)
    }
    save_json_file(JOB_DATA_FILE, data)


def generate_job_id() -> str:
    return f"job_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


def generate_mock_jobs(count: int = 30) -> List[Dict]:
    jobs = []
    for _ in range(count):
        title = random.choice(MOCK_JOB_TITLES)
        company = random.choice(MOCK_COMPANIES)
        location = random.choice(MOCK_LOCATIONS)
        salary = random.choice(MOCK_SALARIES)
        education = random.choice(MOCK_EDUCATIONS)
        experience = random.choice(MOCK_EXPERIENCES)
        source = random.choice(JOB_SOURCES)

        desc_count = random.randint(3, 6)
        req_count = random.randint(3, 6)
        description = "".join(random.sample(MOCK_JOB_DESCRIPTIONS, desc_count))
        requirements = "".join(random.sample(MOCK_JOB_REQUIREMENTS, req_count))

        skills = random.sample(COMMUNICATION_KEYWORDS, k=random.randint(3, 8))
        tags = [location, education, experience] + random.sample(
            ["五险一金", "年终奖金", "带薪年假", "弹性工作", "定期体检", "免费班车", "员工旅游", "餐补", "交通补助", "节日福利"],
            k=random.randint(2, 5)
        )

        publish_days_ago = random.randint(0, 30)
        publish_date = (datetime.now() - timedelta(days=publish_days_ago)).strftime("%Y-%m-%d")

        job = {
            "id": generate_job_id(),
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "salary_min": parse_salary_min(salary),
            "salary_max": parse_salary_max(salary),
            "education": education,
            "experience": experience,
            "source": source["name"],
            "source_id": source["id"],
            "source_url": f"{source['url']}/job/detail/{generate_job_id()}",
            "description": description,
            "requirements": requirements,
            "skills": skills,
            "tags": tags,
            "publish_date": publish_date,
            "is_new": publish_days_ago <= 3,
            "is_hot": random.random() < 0.2,
            "is_real_data": False,
            "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "viewed": False,
            "applied": False,
            "favorite": False
        }
        jobs.append(job)

    jobs.sort(key=lambda x: x["publish_date"], reverse=True)
    return jobs


def parse_salary_min(salary_str: str) -> Optional[int]:
    try:
        match = re.search(r"(\d+)-(\d+)K", salary_str)
        if match:
            return int(match.group(1)) * 1000
    except (ValueError, AttributeError):
        pass
    return None


def parse_salary_max(salary_str: str) -> Optional[int]:
    try:
        match = re.search(r"(\d+)-(\d+)K", salary_str)
        if match:
            return int(match.group(2)) * 1000
    except (ValueError, AttributeError):
        pass
    return None


def _get_common_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/"
    }


def _normalize_job(raw_job: dict, source_name: str, source_id: str, source_url: str) -> Optional[Dict]:
    """将不同来源的原始岗位数据统一格式"""
    try:
        title = raw_job.get("title") or raw_job.get("jobName") or raw_job.get("position") or raw_job.get("name", "")
        company = raw_job.get("company") or raw_job.get("companyName") or raw_job.get("corpName") or source_name

        if not title:
            return None

        location = raw_job.get("city") or raw_job.get("location") or raw_job.get("workPlace") or raw_job.get("workLocation", "")
        if isinstance(location, list):
            location = "、".join(location)

        salary = raw_job.get("salary") or raw_job.get("salaryRange") or raw_job.get("pay") or "面议"
        if isinstance(salary, dict):
            salary = f"{salary.get('min', '')}-{salary.get('max', '')}K"

        education = raw_job.get("education") or raw_job.get("degree") or raw_job.get("degreeRequire", "不限")
        experience = raw_job.get("experience") or raw_job.get("workYear") or raw_job.get("workExp", "不限")

        description = raw_job.get("description") or raw_job.get("jobDesc") or raw_job.get("detail", "")
        requirements = raw_job.get("requirement") or raw_job.get("qualification") or ""

        skills_raw = raw_job.get("skills") or raw_job.get("tags") or raw_job.get("skillLabels", [])
        if isinstance(skills_raw, str):
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif isinstance(skills_raw, list):
            skills = skills_raw
        else:
            skills = []

        is_comm_related = False
        all_keywords = COMMUNICATION_KEYWORDS
        check_text = f"{title} {description} {' '.join(skills)}".lower()
        for kw in all_keywords:
            if kw.lower() in check_text:
                is_comm_related = True
                if not skills:
                    skills.append(kw)
                break

        if not is_comm_related:
            return None

        publish_date = raw_job.get("publishDate") or raw_job.get("updateTime") or raw_job.get("createTime", "")
        if not publish_date or len(str(publish_date)) < 8:
            publish_date = datetime.now().strftime("%Y-%m-%d")
        publish_date = str(publish_date)[:10] if len(str(publish_date)) >= 10 else str(publish_date)

        try:
            dt = datetime.strptime(publish_date, "%Y-%m-%d")
            is_new = (datetime.now() - dt).days <= 7
        except:
            is_new = True

        job = {
            "id": generate_job_id(),
            "title": title,
            "company": company,
            "location": location or "未知",
            "salary": str(salary),
            "salary_min": parse_salary_min(str(salary)),
            "salary_max": parse_salary_max(str(salary)),
            "education": education,
            "experience": experience,
            "source": source_name,
            "source_id": source_id,
            "source_url": raw_job.get("url") or raw_job.get("jobUrl") or source_url,
            "description": description,
            "requirements": requirements,
            "skills": skills[:10],
            "tags": raw_job.get("welfare") or raw_job.get("benefit") or [],
            "publish_date": publish_date,
            "is_new": is_new,
            "is_hot": raw_job.get("isHot", False) or raw_job.get("urgent", False),
            "is_real_data": True,
            "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "viewed": False,
            "applied": False,
            "favorite": False
        }
        return job
    except Exception as e:
        print(f"[招聘爬虫] 标准化岗位数据失败: {e}")
        return None


# ====================== 方案1：聚合数据API（企业招聘信息查询） ======================

def fetch_from_juhe_api(api_key: str, max_companies: int = 10) -> List[Dict]:
    """通过聚合数据企业招聘查询API获取真实招聘数据
    
    API文档: https://www.juhe.cn/docs/api/id/852
    接口地址: https://apis.juhe.cn/api_credit/query852
    """
    if not REQUESTS_AVAILABLE:
        print("[聚合数据] requests未安装")
        return []

    if not api_key:
        print("[聚合数据] 未配置API Key")
        return []

    print(f"[聚合数据] 开始获取真实招聘数据，共查询{min(max_companies, len(COMMUNICATION_COMPANIES))}家通信企业...")
    print(f"[聚合数据] API文档: https://www.juhe.cn/docs/api/id/852")

    all_jobs = []
    companies_to_query = COMMUNICATION_COMPANIES[:max_companies]

    for idx, company_name in enumerate(companies_to_query):
        try:
            params = {
                "key": api_key,
                "name": company_name,
                "nametype": "1",
                "pageIndex": "1"
            }

            response = requests.get(JUHE_API_URL, params=params, timeout=15,
                                    headers=_get_common_headers())

            if response.status_code != 200:
                print(f"[聚合数据] {company_name}: HTTP {response.status_code}")
                continue

            data = response.json()

            if data.get("reason") != "成功" or data.get("error_code") != 0:
                reason = data.get("reason", "未知错误")
                error_code = data.get("error_code", -1)
                print(f"[聚合数据] {company_name}: {error_code} - {reason}")
                if error_code in (10001, 10002, 10003):
                    print(f"[聚合数据] API Key无效或过期，请检查Key是否正确")
                    break
                continue

            result = data.get("result", {})
            job_list = result.get("data", [])
            total_count = result.get("totalCount", 0)

            if job_list:
                for raw_job in job_list:
                    job = _normalize_juhe_job(raw_job, company_name)
                    if job:
                        all_jobs.append(job)
                print(f"[聚合数据] {company_name}: 获取到{len(job_list)}条岗位 (共{total_count}条)")
            else:
                print(f"[聚合数据] {company_name}: 暂无招聘信息")

            time.sleep(1.5)

        except requests.exceptions.Timeout:
            print(f"[聚合数据] {company_name}: 请求超时")
        except Exception as e:
            print(f"[聚合数据] {company_name}: {type(e).__name__} - {str(e)[:80]}")

    print(f"[聚合数据] 共获取{len(all_jobs)}条真实招聘信息")
    return all_jobs


def _normalize_juhe_job(raw_job: dict, queried_company: str) -> Optional[Dict]:
    """将聚合数据API返回的原始数据转为标准岗位格式"""
    try:
        title = raw_job.get("position", "")
        if not title:
            return None

        company = raw_job.get("enterpriseName", queried_company)
        location = raw_job.get("workplace", "")
        salary = raw_job.get("salary", "面议")
        education = raw_job.get("education", "不限")
        experience = raw_job.get("workYears", "不限")
        description = raw_job.get("description", "")
        position_type = raw_job.get("positionType", "")
        position_label = raw_job.get("positionLabel", "")
        source_url = raw_job.get("url", "")
        publish_date = raw_job.get("punlishDate") or raw_job.get("publishDate", "")

        if not publish_date or len(str(publish_date)) < 8:
            publish_date = datetime.now().strftime("%Y-%m-%d")
        publish_date = str(publish_date)[:10]

        skills = []
        check_text = f"{title} {description} {position_label}".lower()
        for kw in COMMUNICATION_KEYWORDS:
            if kw.lower() in check_text:
                skills.append(kw)
            if len(skills) >= 8:
                break

        is_comm = bool(skills) or any(kw in f"{company} {title}" for kw in ["通信", "电信", "电子", "信息", "网络", "无线"])
        if not is_comm:
            return None

        try:
            dt = datetime.strptime(publish_date, "%Y-%m-%d")
            is_new = (datetime.now() - dt).days <= 14
        except:
            is_new = True

        tags = []
        if position_type:
            tags.append(position_type)
        if raw_job.get("recruitNum"):
            tags.append(f"招聘{raw_job['recruitNum']}")

        job = {
            "id": generate_job_id(),
            "title": title,
            "company": company,
            "location": location or "未知",
            "salary": str(salary),
            "salary_min": parse_salary_min(str(salary)),
            "salary_max": parse_salary_max(str(salary)),
            "education": education,
            "experience": experience,
            "source": company,
            "source_id": "juhe_real",
            "source_url": source_url or JUHE_API_URL,
            "description": description,
            "requirements": "",
            "skills": skills[:10],
            "tags": tags,
            "publish_date": publish_date,
            "is_new": is_new,
            "is_hot": False,
            "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "viewed": False,
            "applied": False,
            "favorite": False,
            "is_real_data": True
        }
        return job
    except Exception as e:
        print(f"[聚合数据] 数据标准化失败: {e}")
        return None


def fetch_from_third_party_api(keywords: List[str], locations: List[str],
                                max_jobs: int = 30, api_key: str = "",
                                provider: str = "juhe") -> List[Dict]:
    """兼容旧接口，实际调用fetch_from_juhe_api"""
    return fetch_from_juhe_api(api_key, max_companies=min(10, len(COMMUNICATION_COMPANIES)))


# ====================== 方案2：通信企业官网招聘爬取 ======================

def fetch_from_huawei(keywords: List[str], max_jobs: int = 15) -> List[Dict]:
    """华为招聘官网数据获取"""
    if not REQUESTS_AVAILABLE:
        return []

    print("[企业官网] 正在获取华为招聘数据...")
    jobs = []

    try:
        url = "https://career.huawei.com/svc/portal/portal5/job-list"
        headers = {
            **_get_common_headers(),
            "Content-Type": "application/json",
            "Origin": "https://career.huawei.com",
            "Referer": "https://career.huawei.com/reccampportal/portal5/job-list.html"
        }

        search_keywords = keywords[:3] if keywords else ["通信", "无线", "射频"]
        for keyword in search_keywords:
            if len(jobs) >= max_jobs:
                break

            payload = {
                "keyword": keyword,
                "currentPage": 1,
                "pageSize": 10,
                "jobType": [],
                "country": [],
                "city": [],
                "deptCode": "",
                "recruitType": "",
                "workExperience": [],
                "educational": []
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    job_list = data.get("jobList", []) or data.get("data", {}).get("jobList", [])
                    for raw_job in job_list:
                        job = _normalize_job(raw_job, "华为招聘官网", "huawei", "https://career.huawei.com")
                        if job:
                            job["company"] = "华为技术有限公司"
                            jobs.append(job)
                    print(f"[企业官网] 华为 - 关键词'{keyword}'获取到{len(job_list)}条")
                else:
                    print(f"[企业官网] 华为 - HTTP {response.status_code}")
            except Exception as e:
                print(f"[企业官网] 华为 - 关键词'{keyword}'获取失败: {e}")

            time.sleep(2)

    except Exception as e:
        print(f"[企业官网] 华为获取失败: {e}")

    return jobs[:max_jobs]


def fetch_from_enterprise_html(site: dict, keywords: List[str], max_jobs: int = 10) -> List[Dict]:
    """通过HTML页面解析获取企业招聘信息（通用方法）"""
    if not REQUESTS_AVAILABLE or not BS4_AVAILABLE:
        print(f"[企业官网] requests或bs4未安装，跳过{site['name']}")
        return []

    print(f"[企业官网] 正在获取{site['name']}招聘数据...")
    jobs = []

    try:
        headers = _get_common_headers()
        headers["Referer"] = site["url"]

        keyword = keywords[0] if keywords else "通信"
        params = {"keyword": keyword, "keywordType": "0"}

        response = requests.get(site["search_url"], params=params, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[企业官网] {site['name']} - HTTP {response.status_code}")
            return []

        content_type = response.headers.get("Content-Type", "")

        if "application/json" in content_type or response.text.strip().startswith("{"):
            data = response.json()
            job_list = data.get("data", {}).get("list", []) or data.get("data", {}).get("jobs", []) or data.get("list", [])
            if isinstance(job_list, dict):
                job_list = job_list.get("records", []) or job_list.get("rows", [])

            for raw_job in job_list:
                job = _normalize_job(raw_job, site["name"], site["id"], site["url"])
                if job:
                    jobs.append(job)

        else:
            if not BS4_AVAILABLE:
                print(f"[企业官网] bs4未安装，无法解析{site['name']}的HTML页面")
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            job_elements = soup.select(".job-item") or soup.select(".job-list-item") or \
                           soup.select("[class*='job']") or soup.select(".position-item") or \
                           soup.select(".recruit-item")

            for elem in job_elements[:max_jobs]:
                title_elem = elem.select_one(".job-title") or elem.select_one(".title") or elem.select_one("h3")
                company_elem = elem.select_one(".company-name") or elem.select_one(".company")
                location_elem = elem.select_one(".job-location") or elem.select_one(".location") or elem.select_one(".city")
                salary_elem = elem.select_one(".salary") or elem.select_one(".job-salary")
                desc_elem = elem.select_one(".job-desc") or elem.select_one(".description")

                raw_job = {
                    "title": title_elem.get_text(strip=True) if title_elem else "",
                    "company": company_elem.get_text(strip=True) if company_elem else site["name"].replace("招聘", ""),
                    "city": location_elem.get_text(strip=True) if location_elem else "",
                    "salary": salary_elem.get_text(strip=True) if salary_elem else "面议",
                    "description": desc_elem.get_text(strip=True) if desc_elem else "",
                    "url": site["url"]
                }

                if raw_job["title"]:
                    matched = False
                    for kw in site.get("keywords_match", []):
                        if kw in raw_job["title"] or kw in raw_job.get("description", ""):
                            matched = True
                            break
                    if matched:
                        job = _normalize_job(raw_job, site["name"], site["id"], site["url"])
                        if job:
                            jobs.append(job)

        print(f"[企业官网] {site['name']} - 获取到{len(jobs)}条通信相关岗位")

    except requests.exceptions.Timeout:
        print(f"[企业官网] {site['name']} - 请求超时")
    except Exception as e:
        print(f"[企业官网] {site['name']} - 获取失败: {e}")

    return jobs[:max_jobs]


def fetch_from_enterprise_sites(keywords: List[str], max_jobs_per_site: int = 8) -> List[Dict]:
    """从所有企业官网获取招聘信息"""
    config = load_job_config()
    enabled_sites = config.get("enterprise_sites_enabled", [s["id"] for s in ENTERPRISE_SITES])
    all_jobs = []

    for site in ENTERPRISE_SITES:
        if site["id"] not in enabled_sites:
            continue

        if site["id"] == "huawei":
            site_jobs = fetch_from_huawei(keywords, max_jobs_per_site)
        else:
            site_jobs = fetch_from_enterprise_html(site, keywords, max_jobs_per_site)

        all_jobs.extend(site_jobs)
        time.sleep(1)

    print(f"[企业官网] 总计获取{len(all_jobs)}条企业官网招聘信息")
    return all_jobs


# ====================== 综合获取入口 ======================

def fetch_jobs_from_source(source_id: str, keywords: List[str], locations: List[str],
                           max_jobs: int = 10) -> List[Dict]:
    """保留原接口兼容，实际由fetch_all_jobs分发"""
    return []


def fetch_all_jobs(use_mock_fallback: bool = True) -> List[Dict]:
    """综合获取招聘信息：企业官网 + 第三方API"""
    config = load_job_config()
    all_jobs = []
    fetch_mode = config.get("fetch_mode", "all")

    max_total = config.get("max_jobs_per_fetch", 50)

    if fetch_mode in ("all", "enterprise") and config.get("enterprise_fetch_enabled", True):
        print("\n========== 方案2: 企业官网招聘爬取 ==========")
        enterprise_jobs = fetch_from_enterprise_sites(
            config.get("keywords", []),
            max_jobs_per_site=max(5, max_total // len(ENTERPRISE_SITES))
        )
        all_jobs.extend(enterprise_jobs)
        print(f"[汇总] 企业官网获取: {len(enterprise_jobs)}条")

    if fetch_mode in ("all", "api") and config.get("api_fetch_enabled", False):
        print("\n========== 方案1: 第三方招聘API ==========")
        api_jobs = fetch_from_third_party_api(
            config.get("keywords", []),
            config.get("locations", []),
            max_jobs=max_total,
            api_key=config.get("third_party_api_key", ""),
            provider=config.get("third_party_api_provider", "juhe")
        )
        all_jobs.extend(api_jobs)
        print(f"[汇总] 第三方API获取: {len(api_jobs)}条")

    if not all_jobs and use_mock_fallback:
        print("\n[招聘爬虫] 未获取到真实数据，使用模拟数据作为演示")
        all_jobs = generate_mock_jobs(config.get("max_jobs_per_fetch", 30))
        for job in all_jobs:
            job["is_real_data"] = False

    config["last_fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_job_config(config)

    existing_jobs = load_job_recruitments()
    existing_ids = {job["id"] for job in existing_jobs}
    existing_ids.update({f"{job['title']}_{job['company']}_{job['location']}" for job in existing_jobs})

    new_jobs = []
    for job in all_jobs:
        unique_key = f"{job['title']}_{job['company']}_{job['location']}"
        if unique_key not in existing_ids:
            if "is_real_data" not in job:
                job["is_real_data"] = False
            new_jobs.append(job)

    all_combined_jobs = new_jobs + existing_jobs
    all_combined_jobs.sort(key=lambda x: x.get("publish_date", ""), reverse=True)

    if len(all_combined_jobs) > 500:
        all_combined_jobs = all_combined_jobs[:500]

    save_job_recruitments(all_combined_jobs)

    real_count = sum(1 for j in all_combined_jobs if j.get("is_real_data", False))
    mock_count = len(all_combined_jobs) - real_count
    print(f"\n[招聘爬虫] 获取完成：新增{len(new_jobs)}条，总计{len(all_combined_jobs)}条")
    print(f"[招聘爬虫] 数据来源: 真实数据{real_count}条, 模拟数据{mock_count}条")

    return all_combined_jobs


def filter_jobs(jobs: List[Dict], keyword: str = None, location: str = None,
                salary_min: int = None, experience: str = None,
                education: str = None, source: str = None,
                only_new: bool = False, only_hot: bool = False,
                only_favorite: bool = False) -> List[Dict]:
    filtered = jobs

    if keyword:
        keyword = keyword.lower()
        filtered = [
            j for j in filtered
            if keyword in j["title"].lower()
            or keyword in j["company"].lower()
            or keyword in " ".join(j.get("skills", [])).lower()
            or keyword in j.get("description", "").lower()
        ]

    if location and location != "全部":
        filtered = [j for j in filtered if location in j["location"]]

    if salary_min:
        filtered = [j for j in filtered if j.get("salary_max") and j["salary_max"] >= salary_min]

    if experience and experience != "不限":
        filtered = [j for j in filtered if j["experience"] == experience]

    if education and education != "不限":
        filtered = [j for j in filtered if j["education"] == education]

    if source and source != "全部":
        filtered = [j for j in filtered if j["source"] == source]

    if only_new:
        filtered = [j for j in filtered if j.get("is_new", False)]

    if only_hot:
        filtered = [j for j in filtered if j.get("is_hot", False)]

    if only_favorite:
        filtered = [j for j in filtered if j.get("favorite", False)]

    return filtered


def get_job_statistics(jobs: List[Dict]) -> Dict:
    if not jobs:
        return {"total": 0}

    total = len(jobs)
    new_count = sum(1 for j in jobs if j.get("is_new", False))
    hot_count = sum(1 for j in jobs if j.get("is_hot", False))
    favorite_count = sum(1 for j in jobs if j.get("favorite", False))

    location_stats = {}
    for j in jobs:
        loc = j["location"]
        location_stats[loc] = location_stats.get(loc, 0) + 1
    location_stats = dict(sorted(location_stats.items(), key=lambda x: x[1], reverse=True)[:10])

    salary_ranges = {"<10K": 0, "10-20K": 0, "20-30K": 0, "30-50K": 0, ">50K": 0}
    for j in jobs:
        s_max = j.get("salary_max") or 0
        if s_max < 10000:
            salary_ranges["<10K"] += 1
        elif s_max < 20000:
            salary_ranges["10-20K"] += 1
        elif s_max < 30000:
            salary_ranges["20-30K"] += 1
        elif s_max < 50000:
            salary_ranges["30-50K"] += 1
        else:
            salary_ranges[">50K"] += 1

    exp_stats = {}
    for j in jobs:
        exp = j["experience"]
        exp_stats[exp] = exp_stats.get(exp, 0) + 1

    edu_stats = {}
    for j in jobs:
        edu = j["education"]
        edu_stats[edu] = edu_stats.get(edu, 0) + 1

    source_stats = {}
    for j in jobs:
        src = j["source"]
        source_stats[src] = source_stats.get(src, 0) + 1

    title_stats = {}
    for j in jobs:
        title = j["title"]
        title_stats[title] = title_stats.get(title, 0) + 1
    title_stats = dict(sorted(title_stats.items(), key=lambda x: x[1], reverse=True)[:10])

    return {
        "total": total,
        "new_count": new_count,
        "hot_count": hot_count,
        "favorite_count": favorite_count,
        "location_stats": location_stats,
        "salary_ranges": salary_ranges,
        "experience_stats": exp_stats,
        "education_stats": edu_stats,
        "source_stats": source_stats,
        "title_stats": title_stats
    }


def toggle_job_favorite(job_id: str) -> Optional[Dict]:
    jobs = load_job_recruitments()
    for job in jobs:
        if job["id"] == job_id:
            job["favorite"] = not job.get("favorite", False)
            save_job_recruitments(jobs)
            return job
    return None


def mark_job_viewed(job_id: str) -> Optional[Dict]:
    jobs = load_job_recruitments()
    for job in jobs:
        if job["id"] == job_id:
            job["viewed"] = True
            save_job_recruitments(jobs)
            return job
    return None


def mark_job_applied(job_id: str) -> Optional[Dict]:
    jobs = load_job_recruitments()
    for job in jobs:
        if job["id"] == job_id:
            job["applied"] = True
            save_job_recruitments(jobs)
            return job
    return None


def delete_old_jobs(days: int = 90) -> int:
    jobs = load_job_recruitments()
    now = datetime.now()
    deleted_count = 0
    kept_jobs = []

    for job in jobs:
        try:
            publish_date = datetime.strptime(job["publish_date"], "%Y-%m-%d")
            if (now - publish_date).days <= days:
                kept_jobs.append(job)
            else:
                deleted_count += 1
        except (ValueError, KeyError):
            kept_jobs.append(job)

    if deleted_count > 0:
        save_job_recruitments(kept_jobs)

    return deleted_count


def init_job_data():
    if not os.path.exists(JOB_CONFIG_FILE):
        save_job_config(DEFAULT_CONFIG.copy())

    if not os.path.exists(JOB_DATA_FILE):
        initial_jobs = generate_mock_jobs(40)
        save_job_recruitments(initial_jobs)
        print(f"[招聘爬虫] 初始化完成，已生成{len(initial_jobs)}条初始招聘数据")
