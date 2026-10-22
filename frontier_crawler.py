# -*- coding: utf-8 -*-
"""前沿知识实时更新模块（对应教学方案模块4）

能力覆盖：
1. 权威信源抓取（3GPP、设备商、运营商、工信部等 RSS/JSON 源）
2. 教学难度分级：本科通识版 / 工程师实战版（AI 生成，失败自动降级为规则分级）
3. 前沿争议标注：识别标准未定、厂商路线分歧的话题，自动生成开放讨论题
4. 动态老化淘汰：内容生命周期监控，超期自动降权并进入待淘汰队列
5. 重复内容去重：SHA256 归一化哈希精确匹配 + difflib 相似度模糊匹配

抓取不到真实信源时自动降级为预置信源内容（离线/演示可用），与 job_crawler 的策略一致。
"""

import os
import re
import json
import time
import random
import hashlib
import difflib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

FRONTIER_DATA_FILE = "data/frontier_knowledge.json"
FRONTIER_CONFIG_FILE = "data/frontier_config.json"

# 通信领域前沿关键词（用于标签归类）
FRONTIER_TAG_RULES = {
    "5G-A": ["5G-A", "5G Advanced", "R18", "Release 18", "5.5G"],
    "6G": ["6G", "IMT-2030", "6G标准", "太赫兹"],
    "标准演进": ["3GPP", "Release", "标准", "规范", "立项", "立项课题"],
    "AI原生空口": ["AI原生", "AI/ML", "人工智能空口", "智能空口", "机器学习"],
    "通感一体": ["通感一体", "ISAC", "感知通信", "通感融合"],
    "卫星通信": ["NTN", "卫星", "非地面网络", "低轨", "星地"],
    "算力网络": ["算力网络", "算力", "边缘计算", "MEC", "算网融合"],
    "网络智能化": ["自智网络", "网络智能化", "意图网络", "自治网络"],
    "绿色通信": ["绿色", "节能", "能效", "低碳", "功耗"],
    "安全可信": ["安全", "隐私", "可信", "量子加密", "内生安全"],
    "核心网演进": ["核心网", "5GC", "服务化架构", "SBA", "网络切片"],
    "无线新技术": ["智能超表面", "RIS", "大规模天线", "Massive MIMO", "波束赋形", "RedCap"],
}

# 前沿争议特征词（命中则标注「前沿争议」并生成开放讨论题）
DISPUTE_KEYWORDS = [
    "争议", "分歧", "路线之争", "尚未定论", "未有定论", "存在两种", "两种技术路线",
    "竞逐", "不确定性", "厂商立场", "尚未纳入", "未达成一致", "博弈", "权衡",
    "是否应该", "取舍", "两种方案", "观点不一"
]

# ====================== 权威信源配置 ======================
FRONTIER_SOURCES = [
    {
        "id": "3gpp",
        "name": "3GPP",
        "category": "标准组织",
        "url": "https://www.3gpp.org/news-events/3gpp-news",
        "rss_url": "https://www.3gpp.org/rss/3gpp-news.xml",
        "type": "rss",
        "keywords_match": ["Release", "5G", "6G", "NR", "标准", "specification"],
    },
    {
        "id": "huawei",
        "name": "华为",
        "category": "设备商",
        "url": "https://www.huawei.com/cn/news",
        "rss_url": "https://www.huawei.com/cn/rss-feed/all",
        "type": "rss",
        "keywords_match": ["5G", "5G-A", "6G", "通信", "网络", "算力", "智能"],
    },
    {
        "id": "zte",
        "name": "中兴通讯",
        "category": "设备商",
        "url": "https://www.zte.com.cn/china/about/news.html",
        "rss_url": "https://www.zte.com.cn/china/rss/news.xml",
        "type": "rss",
        "keywords_match": ["5G", "6G", "核心网", "无线", "算力", "通信"],
    },
    {
        "id": "miit",
        "name": "工业和信息化部",
        "category": "主管部门",
        "url": "https://www.miit.gov.cn/",
        "rss_url": "https://www.miit.gov.cn/api/rss",
        "type": "rss",
        "keywords_match": ["5G", "6G", "通信", "网络", "信息化", "标准", "试点"],
    },
    {
        "id": "c114",
        "name": "C114通信网",
        "category": "行业媒体",
        "url": "https://www.c114.com.cn/",
        "rss_url": "https://www.c114.com.cn/rss/news.xml",
        "type": "rss",
        "keywords_match": ["5G", "6G", "运营商", "基站", "网络", "频谱", "通信"],
    },
    {
        "id": "cww",
        "name": "通信世界网",
        "category": "行业媒体",
        "url": "https://www.cww.net.cn/",
        "rss_url": "https://www.cww.net.cn/rss/news.xml",
        "type": "rss",
        "keywords_match": ["5G", "6G", "运营商", "网络", "技术", "标准"],
    },
]

DEFAULT_CONFIG = {
    "auto_fetch_enabled": True,
    "fetch_interval_hours": 12,
    "max_items_per_source": 8,
    "ai_grading_enabled": True,
    "auto_approve": False,          # 抓取内容一律进入待审队列，教师批准后才入库
    "freshness_days": 180,          # 超过该天数的内容标记为过期并降权
    "sources": [s["id"] for s in FRONTIER_SOURCES],
    "last_fetch_time": None,
    "fetch_count": 0,
}

# ====================== 预置信源内容（抓取失败时的降级数据） ======================
SEED_FRONTIER_ITEMS = [
    {
        "source_id": "3gpp", "source_name": "3GPP",
        "title": "3GPP Release 19 立项：AI/ML 空口增强与通感一体化成为重点方向",
        "summary_raw": "3GPP 在 Release 19 阶段新增多项与 AI/ML 空口、通感一体化（ISAC）相关的研究与工作项，推动网络侧与终端侧智能化能力落地，并明确感知与通信频谱共享的技术评估框架。",
        "source_url": "https://www.3gpp.org/news-events/3gpp-news",
    },
    {
        "source_id": "3gpp", "source_name": "3GPP",
        "title": "Release 20 时间表讨论：6G 研究窗口与 5G-Advanced 演进如何衔接尚存分歧",
        "summary_raw": "围绕 6G 研究何时启动、5G-Advanced 增强内容如何排期，各厂商在 Release 20 议题上存在两种技术路线主张，尚未达成一致，标准节奏的不确定性成为产业关注焦点。",
        "source_url": "https://www.3gpp.org/news-events/3gpp-news",
    },
    {
        "source_id": "huawei", "source_name": "华为",
        "title": "5G-Advanced 商用进展：万兆下行与通感一体在多个场景完成验证",
        "summary_raw": "华为发布 5G-Advanced 相关测试成果，展示万兆级下行速率、低时延确定性网络以及通感一体化在工业与低空场景的验证结果，标志着 5.5G 能力从标准走向工程实现。",
        "source_url": "https://www.huawei.com/cn/news",
    },
    {
        "source_id": "huawei", "source_name": "华为",
        "title": "AI 原生空口技术白皮书：基站内嵌大模型推理的能效与实时性取舍",
        "summary_raw": "白皮书提出将 AI 推理能力下沉到基站侧的技术架构，分析了智能空口在提升频谱效率的同时带来的功耗、实时性与可解释性挑战，工程落地仍需权衡多种方案。",
        "source_url": "https://www.huawei.com/cn/news",
    },
    {
        "source_id": "zte", "source_name": "中兴通讯",
        "title": "中兴通讯发布 6G 核心网演进方案，聚焦服务化架构与算网融合",
        "summary_raw": "面向 6G 时代，中兴提出核心网服务化架构的持续演进路径，强调算力与网络深度融合、内生安全与网络自治能力，推动核心网从连接中心向算力服务中心转型。",
        "source_url": "https://www.zte.com.cn/china/about/news.html",
    },
    {
        "source_id": "zte", "source_name": "中兴通讯",
        "title": "智能超表面（RIS）外场测试结果公布：覆盖增强能力受限于部署密度",
        "summary_raw": "智能超表面在弱覆盖场景的外场测试中取得增益，但测试同时表明其效果对部署位置与密度高度敏感，规模化商用价值仍存在争议，业界对 RIS 定位尚未形成共识。",
        "source_url": "https://www.zte.com.cn/china/about/news.html",
    },
    {
        "source_id": "miit", "source_name": "工业和信息化部",
        "title": "工信部推进 5G-A 规模化应用试点，明确重点行业融合方向",
        "summary_raw": "工业和信息化部组织 5G-Advanced 规模化应用试点，覆盖工业互联网、低空经济、智慧交通等重点方向，提出以行业融合应用牵引网络能力升级的政策导向。",
        "source_url": "https://www.miit.gov.cn/",
    },
    {
        "source_id": "miit", "source_name": "工业和信息化部",
        "title": "6G 频谱规划研究启动：高频段与低频段使用策略尚未定论",
        "summary_raw": "面向 6G 的频谱需求研究启动，高频段（毫米波/太赫兹）与重耕低频段的组合策略存在两种方案取向，频谱使用策略尚未定论，需要平衡覆盖成本与容量需求。",
        "source_url": "https://www.miit.gov.cn/",
    },
    {
        "source_id": "c114", "source_name": "C114通信网",
        "title": "运营商自智网络等级评估结果发布：L4 级能力成为年度焦点",
        "summary_raw": "多家运营商公布自智网络分级评估结果，网络智能化从 L3 向 L4 演进成为焦点，AI 在故障预测、参数自优化与能耗管理中的实际收益数据被首次系统披露。",
        "source_url": "https://www.c114.com.cn/",
    },
    {
        "source_id": "c114", "source_name": "C114通信网",
        "title": "RedCap 终端规模上量：中速物联场景的商用节奏快于预期",
        "summary_raw": "RedCap 终端出货量增长明显，在工业传感、车联网与可穿戴场景加速落地，运营商围绕中速物联的资费与网络策略同步调整，5G 物联市场结构正在重塑。",
        "source_url": "https://www.c114.com.cn/",
    },
    {
        "source_id": "cww", "source_name": "通信世界网",
        "title": "低轨卫星与地面网络融合：NTN 商用面临标准与产业双重挑战",
        "summary_raw": "低轨卫星通信与 5G NTN 标准的融合推进加速，但频谱协调、终端功耗与跨域漫游仍存在产业分歧，卫星直连手机的业务模式可持续性亦有不同观点。",
        "source_url": "https://www.cww.net.cn/",
    },
    {
        "source_id": "cww", "source_name": "通信世界网",
        "title": "绿色通信指标落地：基站节能与算力中心能耗成为双重考核点",
        "summary_raw": "面向双碳目标，通信行业绿色评价指标逐步落地，基站智能关断、液冷与算力调度成为主要手段，如何在节能与业务体验之间取得平衡仍是工程难点。",
        "source_url": "https://www.cww.net.cn/",
    },
]


# ====================== 文件读写 ======================
def _atomic_save_json(filepath: str, data):
    """原子写入 JSON：先写临时文件再重命名，防止并发写入损坏"""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, filepath)


def load_frontier_items() -> List[Dict]:
    """加载前沿知识条目"""
    try:
        if os.path.exists(FRONTIER_DATA_FILE):
            with open(FRONTIER_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"[前沿知识] 加载失败: {e}")
        return []


def save_frontier_items(items: List[Dict]):
    """保存前沿知识条目"""
    try:
        _atomic_save_json(FRONTIER_DATA_FILE, items)
    except Exception as e:
        print(f"[前沿知识] 保存失败: {e}")


def load_frontier_config() -> Dict:
    """加载前沿知识抓取配置（缺失字段用默认值补齐）"""
    config = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(FRONTIER_CONFIG_FILE):
            with open(FRONTIER_CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f) or {})
    except Exception as e:
        print(f"[前沿知识] 配置加载失败: {e}")
    return config


def save_frontier_config(config: Dict):
    """保存前沿知识抓取配置"""
    try:
        _atomic_save_json(FRONTIER_CONFIG_FILE, config)
    except Exception as e:
        print(f"[前沿知识] 配置保存失败: {e}")


# ====================== 大模型调用（教学难度分级 / 争议标注） ======================
def _load_api_key() -> str:
    """密钥读取优先级：环境变量 SILICONFLOW_API_KEY > api_key.local > 硬编码默认值"""
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if key:
        return key
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key.local")
    try:
        with open(key_file, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    return "sk-sdfaoxkrbsmmnueekypiqjgxtcrscmrmajrzvtdjkgnjieyi"


API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_NAME = "Pro/moonshotai/Kimi-K2.6"

GRADE_PROMPT = """你是通信工程教学资源加工专家。请阅读给定的行业前沿资讯，输出教学化加工结果。

严格输出 JSON（不要输出任何其他文字），字段如下：
{
  "undergrad": "本科通识版讲解，150字以内，用通俗语言讲清是什么、为什么重要，避免公式术语堆砌",
  "engineer": "工程师实战版讲解，200字以内，突出技术实现、工程约束、部署影响与实战要点",
  "tags": ["3-5个技术标签"],
  "is_frontier_dispute": true或false，是否为行业尚有争议/路线未定的前沿话题,
  "dispute_reason": "若为争议话题，说明分歧点；否则填空字符串",
  "discussion_question": "若为争议话题，给出一个面向学生的开放性讨论题；否则填空字符串",
  "key_points": ["3-4条要点，每条20字以内"]
}"""


def call_ai_grade(title: str, summary: str, timeout: int = 90) -> Optional[Dict]:
    """调用大模型对前沿内容做教学分级加工，失败返回 None"""
    if not REQUESTS_AVAILABLE:
        return None
    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": GRADE_PROMPT},
                {"role": "user", "content": f"标题：{title}\n摘要：{summary}"},
            ],
            "temperature": 0.4,
            "max_tokens": 1200,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_load_api_key()}",
        }
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            print(f"[前沿知识] AI 分级失败: {resp.status_code}")
            return None
        answer = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if answer.startswith("```"):
            answer = re.sub(r"^```(?:json)?\s*", "", answer)
            answer = re.sub(r"\s*```$", "", answer)
        try:
            return json.loads(answer)
        except json.JSONDecodeError:
            s, e = answer.find("{"), answer.rfind("}")
            if s >= 0 and e > s:
                try:
                    return json.loads(answer[s:e + 1])
                except json.JSONDecodeError:
                    return None
        return None
    except Exception as e:
        print(f"[前沿知识] AI 分级异常: {e}")
        return None


def _extract_tags(text: str) -> List[str]:
    """按关键词规则为内容打标签"""
    tags = []
    for tag, keywords in FRONTIER_TAG_RULES.items():
        if any(kw.lower() in text.lower() for kw in keywords):
            tags.append(tag)
    return tags or ["行业动态"]


def _is_dispute(text: str) -> Optional[str]:
    """判断是否为前沿争议话题，返回命中的分歧线索"""
    hits = [kw for kw in DISPUTE_KEYWORDS if kw in text]
    return hits[0] if hits else None


def rule_based_grade(title: str, summary: str) -> Dict:
    """规则分级（AI 不可用时的降级方案，保证功能离线可用）"""
    text = f"{title} {summary}"
    tags = _extract_tags(text)
    dispute_hit = _is_dispute(text)
    is_dispute = bool(dispute_hit)
    undergrad = f"【通识版】{summary[:110]}……核心概念：{'、'.join(tags[:3])}。"
    engineer = (
        f"【实战版】{summary[:150]}……"
        f"关注点：标准化节奏、部署约束与实际收益，需结合{'、'.join(tags[:2])}评估落地可行性。"
    )
    return {
        "undergrad": undergrad,
        "engineer": engineer,
        "tags": tags,
        "is_frontier_dispute": is_dispute,
        "dispute_reason": f"文中出现“{dispute_hit}”等表述，产业路线尚未收敛。" if is_dispute else "",
        "discussion_question": (
            f"围绕「{title[:30]}」，你认为哪种技术路线更适合当前阶段？请说明理由与适用边界。"
            if is_dispute else ""
        ),
        "key_points": [t for t in tags[:4]],
        "graded_by": "rule",
    }


def grade_item(title: str, summary: str, use_ai: bool = True) -> Dict:
    """对单条内容做教学分级：优先 AI，失败回退规则分级"""
    if use_ai:
        result = call_ai_grade(title, summary)
        if result and result.get("undergrad"):
            result.setdefault("tags", _extract_tags(f"{title} {summary}"))
            result.setdefault("is_frontier_dispute", False)
            result.setdefault("dispute_reason", "")
            result.setdefault("discussion_question", "")
            result.setdefault("key_points", [])
            result["graded_by"] = "ai"
            return result
    return rule_based_grade(title, summary)


# ====================== 信源抓取 ======================
def _strip_html(text: str) -> str:
    """去除 HTML/XML 标签与实体，得到纯文本"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def _parse_rss(xml_text: str, max_items: int) -> List[Dict]:
    """轻量解析 RSS/Atom（不依赖第三方 XML 库，避免命名空间干扰）"""
    items = []
    blocks = re.findall(r"<(?:item|entry)[^>]*>(.*?)</(?:item|entry)>", xml_text, re.S | re.I)
    for block in blocks[:max_items]:
        title_m = re.search(r"<title[^>]*>(.*?)</title>", block, re.S | re.I)
        link_m = re.search(r"<link[^>]*>(.*?)</link>", block, re.S | re.I)
        if not title_m:
            continue
        desc_m = re.search(r"<(?:description|summary)[^>]*>(.*?)</(?:description|summary)>", block, re.S | re.I)
        date_m = re.search(r"<(?:pubDate|updated|published)[^>]*>(.*?)</(?:pubDate|updated|published)>", block, re.S | re.I)
        items.append({
            "title": _strip_html(title_m.group(1)),
            "summary_raw": _strip_html(desc_m.group(1))[:600] if desc_m else "",
            "source_url": _strip_html(link_m.group(1)) if link_m else "",
            "published_at": _strip_html(date_m.group(1)) if date_m else datetime.now().strftime("%Y-%m-%d"),
        })
    return items


def _normalize_date(raw: str) -> str:
    """把 RSS 里的日期字符串统一成 YYYY-MM-DD"""
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")
    patterns = [
        (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
        (r"(\d{4})/(\d{2})/(\d{2})", "%Y-%m-%d"),
        (r"(\d{1,2})\s+(\w{3})\s+(\d{4})", "%d %b %Y"),
        (r"(\w{3}),\s*(\d{1,2})\s+(\w{3})\s+(\d{4})", "%d %b %Y"),
    ]
    from datetime import datetime as _dt
    for pattern, _fmt in patterns:
        m = re.search(pattern, raw)
        if not m:
            continue
        try:
            if len(m.groups()) == 3 and m.group(1).isdigit():
                return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            if len(m.groups()) == 3:
                return _dt.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").strftime("%Y-%m-%d")
            if len(m.groups()) == 4:
                return _dt.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %b %Y").strftime("%Y-%m-%d")
        except Exception:
            continue
    return datetime.now().strftime("%Y-%m-%d")


def fetch_from_source(source: Dict, max_items: int = 8) -> List[Dict]:
    """从单个信源抓取原始资讯，失败返回空列表"""
    if not REQUESTS_AVAILABLE:
        return []
    rss_url = source.get("rss_url")
    if not rss_url:
        return []
    try:
        resp = requests.get(
            rss_url,
            timeout=12,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        if resp.status_code != 200 or not resp.text:
            print(f"[前沿知识] 信源 {source['name']} 返回异常: {resp.status_code}")
            return []
        raw_items = _parse_rss(resp.text, max_items)
        keywords = [k.lower() for k in source.get("keywords_match", [])]
        results = []
        for item in raw_items:
            text = f"{item['title']} {item['summary_raw']}".lower()
            if keywords and not any(kw in text for kw in keywords):
                continue
            item["source_id"] = source["id"]
            item["source_name"] = source["name"]
            item["published_at"] = _normalize_date(item.get("published_at", ""))
            results.append(item)
        print(f"[前沿知识] 信源 {source['name']} 抓取 {len(results)} 条")
        return results
    except Exception as e:
        print(f"[前沿知识] 信源 {source['name']} 抓取失败: {e}")
        return []


def generate_seed_items(count: Optional[int] = None) -> List[Dict]:
    """生成预置前沿内容（真实信源不可达时的降级数据源）"""
    pool = list(SEED_FRONTIER_ITEMS)
    random.shuffle(pool)
    if count:
        pool = pool[:count]
    results = []
    for item in pool:
        data = dict(item)
        data["published_at"] = (datetime.now() - timedelta(days=random.randint(0, 20))).strftime("%Y-%m-%d")
        results.append(data)
    return results


# ====================== 去重 ======================
def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\W]+", "", (text or "").lower())


def _title_hash(title: str) -> str:
    return hashlib.sha256(_normalize_text(title).encode("utf-8")).hexdigest()


def is_duplicate(title: str, existing_items: List[Dict]) -> bool:
    """去重：SHA256 归一化精确匹配 + difflib 相似度 > 0.9 模糊匹配"""
    new_norm = _normalize_text(title)
    if not new_norm:
        return True
    new_hash = _title_hash(title)
    for item in existing_items:
        existing_norm = _normalize_text(item.get("title", ""))
        if len(new_norm) < 8 or len(existing_norm) < 8:
            continue
        if existing_norm == new_norm:
            return True
        if hashlib.sha256(existing_norm.encode("utf-8")).hexdigest() == new_hash:
            return True
        len_ratio = min(len(new_norm), len(existing_norm)) / max(len(new_norm), len(existing_norm))
        if len_ratio >= 0.85 and difflib.SequenceMatcher(None, new_norm, existing_norm).ratio() > 0.9:
            return True
    return False


# ====================== 老化淘汰 ======================
def refresh_freshness(items: List[Dict], freshness_days: int = 180) -> int:
    """扫描内容生命周期：超期内容标记过期并降权（权重 1.0 → 0.4）"""
    today = datetime.now()
    changed = 0
    for item in items:
        if item.get("status") in ("discarded", "rejected"):
            continue
        published = item.get("published_at") or item.get("fetched_at", "")
        try:
            pub_dt = datetime.strptime(published[:10], "%Y-%m-%d")
        except Exception:
            continue
        age_days = (today - pub_dt).days
        expired = age_days > freshness_days
        if item.get("expired") != expired:
            changed += 1
        item["expired"] = expired
        item["age_days"] = age_days
        item["weight"] = 0.4 if expired else 1.0
        item["valid_until"] = (pub_dt + timedelta(days=freshness_days)).strftime("%Y-%m-%d")
    return changed


def build_item(raw: Dict, existing_items: List[Dict], use_ai: bool = True,
               freshness_days: int = 180) -> Dict:
    """把抓取到的原始资讯加工为标准条目（分级 + 标签 + 争议标注 + 生命周期字段）"""
    title = (raw.get("title") or "").strip()
    summary = (raw.get("summary_raw") or "").strip() or title
    grade = grade_item(title, summary, use_ai=use_ai)
    now = datetime.now()
    published = raw.get("published_at") or now.strftime("%Y-%m-%d")
    try:
        pub_dt = datetime.strptime(published[:10], "%Y-%m-%d")
    except Exception:
        pub_dt = now
    item_id = "fk_%s_%s" % (now.strftime("%Y%m%d%H%M%S"), hashlib.md5(title.encode("utf-8")).hexdigest()[:6])
    return {
        "id": item_id,
        "title": title,
        "summary_raw": summary,
        "content": grade.get("undergrad", summary),
        "difficulty_versions": {
            "undergrad": grade.get("undergrad", ""),
            "engineer": grade.get("engineer", ""),
        },
        "key_points": grade.get("key_points", []),
        "tags": grade.get("tags", []),
        "is_frontier_dispute": bool(grade.get("is_frontier_dispute")),
        "dispute_reason": grade.get("dispute_reason", ""),
        "discussion_question": grade.get("discussion_question", ""),
        "source_id": raw.get("source_id", ""),
        "source_name": raw.get("source_name", ""),
        "source_url": raw.get("source_url", ""),
        "published_at": pub_dt.strftime("%Y-%m-%d"),
        "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "graded_by": grade.get("graded_by", "rule"),
        "status": "pending",          # pending / approved / rejected / discarded
        "review_note": "",
        "reviewed_by": "",
        "reviewed_at": "",
        "added_to_kb": False,
        "expired": False,
        "age_days": 0,
        "weight": 1.0,
        "valid_until": (pub_dt + timedelta(days=freshness_days)).strftime("%Y-%m-%d"),
    }


def fetch_all_frontier(use_mock_fallback: bool = True, use_ai: Optional[bool] = None) -> Dict:
    """抓取全部信源并加工入库，返回本次抓取统计"""
    config = load_frontier_config()
    if use_ai is None:
        use_ai = bool(config.get("ai_grading_enabled", True))
    max_items = int(config.get("max_items_per_source", 8))
    enabled_ids = config.get("sources") or [s["id"] for s in FRONTIER_SOURCES]
    freshness_days = int(config.get("freshness_days", 180))

    items = load_frontier_items()
    raw_list = []
    used_fallback = False

    for source in FRONTIER_SOURCES:
        if source["id"] not in enabled_ids:
            continue
        raw_list.extend(fetch_from_source(source, max_items=max_items))

    if not raw_list and use_mock_fallback:
        raw_list = generate_seed_items(count=max_items)
        used_fallback = True
        print(f"[前沿知识] 真实信源不可达，降级使用预置信源内容 {len(raw_list)} 条")

    added, skipped, dispute_count, ai_count = 0, 0, 0, 0
    for raw in raw_list:
        title = raw.get("title", "")
        if not title or is_duplicate(title, items):
            skipped += 1
            continue
        item = build_item(raw, items, use_ai=use_ai, freshness_days=freshness_days)
        if config.get("auto_approve"):
            item["status"] = "approved"
        if item.get("is_frontier_dispute"):
            dispute_count += 1
        if item.get("graded_by") == "ai":
            ai_count += 1
        items.append(item)
        added += 1

    refresh_freshness(items, freshness_days)
    save_frontier_items(items)

    config["last_fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config["fetch_count"] = int(config.get("fetch_count", 0)) + 1
    save_frontier_config(config)

    stats = {
        "fetched_raw": len(raw_list),
        "added": added,
        "skipped_duplicate": skipped,
        "dispute_count": dispute_count,
        "ai_graded": ai_count,
        "rule_graded": added - ai_count,
        "used_fallback": used_fallback,
        "total": len(items),
    }
    print(f"[前沿知识] 抓取完成: {stats}")
    return stats


def get_stats(items: Optional[List[Dict]] = None) -> Dict:
    """汇总前沿知识看板统计"""
    if items is None:
        items = load_frontier_items()
    config = load_frontier_config()
    return {
        "total": len(items),
        "pending": sum(1 for i in items if i.get("status") == "pending"),
        "approved": sum(1 for i in items if i.get("status") == "approved"),
        "rejected": sum(1 for i in items if i.get("status") == "rejected"),
        "discarded": sum(1 for i in items if i.get("status") == "discarded"),
        "dispute": sum(1 for i in items if i.get("is_frontier_dispute")),
        "expired": sum(1 for i in items if i.get("expired") and i.get("status") != "discarded"),
        "added_to_kb": sum(1 for i in items if i.get("added_to_kb")),
        "last_fetch_time": config.get("last_fetch_time"),
        "fetch_count": config.get("fetch_count", 0),
    }


def init_frontier_data():
    """首次运行时初始化数据文件（含预置内容，保证无网络也能演示）"""
    if not os.path.exists(FRONTIER_CONFIG_FILE):
        save_frontier_config(dict(DEFAULT_CONFIG))
    if not os.path.exists(FRONTIER_DATA_FILE):
        save_frontier_items([])
        print("[前沿知识] 数据文件初始化完成")
