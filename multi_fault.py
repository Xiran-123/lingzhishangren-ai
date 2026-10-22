# -*- coding: utf-8 -*-
"""
多故障并发优先级决策（Multi-Fault Concurrent Prioritization）

岗位场景任务智能生成 —— 第三个核心能力：

核心网设备异常、传输光缆中断、无线侧干扰等多故障同时告警。
学员需基于【业务SLA + 影响用户数 + 业务等级】快速判断故障等级，
在有限人力（2个现场班组 + 1个远程支持席）下制定最优排障顺序与资源分配，
平衡技术修复与业务止损。

一局流程：
  1. 开局：按难度动态生成 3~5 个并发故障工单（参数每局随机，真正动态）
  2. 排查决策：学员拖拽排序 + 为每个故障分配处理通道（班组A/班组B/远程席/不派单）
     - 次生故障（如传输中断引发的基站退服）应由上游故障恢复自动消除，不应单独派单
  3. 专家级：开局 75 秒后注入突发事件（演唱会应急扩容），学员须决定插入位置
  4. 提交：系统用离散事件仿真推演恢复时间线，穷举 排列×分配 求最优解对比评分

评分（满分100）：
  排序分 40（与最优顺序的肯德尔一致对比例）
  调度分 30（资源约束 + 业务损失 vs 最优损失）
  动态决策分 20（专家级事件插入位置；低难度无事件自动满分）
  零重大失误加分 10

难度自适应：入门(3故障) / 工程师(4故障+次生) / 专家(5故障+次生+突发事件+限时10分钟)。
规则与故障链一致：零重大失误且得分≥80 升级，重大失误≥2 降级，持久化到
data/multi_fault_state.json，等级变化由 app.py 写审计。

确定性规则引擎，不依赖 AI。
"""

import itertools
import json
import os
import random
import uuid
from datetime import datetime, timedelta

DATA_DIR = "data"
STATE_FILE = os.path.join(DATA_DIR, "multi_fault_state.json")

LEVELS = {1: "入门", 2: "工程师", 3: "专家"}

LEVEL_RULES = {
    1: {"label": "入门", "fault_count": 3, "dependency": False, "insert_event": False,
        "time_limit": None,
        "desc": "3 个并发故障，无次生关联，不限时"},
    2: {"label": "工程师", "fault_count": 4, "dependency": True, "insert_event": False,
        "time_limit": None,
        "desc": "4 个并发故障，含 1 组次生关联（上游修复后下游告警自动消除）"},
    3: {"label": "专家", "fault_count": 5, "dependency": True, "insert_event": True,
        "time_limit": 600, "event_delay_sec": 75,
        "desc": "5 个并发故障 + 次生关联 + 75 秒后突发事件插入，限时 10 分钟"},
}

# 评分权重
SCORE_ORDER = 40
SCORE_DISPATCH = 30
SCORE_DECISION = 20
SCORE_CLEAN = 10

# 可用资源
RESOURCES = {
    "crew_a": {"label": "现场班组A", "onsite_capable": True},
    "crew_b": {"label": "现场班组B", "onsite_capable": True},
    "remote": {"label": "远程支持席", "onsite_capable": False},
}

# ============================ 故障模板库 ============================
# biz_weight: 业务等级权重 1~4（政企专线/VIP最高）
# users_range: 影响用户数随机范围；sla_range: 剩余SLA分钟；repair_range: 预计修复分钟
# onsite: 是否必须现场处理；secondary_of: 次生上游模板id（上游恢复后自动消除）
# clue: 文案中埋给学员的次生识别线索

FAULT_TEMPLATES = {
    "cn_sgw_overload": {
        "domain": "core_network", "domain_label": "核心网",
        "title": "SAE-GW 池化节点负荷过载",
        "symptom": "网管告警：SAE-GW-POOL-01 CPU 利用率 92%，部分用户 PDP 上下文激活失败，APN 接通率降至 87%。",
        "biz_type": "公众数据业务", "biz_weight": 3,
        "users_range": (30000, 80000), "sla_range": (30, 60), "repair_range": (25, 45),
        "onsite": False, "secondary_of": None,
    },
    "cn_hss_storm": {
        "domain": "core_network", "domain_label": "核心网",
        "title": "HSS 信令风暴导致注册失败率飙升",
        "symptom": "HSS-01 Diameter 信令拥塞，鉴权超时率 18%，大量用户开机后无法附着网络，投诉量 10 分钟内翻 3 倍。",
        "biz_type": "公众语音+注册", "biz_weight": 4,
        "users_range": (50000, 120000), "sla_range": (20, 40), "repair_range": (30, 50),
        "onsite": False, "secondary_of": None,
    },
    "tr_otn_cut": {
        "domain": "transmission", "domain_label": "传输",
        "title": "OTN 骨干光缆中断（施工挖断）",
        "symptom": "OTN-NE-07 上报 R_LOS：城东管廊光缆被市政施工挖断，承载 12 条政企专线与 3 个基站传输环受影响，保护倒换部分失败。",
        "biz_type": "政企专线+基站回传", "biz_weight": 4,
        "users_range": (5000, 20000), "sla_range": (25, 45), "repair_range": (60, 120),
        "onsite": True, "secondary_of": None,
    },
    "tr_ptn_jitter": {
        "domain": "transmission", "domain_label": "传输",
        "title": "PTN 汇聚环时延抖动超标",
        "symptom": "PTN-RING-03 北向性能越限：时延抖动 38ms（门限 10ms），VoLTE 用户感知杂音，暂未见丢包扩散。",
        "biz_type": "VoLTE 语音", "biz_weight": 2,
        "users_range": (8000, 25000), "sla_range": (45, 90), "repair_range": (30, 60),
        "onsite": False, "secondary_of": None,
    },
    "wl_cell_outage": {
        "domain": "wireless", "domain_label": "无线",
        "title": "宏站小区批量退服",
        "symptom": "城东 3 个宏站小区退服，告警为「传输链路中断」；该片区无电源告警、无设备硬件告警，退服段落与 OTN 中断点为同一管廊路由。",
        "biz_type": "公众移动业务", "biz_weight": 3,
        "users_range": (3000, 9000), "sla_range": (30, 60), "repair_range": (20, 40),
        "onsite": True, "secondary_of": "tr_otn_cut",
        "clue": "告警为传输链路中断且无电源/硬件告警，极可能是传输中断的次生故障，上游恢复后应自动消除。",
    },
    "wl_interference": {
        "domain": "wireless", "domain_label": "无线",
        "title": "高话务区域上行干扰",
        "symptom": "CBD 商圈 6 个小区上行 NI 底噪抬升至 -95dBm，RRC 接通率降至 82%，疑似外部干扰源，需现场扫频定位。",
        "biz_type": "公众移动业务", "biz_weight": 2,
        "users_range": (10000, 40000), "sla_range": (40, 90), "repair_range": (30, 60),
        "onsite": True, "secondary_of": None,
    },
    "pw_rectifier": {
        "domain": "power", "domain_label": "电源",
        "title": "机房整流模块故障转电池供电",
        "symptom": "城南汇聚机房 2 组整流模块故障，负载已切换至蓄电池组供电，按当前负载估算续航约 90 分钟，超时将大面积掉电。",
        "biz_type": "汇聚机房承载业务", "biz_weight": 3,
        "users_range": (4000, 12000), "sla_range": (50, 80), "repair_range": (30, 50),
        "onsite": True, "secondary_of": None,
    },
    "pw_ups_alarm": {
        "domain": "power", "domain_label": "电源",
        "title": "UPS 旁路告警伴市电闪断风险",
        "symptom": "核心机房 UPS 转旁路运行，同期市电出现 3 次瞬时闪断，核心设备直挂市电风险高，需立即处置。",
        "biz_type": "核心机房承载业务", "biz_weight": 3,
        "users_range": (6000, 18000), "sla_range": (35, 70), "repair_range": (25, 45),
        "onsite": True, "secondary_of": None,
    },
    "dt_otn_vip": {
        "domain": "data_service", "domain_label": "政企数据",
        "title": "政企 OTN 专线中断（银行客户）",
        "symptom": "某银行总行—3 家分行 OTN 专线中断，1200 路 POS/ATM 离线，客户已电话升级投诉，SLA 罚则条款启动倒计时。",
        "biz_type": "政企专线（银行）", "biz_weight": 4,
        "users_range": (800, 2000), "sla_range": (20, 35), "repair_range": (20, 40),
        "onsite": True, "secondary_of": None,
    },
    "dt_dns": {
        "domain": "data_service", "domain_label": "政企数据",
        "title": "省内 DNS 解析成功率下降",
        "symptom": "省干 DNS-01 解析成功率从 99.9% 降至 96.2%，部分用户网页打开缓慢，舆情监控出现零星负面帖。",
        "biz_type": "公众互联网业务", "biz_weight": 2,
        "users_range": (40000, 100000), "sla_range": (40, 80), "repair_range": (20, 40),
        "onsite": False, "secondary_of": None,
    },
}

# 专家级突发事件（开局 75 秒后注入）
INSERT_EVENT_TEMPLATE = {
    "id": "ev_concert",
    "domain": "wireless", "domain_label": "无线",
    "title": "突发事件：演唱会场馆话务风暴预警",
    "symptom": "应急通信指挥部通报：奥体中心演唱会 1 小时后开场，预计入场 2.8 万人，场馆周边 3 个小区 PRB 利用率已升至 95%，需立即派员配合应急扩容与现场保障。",
    "biz_type": "重大活动保障（政企合同）", "biz_weight": 4,
    "users": 28000, "sla": 50, "repair": 35,
    "onsite": True, "secondary_of": None,
    "is_event": True,
}

SCENARIOS_BG = [
    "国庆黄金周保障第 3 天 14:20，网管大屏同时弹出多条告警，值班主任要求你在时限内给出排障顺序与人力调度方案。",
    "汛期红色预警期间 09:05，多处网元同时告警，应急通信保障预案已启动，你是当班调度长。",
    "春运返乡高峰 18:40，晚高峰叠加恶劣天气，网管告警风暴来袭，抢修人力仅剩 2 个班组。",
]

# 难度对应的故障组合
_LEVEL_POOLS = {
    1: ["cn_sgw_overload", "tr_ptn_jitter", "wl_interference", "pw_ups_alarm", "dt_dns"],
    2: ["cn_sgw_overload", "cn_hss_storm", "wl_interference", "pw_rectifier", "dt_dns"],
    3: ["cn_sgw_overload", "cn_hss_storm", "wl_interference", "pw_rectifier", "dt_dns",
        "dt_otn_vip", "pw_ups_alarm", "tr_ptn_jitter"],
}
DEPENDENCY_PAIR = ("tr_otn_cut", "wl_cell_outage")


# ============================ 基础工具 ============================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def init_multi_fault_data():
    """初始化状态文件（首次运行自动创建）"""
    _ensure_dir()
    if not os.path.exists(STATE_FILE):
        _save({"version": 1, "created_at": _now(), "updated_at": _now(),
               "levels": {}, "sessions": {}, "history": []})


def _load() -> dict:
    _ensure_dir()
    if not os.path.exists(STATE_FILE):
        return {"version": 1, "created_at": _now(), "updated_at": _now(),
                "levels": {}, "sessions": {}, "history": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("状态文件结构异常")
        data.setdefault("levels", {})
        data.setdefault("sessions", {})
        data.setdefault("history", [])
        return data
    except Exception as e:
        print(f"[多故障] 状态读取失败，使用空状态: {e}")
        return {"version": 1, "created_at": _now(), "updated_at": _now(),
                "levels": {}, "sessions": {}, "history": []}


def _save(data: dict):
    """原子写入，避免中途崩溃损坏状态"""
    _ensure_dir()
    data["updated_at"] = _now()
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# ============================ 难度自适应 ============================

def get_student_level(student_no: str) -> int:
    data = _load()
    return int(data.get("levels", {}).get(str(student_no), 1))


def set_student_level(student_no: str, level: int) -> dict:
    level = max(1, min(3, int(level)))
    data = _load()
    before = int(data.setdefault("levels", {}).get(str(student_no), 1))
    data["levels"][str(student_no)] = level
    _save(data)
    return {"student_no": str(student_no), "before": before, "after": level}


# ============================ 故障生成（动态） ============================

def _instantiate(template_id: str, rng: random.Random) -> dict:
    """从模板实例化一个故障工单（参数随机化，每局不同）"""
    t = FAULT_TEMPLATES[template_id]
    return {
        "id": f"{template_id}_{rng.randint(100, 999)}",
        "template": template_id,
        "domain": t["domain"], "domain_label": t["domain_label"],
        "title": t["title"], "symptom": t["symptom"],
        "biz_type": t["biz_type"], "biz_weight": t["biz_weight"],
        "users": rng.randint(*t["users_range"]),
        "sla": rng.randint(*t["sla_range"]),
        "repair": rng.randint(*t["repair_range"]),
        "onsite": t["onsite"],
        "secondary_of_template": t["secondary_of"],
        "secondary_of": None,  # 实例化后回填为上游工单 id
    }


def _instantiate_event() -> dict:
    t = INSERT_EVENT_TEMPLATE
    return {
        "id": t["id"], "template": t["id"],
        "domain": t["domain"], "domain_label": t["domain_label"],
        "title": t["title"], "symptom": t["symptom"],
        "biz_type": t["biz_type"], "biz_weight": t["biz_weight"],
        "users": t["users"], "sla": t["sla"], "repair": t["repair"],
        "onsite": t["onsite"], "secondary_of": None, "is_event": True,
    }


def generate_faults(level: int, rng: random.Random) -> list:
    """按难度生成一局故障列表"""
    rules = LEVEL_RULES[level]
    faults = []
    if rules["dependency"]:
        primary = _instantiate(DEPENDENCY_PAIR[0], rng)
        secondary = _instantiate(DEPENDENCY_PAIR[1], rng)
        secondary["secondary_of"] = primary["id"]
        faults = [primary, secondary]
        pool = [p for p in _LEVEL_POOLS[level]]
        for tpl in rng.sample(pool, rules["fault_count"] - 2):
            faults.append(_instantiate(tpl, rng))
    else:
        pool = [p for p in _LEVEL_POOLS[level]]
        for tpl in rng.sample(pool, rules["fault_count"]):
            faults.append(_instantiate(tpl, rng))
    rng.shuffle(faults)
    return faults


def urgency_score(f: dict) -> float:
    """紧急度评分（对外可解释）：业务权重×40 + 用户规模 + SLA紧迫度"""
    users_part = min(f["users"] / 10000.0, 4.0) * 8
    sla_part = max(0, 90 - f["sla"]) * 0.6
    return f["biz_weight"] * 40 + users_part + sla_part


# ============================ 仿真与最优解 ============================

def simulate(faults: list, order: list, assignments: dict) -> dict:
    """离散事件仿真：按全局顺序，各资源串行处理自己队列
    返回 {completion: {fid: 分钟}, loss: 总业务损失, violations: 违约故障id列表}
    约束违规（现场故障派远程）的故障视为未修复，损失按满时限计。"""
    fmap = {f["id"]: f for f in faults}
    res_time = {r: 0 for r in RESOURCES}
    completion = {}
    HORIZON = 480  # 未修复视为 480 分钟后恢复（远超SLA，产生大损失）
    for fid in order:
        f = fmap.get(fid)
        if not f:
            continue
        if f.get("secondary_of"):
            parent_done = completion.get(f["secondary_of"], HORIZON)
            completion[fid] = parent_done  # 次生随上游自动恢复
            continue
        res = assignments.get(fid, "none")
        if res not in RESOURCES:
            completion[fid] = HORIZON  # 不派单 = 不修
            continue
        if f["onsite"] and not RESOURCES[res]["onsite_capable"]:
            completion[fid] = HORIZON  # 远程处理现场故障 = 无效
            continue
        start = res_time[res]
        done = start + f["repair"]
        res_time[res] = done
        completion[fid] = done
    loss, violations = 0.0, []
    for f in faults:
        done = completion.get(f["id"], HORIZON)
        overtime = max(0, done - f["sla"])
        if overtime > 0:
            violations.append(f["id"])
            loss += f["biz_weight"] * overtime
    return {"completion": completion, "loss": round(loss, 1), "violations": violations}


def find_optimal(faults: list) -> dict:
    """穷举 排列×合法分配 求最优（最小业务损失；并列时违约数少者优先）"""
    ids = [f["id"] for f in faults]
    fmap = {f["id"]: f for f in faults}

    def legal_assignments(f):
        if f.get("secondary_of"):
            return ["none"]
        return [r for r, cfg in RESOURCES.items()
                if not f["onsite"] or cfg["onsite_capable"]]

    best = None
    for perm in itertools.permutations(ids):
        # 次生必须排在上游之后才有意义，剪枝提速
        ok = True
        pos = {fid: i for i, fid in enumerate(perm)}
        for f in faults:
            if f.get("secondary_of") and pos[f["id"]] < pos[f["secondary_of"]]:
                ok = False
                break
        if not ok:
            continue
        choices = [legal_assignments(fmap[fid]) for fid in perm]
        for combo in itertools.product(*choices):
            assign = dict(zip(perm, combo))
            sim = simulate(faults, list(perm), assign)
            key = (sim["loss"], len(sim["violations"]))
            if best is None or key < best["key"]:
                best = {"key": key, "order": list(perm), "assignments": assign,
                        "sim": sim}
    return best


# ============================ 会话引擎 ============================

def _fault_public(f: dict) -> dict:
    """对外视图：不泄露次生关系结论（埋在线索文案里由学员推理）"""
    return {
        "id": f["id"], "domain": f["domain"], "domain_label": f["domain_label"],
        "title": f["title"], "symptom": f["symptom"],
        "biz_type": f["biz_type"], "biz_weight": f["biz_weight"],
        "users": f["users"], "sla": f["sla"], "repair": f["repair"],
        "onsite": f["onsite"], "is_event": bool(f.get("is_event")),
    }


def _session_public(sess: dict, reveal_event: bool = True) -> dict:
    rules = LEVEL_RULES[sess["level"]]
    faults = [_fault_public(f) for f in sess["faults"]]
    event = None
    if sess["level"] == 3 and sess.get("event") and reveal_event:
        started = datetime.strptime(sess["started_at"], "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.now() - started).total_seconds()
        if elapsed >= rules.get("event_delay_sec", 75):
            event = _fault_public(sess["event"])
            sess["event_revealed"] = True
    remaining = None
    if sess.get("deadline"):
        remaining = max(0, int((datetime.strptime(sess["deadline"], "%Y-%m-%d %H:%M:%S")
                                - datetime.now()).total_seconds()))
    return {
        "session_id": sess["session_id"],
        "level": sess["level"], "level_label": LEVELS[sess["level"]],
        "level_rules": rules,
        "status": sess["status"],
        "background": sess["background"],
        "faults": faults,
        "resources": {k: v["label"] for k, v in RESOURCES.items()},
        "event": event,
        "time_limit_sec": sess.get("time_limit_sec"),
        "remaining_sec": remaining,
        "started_at": sess["started_at"],
        "score": sess.get("score"),
        "verdict": sess.get("verdict"),
        "suggestion": sess.get("suggestion"),
    }


def start_session(student_no: str, student_name: str, level: int = 0) -> dict:
    """开局：动态生成并发故障。level=0 表示使用学生当前等级"""
    student_no = str(student_no or "").strip()
    if not student_no:
        return {"ok": False, "error": "学号不能为空"}
    data = _load()
    # 幂等：已有进行中的会话直接返回
    for s in data["sessions"].values():
        if s.get("student_no") == student_no and s.get("status") == "active":
            return {"ok": True, "resumed": True, "session": _session_public(s)}

    if not level:
        level = int(data.get("levels", {}).get(student_no, 1))
    level = max(1, min(3, int(level)))
    rules = LEVEL_RULES[level]

    rng = random.Random(uuid.uuid4().hex)
    faults = generate_faults(level, rng)

    time_limit = rules.get("time_limit")
    deadline = None
    if time_limit:
        deadline = (datetime.now() + timedelta(seconds=time_limit)).strftime("%Y-%m-%d %H:%M:%S")

    sess = {
        "session_id": "mf_" + uuid.uuid4().hex[:10],
        "student_no": student_no,
        "student_name": student_name or "",
        "level": level,
        "status": "active",
        "started_at": _now(),
        "finished_at": "",
        "background": rng.choice(SCENARIOS_BG),
        "faults": faults,
        "event": _instantiate_event() if rules.get("insert_event") else None,
        "event_revealed": False,
        "time_limit_sec": time_limit,
        "deadline": deadline,
        "timed_out": False,
        "score": None,
        "verdict": None,
        "suggestion": None,
    }
    data["sessions"][sess["session_id"]] = sess
    _save(data)
    return {"ok": True, "session": _session_public(sess, reveal_event=False)}


def get_session(student_no: str, session_id: str) -> dict:
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    pub = _session_public(sess)  # 先渲染（75秒到点后置 event_revealed=True）
    _save(data)                  # 再持久化揭示状态
    return {"ok": True, "session": pub}


def abandon_session(student_no: str, session_id: str) -> dict:
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    if sess["status"] == "active":
        sess["status"] = "done"
        sess["finished_at"] = _now()
        sess["verdict"] = {"abandoned": True}
        data["history"].append({
            "session_id": sess["session_id"], "student_no": sess["student_no"],
            "student_name": sess.get("student_name", ""), "level": sess["level"],
            "score": 0, "grade": "-", "violations": 0, "major_errors": [],
            "finished_at": sess["finished_at"], "morph": "abandoned",
        })
        _save(data)
    return {"ok": True}


# ============================ 提交评分 ============================

def _kendall_concordance(student_order: list, optimal_order: list) -> float:
    """学生顺序与最优顺序的肯德尔一致对比例 0~1"""
    n = len(student_order)
    if n < 2:
        return 1.0
    opt_pos = {fid: i for i, fid in enumerate(optimal_order)}
    concordant, total = 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = student_order[i], student_order[j]
            if a not in opt_pos or b not in opt_pos:
                continue
            total += 1
            if (opt_pos[a] < opt_pos[b]) == (i < j):
                concordant += 1
    return concordant / total if total else 1.0


def _evaluate_morph(sess: dict, data: dict, major_errors: list) -> list:
    """难度变形：零重大失误且得分≥80 升级；重大失误≥2 降级"""
    events = []
    student_no = sess["student_no"]
    cur = int(data.get("levels", {}).get(student_no, 1))
    if len(major_errors) >= 2 and cur > 1:
        data.setdefault("levels", {})[student_no] = cur - 1
        sess["suggestion"] = {
            "type": "downgrade",
            "text": f"出现 {len(major_errors)} 处重大失误，难度已从 {LEVELS[cur]} 调整为 {LEVELS[cur-1]}，下局生效",
            "before": cur, "after": cur - 1}
        events.append(sess["suggestion"])
    elif not major_errors and sess["score"] is not None and sess["score"] >= 80 and cur < 3:
        data.setdefault("levels", {})[student_no] = cur + 1
        sess["suggestion"] = {
            "type": "upgrade",
            "text": f"零重大失误且得分 {sess['score']}，难度从 {LEVELS[cur]} 升级为 {LEVELS[cur+1]}，下局解锁更多挑战",
            "before": cur, "after": cur + 1}
        events.append(sess["suggestion"])
    return events


def submit(student_no: str, session_id: str, order: list, assignments: dict,
           event_action: str = "", event_position: int = -1) -> dict:
    """提交排障顺序 + 资源分配，仿真评分
    event_action: 'insert' 插入事件故障到 event_position；'ignore' 暂不处理；'' 无事件
    """
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    if sess["status"] != "active":
        return {"ok": False, "error": "会话已结束"}
    if sess.get("deadline") and datetime.now() > datetime.strptime(sess["deadline"], "%Y-%m-%d %H:%M:%S"):
        sess["timed_out"] = True

    faults = list(sess["faults"])
    event = sess.get("event") if sess["level"] == 3 else None
    event_handled = False

    # 组装最终故障全集与最终顺序
    final_order = [fid for fid in (order or []) if any(f["id"] == fid for f in faults)]
    for f in faults:  # 遗漏的补到队尾，视为最低优先级
        if f["id"] not in final_order:
            final_order.append(f["id"])
    if event:
        if event_action == "insert" and sess.get("event_revealed"):
            faults.append(event)
            pos = max(0, min(int(event_position), len(final_order)))
            final_order.insert(pos, event["id"])
            event_handled = True
        elif sess.get("event_revealed"):
            # 事件已揭示却选择忽视：作为未修复故障计入仿真（必违约，产生大损失）
            faults.append(event)
    final_faults = faults
    for f in final_faults:  # 事件等后续加入的故障若不在序列中，补到队尾（视为最低优先级/未排入）
        if f["id"] not in final_order:
            final_order.append(f["id"])
    fmap = {f["id"]: f for f in final_faults}
    final_assign = {fid: (assignments or {}).get(fid, "none") for fid in fmap}
    if event_handled:
        final_assign[event["id"]] = (assignments or {}).get(event["id"], "none")
    elif event and event["id"] in final_assign:
        final_assign[event["id"]] = "none"  # 选择忽视 = 不派单不修复

    # 学生方案仿真 + 最优解
    student_sim = simulate(final_faults, final_order, final_assign)
    optimal = find_optimal(final_faults)
    opt_sim = optimal["sim"]

    # ---- 排序分 ----
    concord = _kendall_concordance(final_order, optimal["order"])
    order_score = round(SCORE_ORDER * concord)

    # ---- 调度分 ----
    constraint_penalty = 0
    major_errors = []
    for f in final_faults:
        res = final_assign.get(f["id"], "none")
        if f.get("secondary_of"):
            if res != "none":
                constraint_penalty += 5
                major_errors.append(f"「{f['title']}」是次生故障，上游恢复后会自动消除，单独派单浪费人力")
        elif f["onsite"] and res == "remote":
            constraint_penalty += 10
            major_errors.append(f"「{f['title']}」必须现场处理，派给远程支持席无效")
    if student_sim["loss"] <= opt_sim["loss"] * 1.05 + 2:
        dispatch_score = SCORE_DISPATCH
    elif opt_sim["loss"] == 0:
        dispatch_score = 0
    else:
        dispatch_score = round(SCORE_DISPATCH * opt_sim["loss"] / max(student_sim["loss"], 1))
    dispatch_score = max(0, dispatch_score - constraint_penalty)

    # 最高紧急度故障被排到最后的重大误判
    # 注意：仅当「最优解并未把它排末位」且「确实造成额外损失」时才判失误，
    # 否则最优损失为 0 时最优顺序本身可能是任意的，会误伤正确方案
    non_secondary = [f for f in final_faults if not f.get("secondary_of")]
    if non_secondary and len(final_order) > 2:
        most_urgent = max(non_secondary, key=urgency_score)
        if (final_order[-1] == most_urgent["id"]
                and optimal["order"][-1] != most_urgent["id"]
                and student_sim["loss"] > opt_sim["loss"]):
            major_errors.append(f"最高紧急度的「{most_urgent['title']}」被排到了最后，造成重大业务损失")

    # ---- 动态决策分 ----
    if not event:
        decision_score = SCORE_DECISION  # 低难度无事件，自动满分
    elif not event_handled:
        decision_score = 0
        major_errors.append("突发事件被忽视未排入处置序列，重大活动保障失守")
    else:
        opt_pos = optimal["order"].index(event["id"]) if event["id"] in optimal["order"] else 0
        stu_pos = final_order.index(event["id"])
        gap = abs(opt_pos - stu_pos)
        decision_score = SCORE_DECISION if gap <= 1 else (12 if gap == 2 else 4)

    # ---- 零重大失误加分 ----
    clean_score = SCORE_CLEAN if not major_errors else 0

    score = order_score + dispatch_score + decision_score + clean_score
    if sess["timed_out"]:
        score -= 10
    score = max(0, min(100, score))
    sess["score"] = score
    grade = "S" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"

    # ---- 复盘明细（提交后揭示）----
    reveal = []
    opt_assign = optimal["assignments"]
    opt_completion = opt_sim["completion"]
    stu_completion = student_sim["completion"]
    for f in final_faults:
        secondary = bool(f.get("secondary_of"))
        reveal.append({
            "id": f["id"], "title": f["title"], "domain_label": f["domain_label"],
            "biz_type": f["biz_type"], "biz_weight": f["biz_weight"],
            "users": f["users"], "sla": f["sla"], "repair": f["repair"],
            "onsite": f["onsite"], "is_event": bool(f.get("is_event")),
            "urgency": round(urgency_score(f), 1),
            "secondary": secondary,
            "secondary_of_title": (fmap[f["secondary_of"]]["title"]
                                   if secondary and f.get("secondary_of") in fmap else ""),
            "clue": (FAULT_TEMPLATES.get(f.get("template"), {}).get("clue", "")
                     if secondary else ""),
            "student_rank": final_order.index(f["id"]) + 1,
            "optimal_rank": optimal["order"].index(f["id"]) + 1,
            "student_resource": RESOURCES.get(final_assign.get(f["id"]), {}).get("label", "不派单"),
            "optimal_resource": ("不派单（次生自动消除）" if secondary
                                 else RESOURCES.get(opt_assign.get(f["id"]), {}).get("label", "不派单")),
            "student_done_min": stu_completion.get(f["id"]),
            "optimal_done_min": opt_completion.get(f["id"]),
            "student_violated": f["id"] in student_sim["violations"],
            "optimal_violated": f["id"] in opt_sim["violations"],
        })
    reveal.sort(key=lambda r: r["optimal_rank"])

    sess["verdict"] = {
        "order_score": order_score, "dispatch_score": dispatch_score,
        "decision_score": decision_score, "clean_score": clean_score,
        "concordance": round(concord, 3),
        "student_loss": student_sim["loss"], "optimal_loss": opt_sim["loss"],
        "student_violations": len(student_sim["violations"]),
        "optimal_violations": len(opt_sim["violations"]),
        "major_errors": major_errors,
        "timed_out": sess["timed_out"],
        "grade": grade,
        "reveal": reveal,
        "optimal_order": optimal["order"],
    }

    sess["status"] = "done"
    sess["finished_at"] = _now()
    morph = _evaluate_morph(sess, data, major_errors)
    data["history"].append({
        "session_id": sess["session_id"], "student_no": sess["student_no"],
        "student_name": sess.get("student_name", ""), "level": sess["level"],
        "score": score, "grade": grade,
        "order_score": order_score, "dispatch_score": dispatch_score,
        "decision_score": decision_score,
        "student_loss": student_sim["loss"], "optimal_loss": opt_sim["loss"],
        "violations": len(student_sim["violations"]),
        "major_errors": len(major_errors),
        "timed_out": sess["timed_out"],
        "finished_at": sess["finished_at"],
        "morph": morph[0]["type"] if morph else "",
    })
    data["history"] = data["history"][-200:]
    _save(data)
    return {"ok": True, "score": score, "grade": grade, "verdict": sess["verdict"],
            "suggestion": sess.get("suggestion"),
            "session": _session_public(sess)}


# ============================ 历史与统计 ============================

def get_history(student_no: str = "", limit: int = 50) -> list:
    data = _load()
    hist = data.get("history", [])
    if student_no:
        hist = [h for h in hist if h.get("student_no") == str(student_no)]
    return list(reversed(hist[-limit:]))


def stats_overview() -> dict:
    data = _load()
    hist = data.get("history", [])
    done = [h for h in hist if h.get("morph") != "abandoned"]
    avg = round(sum(h.get("score", 0) for h in done) / len(done), 1) if done else 0
    by_level = {}
    for h in done:
        lv = h.get("level", 1)
        by_level.setdefault(lv, {"count": 0, "total": 0})
        by_level[lv]["count"] += 1
        by_level[lv]["total"] += h.get("score", 0)
    level_stats = [{"level": lv, "label": LEVELS[lv],
                    "count": v["count"], "avg": round(v["total"] / v["count"], 1)}
                   for lv, v in sorted(by_level.items())]
    return {
        "total_sessions": len(hist),
        "completed": len(done),
        "avg_score": avg,
        "upgrades": len([h for h in done if h.get("morph") == "upgrade"]),
        "downgrades": len([h for h in done if h.get("morph") == "downgrade"]),
        "level_stats": level_stats,
        "active_sessions": len([s for s in data.get("sessions", {}).values()
                                if s.get("status") == "active"]),
    }
