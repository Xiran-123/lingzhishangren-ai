# -*- coding: utf-8 -*-
"""
安全与隐私合规（Security & Compliance）

三件事：
1. 凭据安全：密码一律以哈希（pbkdf2:sha256 + 随机盐）落盘，历史明文凭据在首次启动时自动迁移
2. 权限统一：@login_required / @require_role 装饰器，替代散落在各路由里的 if 判断
3. 操作审计：高危操作写入 data/audit_log.jsonl（谁、何时、从哪、对谁、改了什么），可追溯
4. 数据脱敏：姓名、学号统一打码，防止个人信息在批量返回/导出时明文外泄

依赖 werkzeug 的密码哈希实现（Flask 自带，无额外依赖）。
"""

import json
import os
import re
import threading
from datetime import datetime
from functools import wraps

from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

DATA_DIR = "data"
CREDENTIAL_FILE = os.path.join(DATA_DIR, "credentials.json")
AUDIT_FILE = os.path.join(DATA_DIR, "audit_log.jsonl")

AUDIT_MAX_BYTES = 5 * 1024 * 1024   # 审计日志超过 5MB 自动滚动，只保留最近 2000 条
AUDIT_KEEP_LINES = 2000

_HASH_PREFIXES = ("pbkdf2:", "scrypt:", "argon2")
_lock = threading.Lock()

HASH_METHOD = "pbkdf2:sha256"
HASH_SALT_LENGTH = 16


def _hash(password: str) -> str:
    """统一的密码哈希入口（pbkdf2:sha256 + 16 字节随机盐，不依赖 OpenSSL scrypt）"""
    return generate_password_hash(password, method=HASH_METHOD, salt_length=HASH_SALT_LENGTH)


ROLE_LABELS = {"teacher": "老师", "student": "学生"}

# 高危操作类型（用于审计分类与看板统计）
AUDIT_ACTIONS = {
    "login": "登录",
    "login_failed": "登录失败",
    "class_create": "新建班级",
    "class_update": "修改班级",
    "class_delete": "删除班级",
    "class_add_student": "班级添加学生",
    "class_remove_student": "班级移除学生",
    "student_add": "新增学生",
    "student_delete": "删除学生",
    "knowledge_upload": "上传知识库",
    "knowledge_delete": "删除知识库",
    "knowledge_append": "知识入库",
    "rag_rebuild": "重建向量索引",
    "frontier_review": "前沿知识审核",
    "credential_append": "成长记录上链",
    "credential_certificate": "签发证书",
    "homework_publish": "发布作业",
    "password_migrate": "凭据哈希迁移",
    "fault_chain_start": "故障链开局",
    "fault_chain_diagnose": "故障链诊断",
    "fault_chain_morph": "难度自适应调整",
}


# ============================ 基础工具 ============================

def _ensure_dir():
    if DATA_DIR and not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_hashed(value: str) -> bool:
    """判断存储值是否为密码哈希（而非历史明文）"""
    if not isinstance(value, str) or not value:
        return False
    return value.startswith(_HASH_PREFIXES) or ("$" in value and ":" in value.split("$")[0])


# ============================ 凭据存储 ============================

def _load_store() -> dict:
    _ensure_dir()
    if os.path.exists(CREDENTIAL_FILE):
        try:
            with open(CREDENTIAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("teachers", {})
                return data
        except (OSError, ValueError) as e:
            print(f"[Security] 凭据文件读取失败: {e}")
    return {"version": 1, "access_password": "", "teachers": {}, "created_at": _now(), "migrated_at": ""}


def _save_store(store: dict):
    _ensure_dir()
    tmp = CREDENTIAL_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CREDENTIAL_FILE)


def init_credentials(teacher_accounts: dict = None, access_password: str = "") -> dict:
    """初始化凭据库：把历史明文密码升级为哈希（幂等，可重复调用）"""
    store = _load_store()
    migrated = 0

    if access_password:
        cur = store.get("access_password", "")
        if not is_hashed(cur):
            store["access_password"] = _hash(access_password)
            migrated += 1
    elif not is_hashed(store.get("access_password", "")):
        # 凭据库缺失且未提供明文种子：写入默认演示密码的哈希
        store["access_password"] = _hash("tongxin2024")
        migrated += 1

    teachers = store.setdefault("teachers", {})
    for name, pwd in (teacher_accounts or {}).items():
        cur = teachers.get(name, "")
        if not is_hashed(cur):
            teachers[name] = _hash(str(pwd))
            migrated += 1

    if not store.get("created_at"):
        store["created_at"] = _now()
    if migrated:
        store["migrated_at"] = _now()
    _save_store(store)
    if migrated:
        print(f"[Security] 凭据已哈希化：本次迁移 {migrated} 条，明文密码不再落盘")
    return {"migrated": migrated, "teachers": len(teachers), "file": CREDENTIAL_FILE}


def verify_teacher(username: str, password: str) -> bool:
    if not username or not password:
        return False
    store = _load_store()
    stored = store.get("teachers", {}).get(username, "")
    if not stored:
        return False
    if is_hashed(stored):
        return check_password_hash(stored, password)
    return False


def verify_access_password(password: str) -> bool:
    """校验统一访问密码（学生入口）"""
    if not password:
        return False
    store = _load_store()
    stored = store.get("access_password", "")
    if not is_hashed(stored):
        return False
    return check_password_hash(stored, password)


def credential_status() -> dict:
    """凭据库状态：是否已全部哈希化、账号数量"""
    store = _load_store()
    teachers = store.get("teachers", {})
    plain = [n for n, v in teachers.items() if not is_hashed(v)]
    if not is_hashed(store.get("access_password", "")):
        plain.append("access_password")
    return {
        "file": CREDENTIAL_FILE,
        "exists": os.path.exists(CREDENTIAL_FILE),
        "hashed": not plain,
        "plain_left": plain,
        "teachers": len(teachers),
        "created_at": store.get("created_at", ""),
        "migrated_at": store.get("migrated_at", ""),
    }


# ============================ 操作审计 ============================

def _actor_from_context() -> dict:
    """从请求上下文取操作人信息；无上下文（如定时任务）时返回空值"""
    info = {"actor": "", "role": "", "ip": ""}
    try:
        if session:
            info["actor"] = session.get("student_name") or session.get("student_no") or ""
            info["role"] = session.get("role", "")
        if request:
            info["ip"] = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or \
                (request.remote_addr or "")
    except Exception:  # noqa: BLE001 - 无请求上下文时忽略
        pass
    return info


def _rotate_if_needed():
    try:
        if os.path.exists(AUDIT_FILE) and os.path.getsize(AUDIT_FILE) > AUDIT_MAX_BYTES:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(AUDIT_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-AUDIT_KEEP_LINES:])
            print(f"[Security] 审计日志已滚动，保留最近 {AUDIT_KEEP_LINES} 条")
    except OSError as e:
        print(f"[Security] 审计日志滚动失败: {e}")


def audit(action: str, target: str = "", detail: str = "", before=None, after=None,
          actor: str = "", role: str = "", ip: str = "") -> dict:
    """写入一条审计记录。action 建议取 AUDIT_ACTIONS 中的键"""
    ctx = _actor_from_context()
    entry = {
        "ts": _now(),
        "action": action,
        "action_label": AUDIT_ACTIONS.get(action, action),
        "actor": actor or ctx["actor"],
        "role": role or ctx["role"],
        "ip": ip or ctx["ip"],
        "target": target,
        "detail": detail,
    }
    if before is not None:
        entry["before"] = before
    if after is not None:
        entry["after"] = after
    try:
        _ensure_dir()
        with _lock:
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            _rotate_if_needed()
    except OSError as e:
        print(f"[Security] 审计写入失败: {e}")
    return entry


def read_audit(limit: int = 200, action: str = "", keyword: str = "") -> list:
    """读取审计记录（倒序，最新在前）"""
    if not os.path.exists(AUDIT_FILE):
        return []
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"[Security] 审计读取失败: {e}")
        return []
    records = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if action and rec.get("action") != action:
            continue
        if keyword and keyword not in json.dumps(rec, ensure_ascii=False):
            continue
        records.append(rec)
        if len(records) >= limit:
            break
    return records


def audit_stats() -> dict:
    """审计概览：总条数、最近记录时间、按操作类型分布"""
    if not os.path.exists(AUDIT_FILE):
        return {"total": 0, "last_ts": "", "by_action": [], "size_kb": 0}
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
    except OSError:
        return {"total": 0, "last_ts": "", "by_action": [], "size_kb": 0}

    counts = {}
    last_ts = ""
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        a = rec.get("action", "unknown")
        counts[a] = counts.get(a, 0) + 1
        if rec.get("ts", "") > last_ts:
            last_ts = rec["ts"]
    by_action = [{"action": a, "label": AUDIT_ACTIONS.get(a, a), "count": c}
                 for a, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]
    return {"total": len(lines), "last_ts": last_ts, "by_action": by_action,
            "size_kb": round(os.path.getsize(AUDIT_FILE) / 1024, 1)}


# ============================ 权限装饰器 ============================

def login_required(view):
    """仅要求已登录"""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "请先登录"}), 401
        return view(*args, **kwargs)
    return wrapper


def require_role(*roles):
    """要求已登录且角色在 roles 中（如 @require_role('teacher')）"""
    allowed = tuple(roles)

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("authenticated"):
                return jsonify({"error": "请先登录"}), 401
            if session.get("role") not in allowed:
                names = "、".join(ROLE_LABELS.get(r, r) for r in allowed)
                return jsonify({"error": f"权限不足：该操作仅限{names}"}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ============================ 数据脱敏 ============================

_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
_LONG_DIGIT_RE = re.compile(r"\b\d{11,}\b")


def mask_name(name: str) -> str:
    """姓名脱敏：保留姓氏，其余打码（李昊 → 李*）"""
    name = (name or "").strip()
    if not name:
        return ""
    if len(name) == 1:
        return name
    return name[0] + "*" * (len(name) - 1)


def mask_student_no(student_no: str, keep_tail: int = 0) -> str:
    """学号脱敏：默认全部打码；keep_tail>0 时保留末尾若干位"""
    no = str(student_no or "").strip()
    if not no:
        return ""
    if keep_tail <= 0 or len(no) <= keep_tail:
        return "*" * len(no)
    return "*" * (len(no) - keep_tail) + no[-keep_tail:]


def mask_phone(text: str) -> str:
    return _PHONE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text or "")


def desensitize_student(student: dict, keep_no_tail: int = 0) -> dict:
    """学生记录脱敏：姓名打码、学号打码，其余字段原样保留"""
    if not isinstance(student, dict):
        return student
    out = dict(student)
    if "name" in out:
        out["name"] = mask_name(out.get("name", ""))
    if "student_no" in out:
        out["student_no"] = mask_student_no(out.get("student_no", ""), keep_no_tail)
    if "phone" in out:
        out["phone"] = mask_phone(str(out.get("phone", "")))
    return out


def desensitize_students(students: list, keep_no_tail: int = 0) -> list:
    return [desensitize_student(s, keep_no_tail) for s in (students or [])]


def desensitize_text(text: str) -> str:
    """文本脱敏：把文中出现的手机号、长数字串（如学号）打码"""
    text = mask_phone(text or "")
    return _LONG_DIGIT_RE.sub(lambda m: "*" * len(m.group(0)), text)
