from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
TEMPLATES = ROOT / "templates"
INDEXES = ROOT / "indexes"
AUTO_NOTICE = "此文件由脚本自动生成，请勿手工编辑。需要修改时，请修改源知识点页面的YAML元数据，然后重新运行索引生成脚本。"

REQUIRED_TOPIC_FIELDS = [
    "id",
    "subject",
    "chapter",
    "topic",
    "status",
    "scope_status",
    "syllabus_version_added",
    "syllabus_version_removed",
    "sources",
    "prerequisites",
    "related_topics",
]
VALID_STATUS = {"skeleton", "learned", "practiced", "verified"}
VALID_SCOPE = {"current", "deprecated", "out_of_scope"}
SUBJECTS = ["数据结构与算法", "计算机组成原理", "操作系统", "计算机网络"]


class KBError(Exception):
    pass


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def parse_scalar(value: str):
    value = value.strip()
    if value == "":
        return ""
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except Exception as exc:
            raise KBError(f"无法解析列表值: {value}") from exc
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value[1:-1]
    if value in {"null", "~"}:
        return ""
    return value


def read_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise KBError(f"{rel(path)} 缺少YAML元数据起始标记")
    end = text.find("\n---", 4)
    if end == -1:
        raise KBError(f"{rel(path)} 缺少YAML元数据结束标记")
    raw = text[4:end].strip("\n")
    meta = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise KBError(f"{rel(path)} YAML行缺少冒号: {line}")
        key, value = line.split(":", 1)
        meta[key.strip()] = parse_scalar(value)
    body = text[end + 5 :].lstrip("\n")
    return meta, body


def topic_files():
    if not KNOWLEDGE.exists():
        return []
    return sorted(KNOWLEDGE.rglob("*.md"), key=lambda p: rel(p))


def load_topics(strict=True):
    topics = []
    errors = []
    seen = {}
    for path in topic_files():
        try:
            meta, body = read_frontmatter(path)
            missing = [field for field in REQUIRED_TOPIC_FIELDS if field not in meta]
            if missing:
                raise KBError(f"{rel(path)} 缺少必要字段: {', '.join(missing)}")
            if meta["status"] not in VALID_STATUS:
                raise KBError(f"{rel(path)} status非法: {meta['status']}")
            if meta["scope_status"] not in VALID_SCOPE:
                raise KBError(f"{rel(path)} scope_status非法: {meta['scope_status']}")
            for field in ["sources", "prerequisites", "related_topics"]:
                if not isinstance(meta[field], list):
                    raise KBError(f"{rel(path)} {field} 必须是ID或来源列表")
            kid = meta["id"]
            if not kid:
                raise KBError(f"{rel(path)} id不能为空")
            if kid in seen:
                raise KBError(f"重复ID: {kid} 出现在 {seen[kid]} 和 {rel(path)}")
            seen[kid] = rel(path)
            topics.append({"path": path, "meta": meta, "body": body})
        except Exception as exc:
            errors.append(str(exc))
    if strict and errors:
        raise KBError("\n".join(errors))
    return topics, errors


def by_id(topics):
    return {t["meta"]["id"]: t for t in topics}


def page_link(topic):
    return f"[页面](../{rel(topic['path'])})"


_REGISTRY_CACHE = None


def sort_key(topic):
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = registry().get("assigned_ids", {})
    meta = topic["meta"]
    order = _REGISTRY_CACHE.get(meta["id"], {}).get("original_order", 10**9)
    return (SUBJECTS.index(meta["subject"]) if meta["subject"] in SUBJECTS else 99, order, meta["chapter"], meta["topic"], meta["id"])


def find_cycles(graph):
    cycles = []
    temp = set()
    perm = set()
    stack = []

    def visit(node):
        if node in perm:
            return
        if node in temp:
            idx = stack.index(node)
            cycles.append(stack[idx:] + [node])
            return
        temp.add(node)
        stack.append(node)
        for nxt in graph.get(node, []):
            visit(nxt)
        stack.pop()
        temp.remove(node)
        perm.add(node)

    for node in graph:
        visit(node)
    unique = []
    seen = set()
    for cycle in cycles:
        marker = tuple(cycle)
        if marker not in seen:
            seen.add(marker)
            unique.append(cycle)
    return unique


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_if_changed(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old != text:
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def registry():
    path = ROOT / "data" / "id_registry.json"
    if not path.exists():
        return {"assigned_ids": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def count_subjects(topics):
    c = Counter(t["meta"]["subject"] for t in topics)
    return {subject: c.get(subject, 0) for subject in SUBJECTS}


def reverse_deps(topics):
    result = defaultdict(list)
    for topic in topics:
        for dep in topic["meta"].get("prerequisites", []):
            result[dep].append(topic["meta"]["id"])
    return result
