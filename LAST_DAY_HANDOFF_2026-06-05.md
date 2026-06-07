# Last Day Handoff - 2026-06-05

这是一份给未来继续接手 `E:\PROJECT FROM CODEX` 的轻量交接。它不替代 `CLAUDE.md`，只记录今天实测到的状态和最稳妥的下一步。

## Current Shape

- 主项目是仓库根目录的 Quant Assistant，部署根目录仍是 `E:\PROJECT FROM CODEX`。
- `main\quant-assistant` 看起来是同项目的另一个副本，不应默认当作部署根目录。
- `codex_comfy_video_pipeline` 是独立的 ComfyUI / ffmpeg 辅助流水线，有自己的 `pyproject.toml` 和测试。
- 工作树里有大量未跟踪文件，多数像是 IDM/Chrome 集成备份、图片实验和附加流水线产物。后续提交时必须精确 `git add`。

## Verification Snapshot

执行日期：2026-06-05

推荐使用系统 Python launcher：

```powershell
cd "E:\PROJECT FROM CODEX"
py -m pytest
```

也可以运行完整只读验证脚本：

```powershell
.\scripts\verify_quant_assistant.ps1
```

结果：

```text
218 passed
```

ComfyUI 流水线测试：

```powershell
cd "E:\PROJECT FROM CODEX\codex_comfy_video_pipeline"
python -m pytest
```

结果：

```text
1 passed
```

注意：当前 `python` 命令指向 Codex/Hermes 自带环境：

```text
C:\Users\18312\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
```

这个环境没有 `pip`，并且缺少 Quant Assistant 测试所需的 `pandas` / `streamlit` 等依赖。因此验证 Quant Assistant 时优先使用 `py -m pytest`，不要被 `python -m pytest` 的依赖导入错误误导成业务回归。

## Git Safety

当前分支：

```text
main...origin/main
```

今天观察到的未跟踪项包括但不限于：

- `codex_comfy_video_pipeline/`
- `idm-chrome-extension-backup-20260601-163836/`
- `scripts/configure_idm_browser_integration.ps1`
- 多个 `idm-*.reg`
- 多个 `pikachu_*.png`
- `main/`

除非用户明确要求，不要批量提交这些文件。提交 Quant Assistant 变更时，继续遵守 `CLAUDE.md` 里的选择性 `git add`。

## Best Next Tasks

1. 不要直接用 2026-05-15 截图覆盖 `portfolio.json`：当前根目录快照已是 `as_of: 2026-05-19 12:53`，比截图更晚。差异审计已记录在 `reports/portfolio_snapshot_audit_2026-06-05.md`。
2. 继续保持截图导入的双路径：上传图片可走 RapidOCR，粘贴手机/微信 OCR 文本是必须保留的兜底。今天已把导入页文案改得更清楚，上传后提供折叠式截图小预览，确认写入后也会保留成功提示并指向总览页变更记录；导入链路里的坏数值现在会按缺失值降级，不会直接打断预检或账户合计，也不会覆盖旧的好持仓数值。schema 校验会拦住配置/组合文件里的非有限数字，策略层、LLM 复盘入口和 multi-agent 风控汇总也会把坏数值降级成安全展示值。
3. 当前策略覆盖检查为 0，详见 `reports/strategy_coverage_audit_2026-06-05.md`。`沃尔核材`、`通宇通讯` 虽存储为 `imported`，但有效策略会走 `short_term`；补专属规则前先确认意图。
4. 代码健康审计已记录在 `reports/code_health_audit_2026-06-05.md`；其中清理了 `strategy.py` 里的重复 `_prepend_health_warning` 定义。
5. 变更范围审计已记录在 `reports/change_set_audit_2026-06-05.md`；提交时按里面的路径选择，不要 `git add .`。
6. 最终验证审计已记录在 `reports/final_verification_audit_2026-06-05.md`，包含测试、CLI、浏览器和 Git ignore 检查结果。
7. OCR 依赖变更必须以 Streamlit Cloud 可部署为前提。不要为了本地识别率牺牲冷启动和云端安装稳定性。
8. 如果要部署，先本地跑 `.\scripts\verify_quant_assistant.ps1`，再检查 `git status --short`，只提交相关文件。

## Personal Note

这个工作区最珍贵的部分不是某一次代码改动，而是它已经形成了一套能继续迭代的节奏：本地验证、谨慎提交、避免真实交易接口、把建议和风险说清楚。以后再回来，从这套节奏接上就好。
