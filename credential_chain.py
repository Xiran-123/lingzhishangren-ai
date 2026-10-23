# -*- coding: utf-8 -*-
"""
哈希链可信成长档案（Credential Chain）

设计目标：让学生的成长记录具备「不可篡改、可溯源、可对外验证」的能力。
- 每条记录包含 payload_hash（业务内容指纹）与 prev_hash（前一条记录指纹）
- record_hash = sha256(学号|序号|prev_hash|payload_hash|时间)，把整条链串起来
- 任意一条记录被修改、删除或插入，后续所有记录的校验都会失败 → 篡改必然暴露
- 证书只固化「签发时刻的链头指纹」，企业可通过证书编号在线验真（脱敏展示）

不依赖区块链，纯本地哈希链即可实现防篡改与可验证，部署零成本。
"""

import hashlib
import json
import os
import re
import uuid
from datetime import datetime

DATA_DIR = "data"
CREDENTIAL_FILE = os.path.join(DATA_DIR, "credential_chain.json")

# ====================== TiDB 数据库支持 ======================
try:
    import pymysql as _pymysql
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    _pymysql = None

_CC_DB_CONFIG = {
    'host': os.environ.get('DB_HOST', '8.155.130.156'),
    'port': int(os.environ.get('DB_PORT', '4000')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'lingzhishangren'),
    'charset': 'utf8mb4',
    'connect_timeout': 5,
}

_cc_db_ready = False


def _cc_get_db():
    global _cc_db_ready
    if not _DB_AVAILABLE:
        return None
    if not _cc_db_ready:
        try:
            _pymysql.connect(**_CC_DB_CONFIG).close()
            _cc_db_ready = True
        except Exception:
            _cc_db_ready = False
            return None
    try:
        return _pymysql.connect(**_CC_DB_CONFIG, cursorclass=_pymysql.cursors.DictCursor)
    except Exception:
        _cc_db_ready = False
        return None

# 创世指纹：每个学生链的第一条记录的前驱
GENESIS_HASH = "0" * 64

# 记录类型（与 12 维能力评价口径保持一致：过程性、可追溯）
RECORD_TYPES = {
    "learning": "学习行为",
    "task": "任务完成",
    "exam": "考核成绩",
    "skill": "能力测评",
    "job": "岗位匹配",
    "frontier": "前沿学习",
    "ethics": "工程伦理",
    "honor": "表彰记录",
}

SOURCE_LABELS = {
    "system_sync": "系统自动同步",
    "teacher_manual": "教师录入",
    "student_self": "学生提交",
}


# ============================ 基础工具 ============================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj) -> str:
    """规范化序列化：键排序 + 紧凑分隔符，保证同一内容指纹恒定"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _ensure_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def init_credential_data():
    """初始化档案文件（首次运行自动创建 + DB 空表自动迁移）"""
    _ensure_dir()
    if not os.path.exists(CREDENTIAL_FILE):
        _cc_save({"version": 1, "created_at": _now(), "updated_at": _now(), "chains": {}})
    db = _cc_get_db()
    if db is not None:
        try:
            cur = db.cursor()
            cur.execute('SELECT COUNT(*) FROM credential_chain_state')
            if cur.fetchone()['COUNT(*)'] == 0 and os.path.exists(CREDENTIAL_FILE):
                with open(CREDENTIAL_FILE, 'r', encoding='utf-8') as f:
                    jdata = json.load(f)
                cur.execute("""INSERT INTO credential_chain_state (state_json, version, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)""",
                    (json.dumps(jdata, ensure_ascii=False), jdata.get('version', 1),
                     jdata.get('created_at') or None, jdata.get('updated_at') or None))
                db.commit()
                print("[成长档案] 从 JSON 导入状态到 TiDB")
            db.close()
        except Exception as e:
            print(f"[成长档案] DB 迁移失败: {e}")
            try: db.close()
            except Exception: pass


def _cc_load() -> dict:
    db = _cc_get_db()
    if db is not None:
        try:
            cur = db.cursor()
            cur.execute('SELECT state_json FROM credential_chain_state ORDER BY id DESC LIMIT 1')
            row = cur.fetchone()
            db.close()
            if row:
                state = json.loads(row['state_json']) if isinstance(row['state_json'], str) else row['state_json']
                if isinstance(state, dict):
                    state.setdefault("chains", {})
                    return state
        except Exception as e:
            print(f"[成长档案] DB 读取失败（降级 JSON）: {e}")
            try: db.close()
            except Exception: pass
    # --- 降级 JSON ---
    _ensure_dir()
    if not os.path.exists(CREDENTIAL_FILE):
        return {"version": 1, "created_at": _now(), "updated_at": _now(), "chains": {}}
    try:
        with open(CREDENTIAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("档案文件结构异常")
        data.setdefault("chains", {})
        return data
    except Exception as e:
        print(f"[成长档案] 读取失败，使用空档案: {e}")
        return {"version": 1, "created_at": _now(), "updated_at": _now(), "chains": {}}


def _cc_save(data: dict):
    """保存成长档案（DB 优先 + JSON 降级）"""
    data["updated_at"] = _now()
    db = _cc_get_db()
    if db is not None:
        try:
            cur = db.cursor()
            cur.execute('SELECT id FROM credential_chain_state ORDER BY id DESC LIMIT 1')
            existing = cur.fetchone()
            state_json = json.dumps(data, ensure_ascii=False)
            if existing:
                cur.execute("""UPDATE credential_chain_state
                    SET state_json=%s, version=%s, updated_at=%s WHERE id=%s""",
                    (state_json, data.get('version', 1), data.get('updated_at'), existing['id']))
            else:
                cur.execute("""INSERT INTO credential_chain_state (state_json, version, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)""",
                    (state_json, data.get('version', 1), data.get('created_at'), data.get('updated_at')))
            db.commit()
            db.close()
            return
        except Exception as e:
            print(f"[成长档案] DB 保存失败（降级 JSON）: {e}")
            try: db.close()
            except Exception: pass
    # --- 降级 JSON ---
    _ensure_dir()
    tmp = CREDENTIAL_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CREDENTIAL_FILE)


def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _as_list(value):
    """把各种可能的容器统一成 list"""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # {student: [ ... ]} 形式
        merged = []
        for v in value.values():
            if isinstance(v, list):
                merged.extend([x for x in v if isinstance(x, dict)])
        return merged
    return []


# ============================ 哈希计算 ============================

def _payload_of(rec: dict) -> dict:
    """业务内容（参与指纹计算，不含哈希字段本身）"""
    return {
        "student_no": rec.get("student_no", ""),
        "seq": rec.get("seq", 0),
        "type": rec.get("type", ""),
        "title": rec.get("title", ""),
        "detail": rec.get("detail", ""),
        "value": rec.get("value", ""),
        "source": rec.get("source", ""),
        "source_ref": rec.get("source_ref", ""),
        "created_at": rec.get("created_at", ""),
    }


def _payload_hash(payload: dict) -> str:
    return _sha256(_canonical(payload))


def _record_hash(student_no: str, seq: int, prev_hash: str, payload_hash: str, created_at: str) -> str:
    return _sha256(f"{student_no}|{seq}|{prev_hash}|{payload_hash}|{created_at}")


# ============================ 链操作 ============================

def _get_chain(data: dict, student_no: str) -> dict:
    chains = data.setdefault("chains", {})
    if student_no not in chains:
        chains[student_no] = {
            "student_no": student_no,
            "student_name": "",
            "records": [],
            "head_hash": GENESIS_HASH,
            "updated_at": _now(),
            "certificates": [],
        }
    chain = chains[student_no]
    chain.setdefault("records", [])
    chain.setdefault("certificates", [])
    chain.setdefault("head_hash", GENESIS_HASH)
    return chain


def append_record(student_no: str, student_name: str, rec_type: str, title: str,
                  detail: str = "", value=None, source: str = "teacher_manual",
                  source_ref: str = "", created_at: str = "", student_class: str = "") -> dict:
    """追加一条成长记录并上链。

    source_ref 非空时具备幂等性：同一来源重复同步不会产生重复记录。
    """
    student_no = str(student_no or "").strip()
    if not student_no:
        return {"ok": False, "error": "学号不能为空"}
    if rec_type not in RECORD_TYPES:
        return {"ok": False, "error": f"未知记录类型: {rec_type}"}
    title = (title or "").strip()
    if not title:
        return {"ok": False, "error": "记录标题不能为空"}

    data = _cc_load()
    chain = _get_chain(data, student_no)

    # 幂等：同来源指纹已存在则跳过
    if source_ref:
        for r in chain["records"]:
            if r.get("source_ref") == source_ref:
                return {"ok": True, "skipped": True, "record_id": r.get("record_id"),
                        "seq": r.get("seq"), "message": "该来源记录已存在，跳过"}

    seq = len(chain["records"]) + 1
    prev_hash = chain["records"][-1]["record_hash"] if chain["records"] else GENESIS_HASH
    rec = {
        "seq": seq,
        "record_id": "CR-" + uuid.uuid4().hex[:12],
        "student_no": student_no,
        "student_name": student_name or chain.get("student_name") or "",
        "type": rec_type,
        "title": title,
        "detail": (detail or "").strip(),
        "value": "" if value is None else str(value),
        "source": source,
        "source_ref": source_ref or "",
        "created_at": created_at or _now(),
        "prev_hash": prev_hash,
    }
    rec["payload_hash"] = _payload_hash(_payload_of(rec))
    rec["record_hash"] = _record_hash(student_no, seq, prev_hash, rec["payload_hash"], rec["created_at"])

    chain["records"].append(rec)
    if student_name:
        chain["student_name"] = student_name
    if student_class:
        chain["student_class"] = student_class
    chain["head_hash"] = rec["record_hash"]
    chain["updated_at"] = _now()
    _cc_save(data)

    return {"ok": True, "record": rec, "seq": seq, "chain_count": len(chain["records"])}


def get_records(student_no: str, rec_type: str = "") -> list:
    data = _cc_load()
    chain = data.get("chains", {}).get(str(student_no), {})
    records = list(chain.get("records", []))
    if rec_type:
        records = [r for r in records if r.get("type") == rec_type]
    return records


def get_chain_summary(student_no: str) -> dict:
    """链概览：记录数、类型分布、链头、最近记录、证书数"""
    data = _cc_load()
    chain = data.get("chains", {}).get(str(student_no), {})
    records = chain.get("records", [])
    type_stats = {}
    for r in records:
        key = r.get("type", "")
        type_stats[key] = type_stats.get(key, 0) + 1
    return {
        "student_no": str(student_no),
        "student_name": chain.get("student_name", ""),
        "student_class": chain.get("student_class", ""),
        "record_count": len(records),
        "type_stats": type_stats,
        "type_stats_labeled": [{"type": k, "label": RECORD_TYPES.get(k, k), "count": v}
                               for k, v in sorted(type_stats.items(), key=lambda x: -x[1])],
        "head_hash": chain.get("head_hash", GENESIS_HASH),
        "first_record_at": records[0]["created_at"] if records else "",
        "last_record_at": records[-1]["created_at"] if records else "",
        "updated_at": chain.get("updated_at", ""),
        "certificate_count": len(chain.get("certificates", [])),
    }


def verify_chain(student_no: str) -> dict:
    """逐条重算指纹，校验整条链的完整性。

    能识别三类破坏：
    - 内容被改 → payload_hash / record_hash 不符
    - 记录被删 → 序号断裂 或 prev_hash 不连续
    - 记录被插 → prev_hash 不连续
    """
    data = _cc_load()
    chain = data.get("chains", {}).get(str(student_no), {})
    records = chain.get("records", [])
    result = {
        "student_no": str(student_no),
        "student_name": chain.get("student_name", ""),
        "total": len(records),
        "checked": 0,
        "valid": True,
        "broken_at": None,
        "reason": "",
        "head_hash": chain.get("head_hash", GENESIS_HASH),
        "verified_at": _now(),
    }
    if not records:
        result["reason"] = "该学生暂无成长记录，无法校验"
        return result

    expected_prev = GENESIS_HASH
    for idx, rec in enumerate(records, 1):
        seq = rec.get("seq")
        if seq != idx:
            result["valid"] = False
            result["broken_at"] = idx
            result["reason"] = f"第 {idx} 条记录的序号为 {seq}，序号断裂（疑似记录被删除）"
            return result
        if rec.get("prev_hash") != expected_prev:
            result["valid"] = False
            result["broken_at"] = idx
            result["reason"] = f"第 {idx} 条记录的前驱指纹不匹配（疑似记录被删除或插入）"
            return result
        payload_hash = _payload_hash(_payload_of(rec))
        if payload_hash != rec.get("payload_hash"):
            result["valid"] = False
            result["broken_at"] = idx
            result["reason"] = f"第 {idx} 条记录内容指纹不符（记录内容被篡改）"
            return result
        expect_rec_hash = _record_hash(str(student_no), seq, rec.get("prev_hash", ""),
                                       payload_hash, rec.get("created_at", ""))
        if expect_rec_hash != rec.get("record_hash"):
            result["valid"] = False
            result["broken_at"] = idx
            result["reason"] = f"第 {idx} 条记录指纹不符（记录被篡改）"
            return result
        expected_prev = rec["record_hash"]
        result["checked"] = idx

    if chain.get("head_hash") and chain["head_hash"] != expected_prev:
        result["valid"] = False
        result["reason"] = "链头指纹与档案记录不一致（档案索引被改动）"
        return result

    result["reason"] = f"校验通过：{len(records)} 条记录指纹连续且完整"
    return result


def list_chains() -> list:
    """所有学生链概览（教师端）"""
    data = _cc_load()
    out = []
    for student_no, chain in data.get("chains", {}).items():
        records = chain.get("records", [])
        out.append({
            "student_no": student_no,
            "student_name": chain.get("student_name", ""),
            "student_class": chain.get("student_class", ""),
            "record_count": len(records),
            "head_hash": chain.get("head_hash", GENESIS_HASH),
            "last_record_at": records[-1].get("created_at", "") if records else "",
            "certificate_count": len(chain.get("certificates", [])),
            "updated_at": chain.get("updated_at", ""),
        })
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out


# ============================ 脱敏 ============================

def mask_name(name: str) -> str:
    """姓名脱敏：李昊 → 李*，欧阳修文 → 欧***"""
    name = (name or "").strip()
    if not name:
        return "匿名"
    if len(name) == 1:
        return name + "*"
    return name[0] + "*" * (len(name) - 1)


def mask_student_no(student_no: str) -> str:
    """学号脱敏：仅保留后 4 位"""
    s = str(student_no or "").strip()
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


# ============================ 证书 ============================

def make_certificate(student_no: str, issuer: str = "灵智尚人平台",
                     extra_snapshot: dict = None) -> dict:
    """签发（或复用）当前链头对应的可信成长证书。

    同一链头只签发一张，重复调用返回已有证书。
    """
    data = _cc_load()
    chain = data.get("chains", {}).get(str(student_no), {})
    records = chain.get("records", [])
    if not records:
        return {"ok": False, "error": "暂无成长记录，无法签发证书"}

    head_hash = chain.get("head_hash", "")
    chain["certificates"] = chain.get("certificates", [])

    # 同一链头复用已签发证书
    for cert in chain["certificates"]:
        if cert.get("head_hash") == head_hash:
            return {"ok": True, "reused": True, "certificate": cert,
                    "message": "该链头已签发证书，直接返回"}

    issues_at = _now()
    date_part = datetime.now().strftime("%Y%m%d")
    cert_id = f"LZSR-{date_part}-{str(student_no)[-4:].zfill(4)}-{head_hash[:8].upper()}"

    type_stats = {}
    for r in records:
        type_stats[r.get("type", "")] = type_stats.get(r.get("type", ""), 0) + 1

    snapshot = {
        "holder_name_masked": mask_name(chain.get("student_name", "")),
        "holder_no_masked": mask_student_no(student_no),
        "class_name": chain.get("student_class", ""),
        "record_count": len(records),
        "type_stats": type_stats,
        "first_record_at": records[0].get("created_at", ""),
        "last_record_at": records[-1].get("created_at", ""),
    }
    if isinstance(extra_snapshot, dict):
        for k, v in extra_snapshot.items():
            if v not in (None, "", [], {}):
                snapshot[k] = v

    cert = {
        "certificate_id": cert_id,
        "student_no": str(student_no),
        "head_hash": head_hash,
        "chain_count": len(records),
        "issued_at": issues_at,
        "issuer": issuer,
        "status": "valid",          # valid / revoked
        "snapshot": snapshot,
        "verify_path": f"/verify/{cert_id}",
    }
    chain["certificates"].append(cert)
    _cc_save(data)
    return {"ok": True, "reused": False, "certificate": cert}


def _find_certificate(data: dict, certificate_id: str):
    for student_no, chain in data.get("chains", {}).items():
        for cert in chain.get("certificates", []):
            if cert.get("certificate_id") == certificate_id:
                return student_no, chain, cert
    return None, None, None


def get_student_certificates(student_no: str) -> list:
    data = _cc_load()
    chain = data.get("chains", {}).get(str(student_no), {})
    return list(chain.get("certificates", []))


def verify_certificate(certificate_id: str) -> dict:
    """证书验真（企业/第三方可访问，返回脱敏信息 + 实时链校验结果）"""
    certificate_id = (certificate_id or "").strip()
    out = {
        "certificate_id": certificate_id,
        "found": False,
        "valid": False,
        "message": "",
        "checked_at": _now(),
    }
    if not certificate_id:
        out["message"] = "证书编号为空"
        return out

    data = _cc_load()
    student_no, chain, cert = _find_certificate(data, certificate_id)
    if not cert:
        out["message"] = "未查询到该证书编号，请确认编号是否正确"
        return out

    out["found"] = True
    chain_result = verify_chain(student_no)
    records = chain.get("records", [])
    type_counts = {}
    for r in records:
        key = r.get("type", "")
        type_counts[key] = type_counts.get(key, 0) + 1

    out.update({
        "issuer": cert.get("issuer", ""),
        "issued_at": cert.get("issued_at", ""),
        "status": cert.get("status", "valid"),
        "cert_head_hash": cert.get("head_hash", ""),
        "cert_chain_count": cert.get("chain_count", 0),
        "current_head_hash": chain_result.get("head_hash", ""),
        "holder": {
            "name": cert.get("snapshot", {}).get("holder_name_masked", "匿名"),
            "student_no": cert.get("snapshot", {}).get("holder_no_masked", ""),
            "class_name": cert.get("snapshot", {}).get("class_name", ""),
            "major": cert.get("snapshot", {}).get("major", ""),
            "ability_summary": cert.get("snapshot", {}).get("ability_summary", ""),
        },
        "summary": {
            "record_count": len(records),
            "type_stats": [
                {"type": k, "label": RECORD_TYPES.get(k, k), "count": v}
                for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
            ],
            "first_record_at": records[0].get("created_at", "") if records else "",
            "last_record_at": records[-1].get("created_at", "") if records else "",
        },
        "chain": {
            "valid": chain_result.get("valid"),
            "reason": chain_result.get("reason", ""),
            "total": chain_result.get("total", 0),
            "checked": chain_result.get("checked", 0),
            "broken_at": chain_result.get("broken_at"),
        },
    })

    if cert.get("status") != "valid":
        out["valid"] = False
        out["message"] = "该证书已被签发方撤销"
    elif not chain_result.get("valid"):
        out["valid"] = False
        out["message"] = f"档案哈希链校验失败：{chain_result.get('reason', '')}"
    else:
        out["valid"] = True
        out["message"] = "校验通过：证书有效，档案哈希链完整、未被篡改"
        new_count = len(records) - int(cert.get("chain_count") or 0)
        if new_count > 0:
            out["message"] += f"（签发后新增 {new_count} 条成长记录，可申请重新签发）"
    return out


# ============================ 从业务数据同步上链 ============================

def sync_from_sources(student_no: str, student_name: str, student_class: str = "") -> dict:
    """把系统中已有的业务数据聚合为成长记录并上链（幂等，可反复执行）。

    数据源：学习行为记录 / 错题本 / 作业提交 / 模拟面试 / 自评画像 / 能力测评
    """
    added, skipped, sources = 0, 0, {}

    jobs = []

    # 1. 学习行为记录 {student_name: [{activity_type, knowledge_point, score, timestamp}]}
    lr = _read_json(os.path.join(DATA_DIR, "learning_records.json"), {})
    if isinstance(lr, dict):
        for item in lr.get(student_name, []) or []:
            if not isinstance(item, dict):
                continue
            kp = item.get("knowledge_point") or item.get("activity_type") or "学习活动"
            jobs.append(("learning", f"学习行为：{item.get('activity_type') or '学习'}", kp,
                         item.get("score"), "system_sync", item.get("timestamp", "")))

    # 2. 错题本（按学生姓名归档）
    for item in _as_list(_read_json(os.path.join(DATA_DIR, "wrong_questions.json"), [])):
        if item.get("student_name") != student_name:
            continue
        mastered = "已掌握" if item.get("mastered") else f"待加强（累计错 {item.get('count', 1)} 次）"
        jobs.append(("learning", f"错题纠正：{item.get('knowledge_point') or '未知知识点'}",
                     f"题目：{item.get('question', '')}｜状态：{mastered}",
                     None, "system_sync", item.get("created_at", "")))

    # 3. 作业提交记录
    for item in _as_list(_read_json(os.path.join(DATA_DIR, "homework_submissions.json"), [])):
        if str(item.get("student_no") or "") != str(student_no) and item.get("student_name") != student_name:
            continue
        score = item.get("score") or item.get("total_score")
        jobs.append(("exam", f"作业提交：{item.get('homework_title') or item.get('title') or '作业'}",
                     f"得分：{score if score is not None else '待批阅'}",
                     score, "system_sync", item.get("submitted_at") or item.get("created_at", "")))

    # 4. 模拟面试记录
    for item in _as_list(_read_json(os.path.join(DATA_DIR, "interview_records.json"), [])):
        if str(item.get("student_no") or "") != str(student_no) and item.get("student_name") != student_name:
            continue
        jobs.append(("skill", f"模拟面试：{item.get('job_name') or item.get('position') or '综合'}",
                     f"综合评分：{item.get('total_score') or item.get('score') or '—'}",
                     item.get("total_score") or item.get("score"), "system_sync",
                     item.get("created_at") or item.get("time", "")))

    # 5. 学生自评画像
    for item in _as_list(_read_json(os.path.join(DATA_DIR, "student_self_assessment.json"), [])):
        if str(item.get("student_no") or "") != str(student_no) and item.get("student_name") != student_name:
            continue
        jobs.append(("skill", "能力自评提交", f"自评分：{item.get('average') or item.get('score') or '已完成'}",
                     item.get("average") or item.get("score"), "system_sync",
                     item.get("created_at") or item.get("updated_at", "")))

    # 6. 能力测评（来自学生档案的胜任力分析）
    students = _read_json(os.path.join(DATA_DIR, "students.json"), [])
    for stu in _as_list(students):
        if str(stu.get("student_no") or "") != str(student_no) and stu.get("name") != student_name:
            continue
        ca = stu.get("competence_analysis")
        if isinstance(ca, dict) and ca:
            top = sorted(ca.items(), key=lambda x: -float(x[1] or 0))[:3]
            top_txt = "、".join(f"{k}({v})" for k, v in top)
            jobs.append(("skill", "胜任力测评（12 维能力分析）", f"优势维度：{top_txt}",
                         None, "system_sync", stu.get("created_at") or stu.get("last_login", "")))

    for rec_type, title, detail, value, source, created_at in jobs:
        ref = f"sync:{rec_type}:{title}:{created_at}:{detail[:40]}"
        ret = append_record(student_no, student_name, rec_type, title, detail,
                            value=value, source=source, source_ref=ref,
                            created_at=created_at, student_class=student_class)
        if ret.get("ok") and ret.get("skipped"):
            skipped += 1
        elif ret.get("ok"):
            added += 1
        sources[rec_type] = sources.get(rec_type, 0) + 1

    return {
        "ok": True,
        "added": added,
        "skipped": skipped,
        "candidate_total": len(jobs),
        "sources": sources,
        "message": f"同步完成：新增 {added} 条，已存在跳过 {skipped} 条",
    }


def stats_overview() -> dict:
    """全局概览（教师驾驶舱）"""
    data = _cc_load()
    chains = data.get("chains", {})
    total_records = sum(len(c.get("records", [])) for c in chains.values())
    total_certs = sum(len(c.get("certificates", [])) for c in chains.values())
    by_type = {}
    for c in chains.values():
        for r in c.get("records", []):
            by_type[r.get("type", "")] = by_type.get(r.get("type", ""), 0) + 1
    return {
        "student_count": len(chains),
        "record_count": total_records,
        "certificate_count": total_certs,
        "type_stats": [{"type": k, "label": RECORD_TYPES.get(k, k), "count": v}
                       for k, v in sorted(by_type.items(), key=lambda x: -x[1])],
        "updated_at": data.get("updated_at", ""),
    }
