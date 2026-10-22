# -*- coding: utf-8 -*-
"""
知识库 RAG 向量检索（Retrieval-Augmented Generation）

升级目标：把「整库塞进提示词」改为「按需召回最相关片段」。
- 切片：知识库长文本按标题/段落切成语义 chunk，控制长度并保留少量重叠
- 向量化：调用 SiliconFlow embedding（BAAI/bge-m3，1024 维），向量缓存到本地索引文件
- 召回：问题向量与切片向量做余弦相似度排序，取 Top-K
- 混合：向量相似度 + 关键词命中加权（避免 OFDM、5G NR 等专有名词被语义漂移漏掉）
- 降级：索引缺失或接口不可用时退回关键词召回，绝不阻断问答主链路

对外主要接口：
    build_index(force=True)     重建索引
    ensure_index()              索引缺失/过期时自动重建（返回状态）
    search(query, top_k)        召回片段（含来源与分数明细）
    format_context(chunks)      把召回片段拼成提示词上下文
    index_status()              索引状态（供管理页/接口展示）
"""

import hashlib
import json
import math
import os
import re
import sys
import threading
from datetime import datetime

import requests

# ============================ 配置 ============================
DATA_DIR = "data"
INDEX_FILE = os.path.join(DATA_DIR, "rag_index.json")
KNOWLEDGE_FILE = "knowledge.txt"

EMBED_API_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
EMBED_DIM = 1024

CHUNK_SIZE = 480          # 单个切片目标字符数
CHUNK_MIN = 80            # 小于该长度的切片会被并入上一片
CHUNK_OVERLAP = 60        # 相邻切片重叠字符数，避免语义在切口处断裂
MAX_CHUNKS = 800          # 单次建索引的切片上限，防止异常长文本拖垮接口
EMBED_BATCH = 8           # 单次 embedding 请求的文本条数

TOP_K = 5                 # 默认召回条数
VECTOR_WEIGHT = 0.7       # 向量相似度权重
KEYWORD_WEIGHT = 0.3      # 关键词命中权重
MIN_SCORE = 0.15          # 低于该分数的切片不进入提示词

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_RE = re.compile(r"[a-z0-9]+")
_HEADING_RE = re.compile(r"^\s*(#{1,6}\s*)?([【\[][^】\]]{1,40}[】\]]|.{1,30}[：:]\s*$)\s*$")
_SEPARATOR_RE = re.compile(r"^\s*[=\-—*]{8,}\s*$")

# 中文高频噪声词（bigram 级别），参与打分但几乎无区分度
_STOP_TOKENS = {
    "的是", "我们", "可以", "这个", "那个", "如果", "因为", "所以", "以及", "进行",
    "通过", "对于", "需要", "一个", "具有", "并且", "或者", "其中", "这些", "为了",
}


# ============================ 基础工具 ============================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir():
    if DATA_DIR and not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _load_api_key() -> str:
    """与 app.py 保持一致：环境变量 > api_key.local > 演示默认值"""
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if key:
        return key
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, "api_key.local"), "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    return "sk-sdfaoxkrbsmmnueekypiqjgxtcrscmrmajrzvtdjkgnjieyi"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_knowledge_text() -> str:
    """读取知识库全文（与业务代码同一约定：相对工作目录）"""
    try:
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                return f.read()
    except OSError as e:
        print(f"[RAG] 知识库读取失败: {e}")
    return ""


# ============================ 切片 ============================

def _tokenize(text: str) -> set:
    """轻量分词：拉丁词/数字 + 中文 bigram，用于关键词命中打分"""
    text = text.lower()
    tokens = set(_LATIN_RE.findall(text))
    for seg in _CJK_RE.findall(text):
        if len(seg) == 1:
            tokens.add(seg)
        else:
            for i in range(len(seg) - 1):
                tokens.add(seg[i:i + 2])
    tokens -= _STOP_TOKENS
    return tokens


def _split_blocks(text: str) -> list:
    """把全文拆成「标题 + 正文段落」序列，分隔线/纯符号行被丢弃"""
    blocks = []
    current_title = ""
    for raw in re.split(r"\n\s*\n", text):
        block = raw.strip()
        if not block:
            continue
        # 单个块里可能混着分隔线与小标题，先做行级清洗
        lines = []
        for line in block.split("\n"):
            line = line.strip()
            if not line or _SEPARATOR_RE.match(line):
                continue
            if len(line) <= 40 and _HEADING_RE.match(line):
                current_title = re.sub(r"^#{1,6}\s*", "", line).strip("【】[]:：")
                continue
            lines.append(line)
        body = "\n".join(lines).strip()
        if not body:
            continue
        blocks.append({"title": current_title, "text": body})
    return blocks


def chunk_text(text: str) -> list:
    """把知识库切成带来源标注的语义切片"""
    chunks = []
    buffer = ""
    buffer_title = ""

    def flush():
        nonlocal buffer, buffer_title
        if buffer.strip():
            chunks.append({
                "title": buffer_title or "知识库",
                "text": buffer.strip(),
            })
        buffer = ""
        buffer_title = ""

    for block in _split_blocks(text):
        piece = block["text"]
        if not buffer:
            buffer_title = block["title"]
        # 超长段落先按句号切分，避免单片过大
        if len(piece) > CHUNK_SIZE:
            parts = [p for p in re.split(r"(?<=[。！？；\n])", piece) if p.strip()]
        else:
            parts = [piece]
        for part in parts:
            if buffer and len(buffer) + len(part) > CHUNK_SIZE:
                tail = buffer[-CHUNK_OVERLAP:] if CHUNK_OVERLAP > 0 else ""
                flush()
                buffer = tail
                buffer_title = block["title"]
            buffer += part
            if not buffer_title:
                buffer_title = block["title"]
    flush()

    # 过短的切片并入前一片，减少语义碎片
    merged = []
    for c in chunks:
        if merged and len(c["text"]) < CHUNK_MIN:
            merged[-1]["text"] += "\n" + c["text"]
        else:
            merged.append(c)

    # 去重：文档抽取常把同一段落重复写入知识库，重复切片会挤占 Top-K 名额
    seen = set()
    unique = []
    for c in merged:
        norm = "".join(c["text"].split())
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(c)
    merged = unique

    if len(merged) > MAX_CHUNKS:
        print(f"[RAG] 切片数 {len(merged)} 超过上限 {MAX_CHUNKS}，已截断")
        merged = merged[:MAX_CHUNKS]

    for i, c in enumerate(merged):
        c["id"] = f"c{i:05d}"
        c["source"] = KNOWLEDGE_FILE
        c["chars"] = len(c["text"])
    return merged


# ============================ 向量化 ============================

def embed_texts(texts: list, batch: int = EMBED_BATCH, retries: int = 2, timeout=60) -> list:
    """批量向量化。失败抛 RuntimeError，由调用方决定降级策略"""
    if not texts:
        return []
    key = _load_api_key()
    vectors = []
    for start in range(0, len(texts), batch):
        piece = texts[start:start + batch]
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(
                    EMBED_API_URL,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": EMBED_MODEL, "input": piece},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    # 接口按 index 返回，需按序还原
                    data = sorted(data, key=lambda d: d.get("index", 0))
                    vectors.extend([d["embedding"] for d in data])
                    last_err = None
                    break
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:  # noqa: BLE001 - 网络异常统一重试
                last_err = repr(e)
            if attempt < retries:
                import time as _t
                _t.sleep(1.5 * (attempt + 1))
        if last_err:
            raise RuntimeError(f"[RAG] embedding 失败（第 {start}-{start + len(piece)} 条）: {last_err}")
    if len(vectors) != len(texts):
        raise RuntimeError(f"[RAG] embedding 返回数量不匹配: 期望 {len(texts)}，实际 {len(vectors)}")
    return vectors


# ============================ 索引读写 ============================

_index_cache = None  # {"chunks": [...], "vectors": [...], "meta": {...}}
_cache_mtime = None
_lock = threading.Lock()


def _save_index(payload: dict):
    _ensure_dir()
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, INDEX_FILE)


def build_index(force: bool = False) -> dict:
    """重建索引（force=False 时若来源未变则跳过）"""
    global _index_cache, _cache_mtime
    text = read_knowledge_text()
    if not text.strip():
        return {"success": False, "error": "知识库为空，无法建索引"}

    source_hash = _sha256(text)
    if not force and os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                old = json.load(f)
            if old.get("source_hash") == source_hash:
                return {"success": True, "skipped": True, "chunks": len(old.get("chunks", [])),
                        "message": "知识库未变化，沿用现有索引"}
        except (OSError, ValueError):
            pass

    chunks = chunk_text(text)
    if not chunks:
        return {"success": False, "error": "切片结果为空"}
    print(f"[RAG] 开始建索引：{len(chunks)} 个切片，模型 {EMBED_MODEL}")
    vectors = embed_texts([c["text"] for c in chunks])

    payload = {
        "version": 1,
        "model": EMBED_MODEL,
        "dim": len(vectors[0]) if vectors else 0,
        "built_at": _now(),
        "source_hash": source_hash,
        "source_chars": len(text),
        "chunks": chunks,
        "vectors": vectors,
    }
    with _lock:
        _save_index(payload)
        _index_cache = {"chunks": chunks, "vectors": vectors, "meta": {k: v for k, v in payload.items()
                                                                       if k not in ("chunks", "vectors")}}
        _cache_mtime = os.path.getmtime(INDEX_FILE) if os.path.exists(INDEX_FILE) else None
    print(f"[RAG] 索引建立完成：{len(chunks)} 切片 / {payload['dim']} 维")
    return {"success": True, "skipped": False, "chunks": len(chunks), "dim": payload["dim"],
            "message": f"索引重建完成，共 {len(chunks)} 个切片"}


def load_index() -> dict:
    """读取索引，带内存缓存 + 文件 mtime 失效检测"""
    global _index_cache, _cache_mtime
    if not os.path.exists(INDEX_FILE):
        return {}
    try:
        mtime = os.path.getmtime(INDEX_FILE)
    except OSError:
        return {}
    if _index_cache is not None and _cache_mtime == mtime:
        return _index_cache
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[RAG] 索引读取失败: {e}")
        return {}
    if not isinstance(data, dict) or not data.get("chunks"):
        return {}
    with _lock:
        _index_cache = {"chunks": data["chunks"], "vectors": data.get("vectors", []),
                        "meta": {k: v for k, v in data.items() if k not in ("chunks", "vectors")}}
        _cache_mtime = mtime
    return _index_cache


def index_status() -> dict:
    """索引状态（供管理页与接口展示）"""
    idx = load_index()
    meta = idx.get("meta", {}) if idx else {}
    current_hash = _sha256(read_knowledge_text()) if os.path.exists(KNOWLEDGE_FILE) else ""
    size = os.path.getsize(INDEX_FILE) if os.path.exists(INDEX_FILE) else 0
    return {
        "available": bool(idx),
        "model": meta.get("model", EMBED_MODEL),
        "dim": meta.get("dim", 0),
        "chunks": len(idx.get("chunks", [])) if idx else 0,
        "built_at": meta.get("built_at", ""),
        "source_chars": meta.get("source_chars", 0),
        "stale": bool(idx) and meta.get("source_hash") != current_hash,
        "size_kb": round(size / 1024, 1),
        "top_k": TOP_K,
        "vector_weight": VECTOR_WEIGHT,
        "keyword_weight": KEYWORD_WEIGHT,
    }


def ensure_index(async_mode: bool = True) -> dict:
    """索引缺失/过期时自动重建；async_mode 时放后台线程，不阻塞启动"""
    if not os.path.exists(KNOWLEDGE_FILE):
        return {"success": False, "error": "知识库文件不存在"}

    def _job():
        try:
            build_index(force=False)
        except Exception as e:  # noqa: BLE001 - 后台任务不允许抛到主线程
            print(f"[RAG] 后台建索引失败: {e}")

    status = index_status()
    if status["available"] and not status["stale"]:
        return {"success": True, "skipped": True, "message": "索引已是最新", **status}
    if async_mode:
        threading.Thread(target=_job, name="rag-index-build", daemon=True).start()
        return {"success": True, "async": True, "message": "索引缺失或过期，已在后台重建"}
    try:
        result = build_index(force=False)
        result.update(index_status())
        return result
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)}


# ============================ 召回 ============================

def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _keyword_score(query_tokens: set, chunk_text: str) -> float:
    """关键词覆盖率：命中词 / 查询词（bigram 层面），惩罚越短越易命中的噪声"""
    if not query_tokens:
        return 0.0
    hit = len(query_tokens & _tokenize(chunk_text))
    return hit / len(query_tokens)


def search(query: str, top_k: int = TOP_K, min_score: float = MIN_SCORE) -> list:
    """混合召回：返回 [{'id','title','source','text','score','vector_score','keyword_score'}]"""
    query = (query or "").strip()
    if not query:
        return []
    idx = load_index()
    if not idx:
        return []

    chunks = idx["chunks"]
    vectors = idx.get("vectors") or []
    query_tokens = _tokenize(query)

    query_vec = None
    if vectors:
        try:
            # 查询向量化必须快失败：这是聊天主链路的前置步骤，
            # embedding 接口异常时宁可用关键词召回也不能拖死整个 /chat
            query_vec = embed_texts([query], retries=0, timeout=(2.5, 4))[0]
        except Exception as e:  # noqa: BLE001 - 向量接口不可用时退化为关键词召回
            print(f"[RAG] 查询向量化失败，退化为关键词召回: {e}")
            query_vec = None

    scored = []
    for i, chunk in enumerate(chunks):
        vec_score = 0.0
        if query_vec is not None and i < len(vectors):
            vec_score = _cosine(query_vec, vectors[i])
        kw_score = _keyword_score(query_tokens, chunk["text"])
        if query_vec is None:
            score = kw_score                      # 降级：纯关键词
        else:
            score = VECTOR_WEIGHT * vec_score + KEYWORD_WEIGHT * kw_score
        if score < min_score:
            continue
        scored.append({
            "id": chunk.get("id", ""),
            "title": chunk.get("title", ""),
            "source": chunk.get("source", KNOWLEDGE_FILE),
            "text": chunk["text"],
            "score": round(score, 4),
            "vector_score": round(vec_score, 4),
            "keyword_score": round(kw_score, 4),
            "degraded": query_vec is None,
        })

    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]


def format_context(chunks: list, max_chars: int = 3600) -> str:
    """把召回片段拼成提示词上下文，带来源标注便于回答引用出处"""
    if not chunks:
        return ""
    lines = ["【知识库检索结果】（按相关度排序，回答时请优先依据以下片段并标注来源）"]
    used = 0
    for i, c in enumerate(chunks, 1):
        block = f"[{i}] 来源：{c.get('source', '')} · {c.get('title', '')}（相关度 {c.get('score', 0)}）\n{c['text']}"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n\n".join(lines)


def keyword_baseline(query: str, top_k: int = TOP_K) -> list:
    """对照用：纯关键词字面匹配（不做向量），用于演示语义召回的提升"""
    query = (query or "").strip()
    idx = load_index()
    if not query or not idx:
        return []
    query_tokens = _tokenize(query)
    scored = []
    for chunk in idx["chunks"]:
        s = _keyword_score(query_tokens, chunk["text"])
        if s <= 0:
            continue
        scored.append({"id": chunk.get("id", ""), "title": chunk.get("title", ""),
                       "source": chunk.get("source", KNOWLEDGE_FILE), "text": chunk["text"],
                       "score": round(s, 4)})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]
