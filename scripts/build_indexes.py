from __future__ import annotations

from collections import Counter, defaultdict

from kb_utils import (
    AUTO_NOTICE,
    INDEXES,
    by_id,
    count_subjects,
    find_cycles,
    load_topics,
    page_link,
    reverse_deps,
    sort_key,
    write_if_changed,
)


def bullet(topic, reason=None):
    meta = topic["meta"]
    if reason:
        return f"- {meta['id']}｜{meta['topic']}｜{reason}｜{page_link(topic)}"
    return f"- {meta['id']}｜{meta['topic']}｜{meta['status']}｜{meta['scope_status']}｜{page_link(topic)}"


def build_total(topics):
    subject_counts = count_subjects(topics)
    status_counts = Counter(t["meta"]["status"] for t in topics)
    current = sum(1 for t in topics if t["meta"]["scope_status"] == "current")
    historical = len(topics) - current
    lines = [
        AUTO_NOTICE,
        "",
        "# 408知识点总索引",
        "",
        "## 汇总",
        "",
        f"- 四科知识点数量：数据结构与算法 {subject_counts['数据结构与算法']}；计算机组成原理 {subject_counts['计算机组成原理']}；操作系统 {subject_counts['操作系统']}；计算机网络 {subject_counts['计算机网络']}",
        f"- 各学习状态数量：skeleton {status_counts.get('skeleton', 0)}；learned {status_counts.get('learned', 0)}；practiced {status_counts.get('practiced', 0)}；verified {status_counts.get('verified', 0)}",
        f"- 当前大纲内知识点数量：{current}",
        f"- 已废弃或已超纲知识点数量：{historical}",
        "",
    ]
    grouped = defaultdict(lambda: defaultdict(list))
    for topic in sorted(topics, key=sort_key):
        grouped[topic["meta"]["subject"]][topic["meta"]["chapter"]].append(topic)
    for subject, chapters in grouped.items():
        lines += [f"## {subject}", ""]
        for chapter, items in chapters.items():
            lines += [f"### {chapter}", ""]
            lines += [bullet(t) for t in items]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_dependencies(topics):
    index = by_id(topics)
    graph = {t["meta"]["id"]: t["meta"].get("prerequisites", []) for t in topics}
    reverse = reverse_deps(topics)
    invalid = []
    self_deps = []
    empty = []
    for topic in sorted(topics, key=sort_key):
        kid = topic["meta"]["id"]
        deps = topic["meta"].get("prerequisites", [])
        if not deps:
            empty.append(topic)
        for dep in deps:
            if dep not in index:
                invalid.append((topic, dep))
            if dep == kid:
                self_deps.append(topic)
    cycles = find_cycles(graph)
    lines = [AUTO_NOTICE, "", "# 前置依赖索引", "", "## 按当前知识点查看其前置知识", ""]
    for topic in sorted(topics, key=sort_key):
        meta = topic["meta"]
        deps = meta.get("prerequisites", [])
        if deps:
            names = []
            for dep in deps:
                names.append(f"{dep}（{index[dep]['meta']['topic'] if dep in index else '不存在'}）")
            lines.append(f"- {meta['id']}｜{meta['topic']}｜依赖：{'; '.join(names)}｜{page_link(topic)}")
    lines += ["", "## 按前置知识查看后续知识点", ""]
    for dep, users in sorted(reverse.items()):
        dep_name = index[dep]["meta"]["topic"] if dep in index else "不存在"
        lines.append(f"- {dep}｜{dep_name}｜被依赖：{'; '.join(users)}")
    lines += ["", "## 引用了不存在知识点ID的依赖关系", ""]
    lines += [f"- {t['meta']['id']}｜{t['meta']['topic']}｜无效依赖：{dep}｜{page_link(t)}" for t, dep in invalid] or ["- 无"]
    lines += ["", "## 知识点依赖自身", ""]
    lines += [bullet(t, "依赖自身") for t in self_deps] or ["- 无"]
    lines += ["", "## 直接或间接的循环依赖", ""]
    lines += [f"- {' -> '.join(cycle)}" for cycle in cycles] or ["- 无"]
    lines += ["", "## 当前没有填写任何前置依赖的知识点", ""]
    lines += [bullet(t, "未填写前置依赖") for t in empty] or ["- 无"]
    return "\n".join(lines).rstrip() + "\n", len(invalid) + len(self_deps) + len(cycles)


def build_unfinished(topics):
    index = by_id(topics)
    groups = [
        ("仅有骨架的知识点", lambda t: t["meta"]["status"] == "skeleton", "status为skeleton"),
        ("已学习但尚未做题验证的知识点", lambda t: t["meta"]["status"] == "learned", "status为learned"),
        ("已练习但尚未可靠验证的知识点", lambda t: t["meta"]["status"] == "practiced", "status为practiced"),
        ("缺少来源的知识点", lambda t: not t["meta"].get("sources"), "sources为空"),
        ("缺少前置依赖信息的知识点", lambda t: not t["meta"].get("prerequisites"), "prerequisites为空"),
        ("待人工确认的大纲变化", lambda t: "待人工确认" in t["body"], "正文含待人工确认"),
        ("已退出当前大纲但仍保留的知识点", lambda t: t["meta"]["scope_status"] in {"deprecated", "out_of_scope"}, "scope_status非current"),
    ]
    lines = [AUTO_NOTICE, "", "# 未完成项索引", ""]
    total = 0
    for title, pred, reason in groups:
        lines += [f"## {title}", ""]
        items = [t for t in sorted(topics, key=sort_key) if pred(t)]
        total += len(items)
        lines += [bullet(t, reason) for t in items] or ["- 无"]
        lines.append("")
    invalid = []
    for topic in sorted(topics, key=sort_key):
        for field in ["prerequisites", "related_topics"]:
            bad = [x for x in topic["meta"].get(field, []) if x not in index]
            for ref in bad:
                invalid.append((topic, field, ref))
    lines += ["## 存在无效引用的知识点", ""]
    lines += [f"- {t['meta']['id']}｜{t['meta']['topic']}｜{field}含不存在ID：{ref}｜{page_link(t)}" for t, field, ref in invalid] or ["- 无"]
    return "\n".join(lines).rstrip() + "\n", total + len(invalid)


def main():
    topics, _ = load_topics(strict=True)
    total = build_total(topics)
    deps, dep_issues = build_dependencies(topics)
    unfinished, unfinished_count = build_unfinished(topics)
    write_if_changed(INDEXES / "知识点总索引.md", total)
    write_if_changed(INDEXES / "前置依赖索引.md", deps)
    write_if_changed(INDEXES / "未完成项索引.md", unfinished)
    print(f"知识点总索引: {len(topics)} 个知识点")
    print(f"前置依赖索引: {len(topics)} 个知识点，发现问题 {dep_issues} 个")
    print(f"未完成项索引: {unfinished_count} 个条目")


if __name__ == "__main__":
    main()
