from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from pathlib import Path

from kb_utils import ROOT


def lines(path: Path):
    return [re.sub(r"\s+", " ", x.strip()) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def stable_new_id(subject_hint: str, new_version: str, text: str):
    prefix = {"数据结构": "DS", "数据结构与算法": "DS", "计算机组成原理": "CO", "操作系统": "OS", "计算机网络": "CN"}.get(subject_hint, "KB")
    digest = hashlib.sha1(f"{new_version}|{subject_hint}|{text}".encode("utf-8")).digest()
    token = base64.b32encode(digest).decode("ascii").rstrip("=")[:8]
    return f"{prefix}-KP-{token}"


def subject_for(line: str, current: str):
    m = re.match(r"^(数据结构|计算机组成原理|操作系统|计算机网络)\s+", line)
    if not m:
        return current
    return "数据结构与算法" if m.group(1) == "数据结构" else m.group(1)


def main():
    parser = argparse.ArgumentParser(description="比较两版大纲并输出增量更新候选变化报告。")
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--apply-confirmed", action="store_true", help="预留开关：仅在人工确认变更后使用。当前实现只生成报告。")
    args = parser.parse_args()

    old_path = Path(args.old)
    new_path = Path(args.new)
    if not old_path.is_absolute():
        old_path = ROOT / old_path
    if not new_path.is_absolute():
        new_path = ROOT / new_path
    old_lines = lines(old_path)
    new_lines = lines(new_path)
    old_set = set(old_lines)
    new_set = set(new_lines)
    added = [x for x in new_lines if x not in old_set]
    removed = [x for x in old_lines if x not in new_set]

    report = ROOT / "大纲版本" / args.new_version / "change_candidates.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    subject = ""
    out = [
        f"# {args.new_version} 大纲增量更新候选变化",
        "",
        "此报告只列出候选变化。新增、删除、改名、移动、拆分和合并均需人工确认后再修改知识库。",
        "",
        "## 新增候选",
        "",
    ]
    for item in added:
        subject = subject_for(item, subject)
        out.append(f"- 待人工确认｜建议新ID：{stable_new_id(subject, args.new_version, item)}｜{item}")
    out += ["", "## 删除候选", ""]
    for item in removed:
        out.append(f"- 待人工确认｜可能标记为deprecated或out_of_scope｜{item}")
    out += [
        "",
        "## 改名、移动、拆分、合并候选",
        "",
        "- 待人工确认：请比较新增候选与删除候选；仅因改名或移动章节，不应创建新ID。",
        "",
        "## 后续命令",
        "",
        "人工确认并修改知识点页面后运行：",
        "",
        "```bash",
        "python agent/scripts/build_indexes.py",
        "python agent/scripts/check_structure.py",
        "```",
    ]
    report.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"已生成候选变化报告: {report.relative_to(ROOT)}")
    print(f"新增候选: {len(added)}")
    print(f"删除候选: {len(removed)}")
    if args.apply_confirmed:
        print("当前脚本不会自动套用未确认变更；请先在报告中完成人工确认。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
