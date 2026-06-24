from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "大纲" / "2026考研考试大纲408计算机_AI易读版文本.txt"
VERSION = "2026考研考试大纲408计算机"
VERSION_ID = "2026"

SUBJECT_CODES = {
    "数据结构与算法": "DS",
    "计算机组成原理": "CO",
    "操作系统": "OS",
    "计算机网络": "CN",
}
SUBJECT_DISPLAY_NAMES = {
    "数据结构": "数据结构与算法",
    "计算机组成原理": "计算机组成原理",
    "操作系统": "操作系统",
    "计算机网络": "计算机网络",
}

AUTO_NOTICE = "此文件由脚本自动生成，请勿手工编辑。需要修改时，请修改源知识点页面的YAML元数据，然后重新运行索引生成脚本。"


def clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\s+", " ", line)
    line = line.replace("【", "(").replace("】", ")")
    return line


def parse_item(line: str):
    patterns = [
        (1, r"^[一二三四五六七八九十]+、\s*(.+)$"),
        (2, r"^[（(]\s*[一二三四五六七八九十]+\s*[）)]\s*(.+)$"),
        (3, r"^\d+\s*[\.\·]\s*(.+)$"),
    ]
    for level, pat in patterns:
        m = re.match(pat, line)
        if m:
            return level, clean_line(m.group(1))
    return None, None


def extract_subject_blocks(text: str):
    hits = list(re.finditer(r"^(数据结构|计算机组成原理|操作系统|计算机网络)\s+26\s+考研大纲\s*$", text, re.M))
    blocks = {}
    for i, hit in enumerate(hits):
        start = hit.start()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        blocks[SUBJECT_DISPLAY_NAMES[hit.group(1)]] = text[start:end].strip()
    return blocks


def parse_topics(text: str):
    topics = []
    for subject, block in extract_subject_blocks(text).items():
        stack = []
        in_goals = False
        for raw in block.splitlines()[1:]:
            line = clean_line(raw)
            if not line or line.isdigit() or line.startswith("====="):
                continue
            if line in {"【考查目标】", "(考查目标)"}:
                in_goals = True
                continue
            level, title = parse_item(line)
            if in_goals and re.match(r"^[一二三四五六七八九十]+、", line):
                in_goals = False
            if in_goals and level == 1:
                continue
            if in_goals and level is None:
                continue
            if in_goals and level and level > 1:
                continue
            if not in_goals:
                level, title = parse_item(line)
            if level:
                node = {"subject": subject, "level": level, "title": title, "text": [line], "children": []}
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                if stack:
                    stack[-1]["children"].append(node)
                stack.append(node)
                topics.append(node)
            elif stack:
                stack[-1]["text"].append(line)

    leaves = []
    for node in topics:
        if node["level"] >= 2 and not node["children"]:
            chapter = None
            for prev in reversed(topics[: topics.index(node) + 1]):
                if prev["subject"] == node["subject"] and prev["level"] == 1:
                    chapter = prev["title"]
                    break
            leaves.append(
                {
                    "subject": node["subject"],
                    "chapter": chapter or "未分章",
                    "topic": node["title"],
                    "syllabus_text": "\n".join(node["text"]),
                }
            )
    return leaves


def stable_id(subject: str, chapter: str, topic: str) -> str:
    digest = hashlib.sha1(f"{VERSION_ID}|{subject}|{chapter}|{topic}".encode("utf-8")).digest()
    token = base64.b32encode(digest).decode("ascii").rstrip("=")[:8]
    return f"{SUBJECT_CODES[subject]}-KP-{token}"


def safe_name(name: str, limit: int = 64) -> str:
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "-", name).strip(" .")
    return name[:limit] or "未命名"


def yaml_value(value):
    if value is None:
        return '""'
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def frontmatter(meta: dict) -> str:
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f"{key}: {yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def topic_body(item: dict, kid: str) -> str:
    meta = {
        "id": kid,
        "subject": item["subject"],
        "chapter": item["chapter"],
        "topic": item["topic"],
        "status": "skeleton",
        "scope_status": "current",
        "syllabus_version_added": VERSION_ID,
        "syllabus_version_removed": "",
        "sources": [f"syllabus:{VERSION_ID}"],
        "prerequisites": [],
        "related_topics": [],
    }
    return (
        frontmatter(meta)
        + f"\n\n# {item['topic']}\n\n"
        + "## 大纲定位\n\n"
        + f"- 大纲版本：{VERSION}\n"
        + f"- 大纲原文：\n\n```text\n{item['syllabus_text']}\n```\n\n"
        + "## 学习目标\n\n- 待补充：用可自测的标准描述掌握要求。\n\n"
        + "## 核心知识\n\n待补充。\n\n"
        + "## 基本解题方法\n\n待补充。\n\n"
        + "## 易错点\n\n待补充。\n\n"
        + "## 相关题目\n\n- 待关联题目ID。\n\n"
        + "## 自测\n\n待补充。\n\n"
        + "## 来源\n\n- 2026考研考试大纲408计算机。\n\n"
        + "## 修订记录\n\n- 2026-06-24：创建知识点骨架，来源为当前大纲。\n"
    )


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def templates():
    kp = """---
id: ""
subject: ""
chapter: ""
topic: ""
status: skeleton
scope_status: current
syllabus_version_added: ""
syllabus_version_removed: ""
sources: []
prerequisites: []
related_topics: []
---

# 知识点标题

## 大纲定位

- 大纲版本：
- 大纲原文：

引用规则：页面之间引用知识点时必须优先使用稳定ID；文件名和路径只作为阅读入口，不作为身份标识。

## 学习目标

使用可自测、可判断是否掌握的目标。

## 核心知识

待补充。

## 基本解题方法

待补充。

## 易错点

待补充。

## 相关题目

使用题目ID建立引用。

## 自测

待补充。

## 来源

记录教材、真题或其他可靠来源。不得无来源生成具体事实。

## 修订记录

记录重要内容修改及其原因。
"""
    q = """---
id: ""
type: ""
year: ""
subject: ""
knowledge_points: []
difficulty: ""
source: ""
status: unattempted
---

# 题目标题

## 题干

## 选项或问题

## 我的作答

## 正确答案

## 解题过程

## 考查知识点

knowledge_points 必须保存知识点ID列表；正文可链接到对应知识点页面。

## 错误选项分析

## 对知识库的修改

记录该题是否暴露出知识点页面的缺失、错误、表述不清或解题方法不足。
"""
    e = """---
question_id: ""
knowledge_points: []
error_type: concept_missing
review_status: unreviewed
first_error_date: ""
last_review_date: ""
---

# 错题标题

## 当时为什么错

## 缺失的知识或判断步骤

## 正确触发信号

## 下次解题动作

## 应更新的知识点页面

通过知识点ID链接回对应知识点页面，不重复抄写完整知识内容。

## 复习记录
"""
    write(ROOT / "templates" / "知识点模板.md", kp)
    write(ROOT / "templates" / "题目模板.md", q)
    write(ROOT / "templates" / "错题模板.md", e)


def docs_and_scripts():
    readme = f"""# 408计算机学科专业基础综合知识库

当前大纲版本：{VERSION}

本知识库当前只建立结构、骨架、模板、索引和检查机制，不编写完整讲义，不生成模拟题。

## 目录

- `knowledge/`：正式知识点页面。
- `templates/`：知识点、题目、错题模板。模板不是正式内容。
- `syllabus_versions/`：每一版大纲原文或规范化副本。
- `indexes/`：脚本自动生成的索引。
- `scripts/`：索引、检查和未来大纲更新辅助脚本。
- `data/id_registry.json`：已经分配过的知识点ID登记表。

## 什么时候运行索引生成脚本

修改任一知识点页面的YAML元数据、移动知识点页面、新增或废弃知识点后，运行：

```bash
python scripts/build_indexes.py
```

脚本读取 `knowledge/` 中的正式知识点页面，覆盖生成：

- `indexes/知识点总索引.md`
- `indexes/前置依赖索引.md`
- `indexes/未完成项索引.md`

如果脚本报错，优先查看错误里给出的文件路径、知识点ID和字段名，再修改对应知识点页面的YAML元数据。

## 结构检查

每次修改知识点、题目、错题或大纲版本后，运行：

```bash
python scripts/check_structure.py
```

该脚本检查大纲覆盖、ID唯一性、历史ID复用、字段合法性、引用有效性、模板误识别以及索引是否与源文件一致。

## 未来更新大纲

先把新版大纲文本保存到 `syllabus_versions/<新版本>/raw.md`，然后运行：

```bash
python scripts/update_syllabus.py syllabus_versions/{VERSION_ID}/raw.md syllabus_versions/<新版本>/raw.md --new-version <新版本>
```

该命令会先输出候选变化报告；无法确定的新增、删除、改名、移动、拆分和合并需要人工确认后再修改知识库。
"""
    agents = """# AGENTS.md

- 大纲决定知识库范围。
- 教材和真题决定准确性与深度。
- 禁止无来源地生成具体事实。
- 当前阶段不写长篇内容，不生成模拟题。
- 不得随意更改、复用或回收知识点ID。
- 大纲更新必须采用增量更新，不得覆盖或重新生成整个知识库。
- 新增、修改、删除大纲条目前，应先输出变更报告，再修改知识库。
- 模板规定页面结构，但模板文件不得被视为正式知识点、题目或错题。
- 索引是自动生成文件，不得手工维护。
- 修改知识点元数据后必须重新运行索引生成和结构检查脚本。
- 旧大纲中存在、当前大纲中不再出现的知识点不直接删除，应标记为 `deprecated` 或 `out_of_scope`，并保留原ID和已有引用。
"""
    changelog = f"""# CHANGELOG

## 2026-06-24

- 初始化 {VERSION} 知识库结构。
- 按当前大纲生成知识点骨架页面。
- 创建模板、索引生成脚本、结构检查脚本和增量更新辅助脚本。
- 当前阶段未编写完整讲义，未生成模拟题。
"""
    write(ROOT / "README.md", readme)
    write(ROOT / "AGENTS.md", agents)
    write(ROOT / "CHANGELOG.md", changelog)


def main():
    text = SOURCE.read_text(encoding="utf-8")
    topics = parse_topics(text)
    if not topics:
        raise SystemExit("未能从大纲文本解析出知识点。")

    for old in ["knowledge", "templates", "indexes", "syllabus_versions", "data"]:
        p = ROOT / old
        if p.exists():
            shutil.rmtree(p)

    write(ROOT / "syllabus_versions" / VERSION_ID / "raw.md", text)
    write(
        ROOT / "syllabus_versions" / "versions.json",
        json.dumps(
            [
                {
                    "version": VERSION_ID,
                    "title": VERSION,
                    "date_recorded": str(date.today()),
                    "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
                    "normalized_copy": f"syllabus_versions/{VERSION_ID}/raw.md",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )

    registry = {"version": 1, "assigned_ids": {}}
    for order, item in enumerate(topics, start=1):
        kid = stable_id(item["subject"], item["chapter"], item["topic"])
        item["id"] = kid
        path = (
            ROOT
            / "knowledge"
            / item["subject"]
            / safe_name(item["chapter"])
            / f"{safe_name(item['topic'])}__{kid}.md"
        )
        write(path, topic_body(item, kid))
        registry["assigned_ids"][kid] = {
            "status": "active",
            "first_assigned_version": VERSION_ID,
            "original_subject": item["subject"],
            "original_chapter": item["chapter"],
            "original_topic": item["topic"],
            "original_order": order,
            "current_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        }
    write(ROOT / "data" / "id_registry.json", json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    templates()
    docs_and_scripts()
    print(f"created_topics={len(topics)}")
    for subject in SUBJECT_CODES:
        print(f"{subject}={sum(1 for t in topics if t['subject'] == subject)}")


if __name__ == "__main__":
    main()
