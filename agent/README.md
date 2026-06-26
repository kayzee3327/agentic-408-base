# 维护资产索引

本目录收纳 AI agent 维护 408 知识库所需的流程、模板、脚本和状态文件。根目录 `AGENTS.md` 仍是 AI agent 的入口规则文件。

## 目录

- `workflows/`：可重复执行的资料库维护流程。
- `templates/knowledge/`：正式知识点页面模板。
- `templates/intake/`：题目、错题、反馈事件和练习记录模板。
- `templates/maintenance/`：维护流程模板。
- `scripts/`：索引生成、结构检查和大纲更新辅助脚本。
- `state/id_registry.json`：已分配知识点ID登记表。

## 常用检查

```bash
python agent/scripts/check_structure.py
```
