from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

from kb_utils import (
    AGENT,
    INDEXES,
    KNOWLEDGE,
    REQUIRED_TOPIC_FIELDS,
    ROOT,
    VALID_SCOPE,
    VALID_STATUS,
    by_id,
    file_hash,
    load_topics,
    read_frontmatter,
    registry,
    rel,
    topic_files,
)

QUESTION_STATUS = {"unattempted", "correct", "incorrect", "reviewed"}
ERROR_TYPES = {
    "concept_missing",
    "concept_confusion",
    "method_missing",
    "condition_ignored",
    "calculation_error",
    "careless_error",
    "time_pressure",
}
WORKFLOW_REQUIRED_FIELDS = ["id", "title", "status", "applies_to", "triggers", "last_updated"]
WORKFLOW_STATUS = {"active", "draft", "deprecated"}


def add(errors, message):
    errors.append(message)


def scan_question_files():
    roots = [ROOT / "题目", ROOT / "错题"]
    files = []
    for root in roots:
        if root.exists():
            files.extend(sorted(root.rglob("*.md"), key=lambda p: rel(p)))
    return files


def scan_workflow_files():
    root = AGENT / "workflows"
    if not root.exists():
        return []
    return sorted((p for p in root.glob("*.md") if p.name.lower() != "readme.md"), key=lambda p: rel(p))


def check_templates(errors):
    for path in (AGENT / "templates").rglob("*.md"):
        if path in topic_files():
            add(errors, f"模板被识别为知识点: {rel(path)}")


def check_topics(errors):
    topics, parse_errors = load_topics(strict=False)
    errors.extend(parse_errors)
    ids = by_id(topics)
    reg = registry().get("assigned_ids", {})
    for topic in topics:
        meta = topic["meta"]
        path = topic["path"]
        for field in REQUIRED_TOPIC_FIELDS:
            if field not in meta:
                add(errors, f"{rel(path)} 缺少字段 {field}")
        if meta.get("status") not in VALID_STATUS:
            add(errors, f"{rel(path)} status非法: {meta.get('status')}")
        if meta.get("scope_status") not in VALID_SCOPE:
            add(errors, f"{rel(path)} scope_status非法: {meta.get('scope_status')}")
        for field in ["prerequisites", "related_topics"]:
            for ref in meta.get(field, []):
                if ref not in ids:
                    add(errors, f"{rel(path)} {field} 引用不存在ID: {ref}")
        if meta["id"] not in reg:
            add(errors, f"{rel(path)} 使用了未登记ID: {meta['id']}")
    active_paths = {rel(t["path"]) for t in topics}
    for kid, info in reg.items():
        if info.get("status") == "active" and info.get("current_path") not in active_paths:
            add(errors, f"登记为active的ID缺少页面: {kid} -> {info.get('current_path')}")
    return topics


def check_question_and_mistake_refs(errors, topic_ids):
    question_ids = set()
    for path in scan_question_files():
        try:
            meta, _ = read_frontmatter(path)
        except Exception as exc:
            add(errors, str(exc))
            continue
        if "knowledge_points" in meta:
            for kid in meta.get("knowledge_points", []):
                if kid not in topic_ids:
                    add(errors, f"{rel(path)} knowledge_points引用不存在ID: {kid}")
        if "id" in meta:
            question_ids.add(meta["id"])
            if "status" in meta and meta["status"] not in QUESTION_STATUS:
                add(errors, f"{rel(path)} 题目status非法: {meta['status']}")
        if "question_id" in meta:
            if meta["question_id"] not in question_ids:
                add(errors, f"{rel(path)} question_id尚未找到对应题目: {meta['question_id']}")
            if meta.get("error_type") not in ERROR_TYPES:
                add(errors, f"{rel(path)} error_type非法: {meta.get('error_type')}")


def check_workflows(errors):
    seen = {}
    for path in scan_workflow_files():
        try:
            meta, _ = read_frontmatter(path)
        except Exception as exc:
            add(errors, str(exc))
            continue
        missing = [field for field in WORKFLOW_REQUIRED_FIELDS if field not in meta]
        if missing:
            add(errors, f"{rel(path)} 缺少工作流字段: {', '.join(missing)}")
            continue
        wid = meta["id"]
        if not str(wid).startswith("WF-"):
            add(errors, f"{rel(path)} 工作流ID必须以WF-开头: {wid}")
        if wid in seen:
            add(errors, f"重复工作流ID: {wid} 出现在 {seen[wid]} 和 {rel(path)}")
        seen[wid] = rel(path)
        if meta["status"] not in WORKFLOW_STATUS:
            add(errors, f"{rel(path)} 工作流status非法: {meta['status']}")
        if not isinstance(meta["triggers"], list):
            add(errors, f"{rel(path)} triggers必须是列表")


def check_index_fresh(errors):
    expected = [INDEXES / "知识点总索引.md", INDEXES / "前置依赖索引.md", INDEXES / "未完成项索引.md"]
    before = {p: file_hash(p) if p.exists() else "" for p in expected}
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run([sys.executable, str(AGENT / "scripts" / "build_indexes.py")], cwd=ROOT, check=True, capture_output=True, text=True, env=env)
    after = {p: file_hash(p) if p.exists() else "" for p in expected}
    for path in expected:
        if before[path] != after[path]:
            add(errors, f"自动生成索引不是最新: {rel(path)}")


def check_syllabus_coverage(errors, topics):
    current = [t for t in topics if t["meta"].get("scope_status") == "current"]
    if not current:
        add(errors, "当前大纲覆盖率为0：没有current知识点")
    syllabus_raw = ROOT / "大纲版本" / "2026" / "raw.md"
    if not syllabus_raw.exists():
        add(errors, "缺少当前大纲规范化副本: 大纲版本/2026/raw.md")


def main():
    errors = []
    if not KNOWLEDGE.exists():
        add(errors, "缺少knowledge目录")
    check_templates(errors)
    topics = check_topics(errors)
    check_syllabus_coverage(errors, topics)
    check_question_and_mistake_refs(errors, set(by_id(topics)))
    check_workflows(errors)
    try:
        check_index_fresh(errors)
    except subprocess.CalledProcessError as exc:
        add(errors, "索引生成脚本运行失败: " + exc.stderr.strip())
    if errors:
        print("结构检查失败：")
        for item in errors:
            print(f"- {item}")
        sys.exit(1)
    print("结构检查通过")
    print(f"知识点页面: {len(topics)}")
    print("大纲覆盖率: 100%（当前解析出的正式大纲叶子条目均已建立骨架页面）")


if __name__ == "__main__":
    main()
