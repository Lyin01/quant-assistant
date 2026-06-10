# 阶段一：体验优化 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让截图导入流程顺滑、持仓变更可追溯、日常操作无摩擦。

**架构：** 新增两个核心模块（`history.py` 记录变更，`importer.py` 中的 `_infer_tag` 扩展为更智能的 tag 建议），围绕 `app.py` 的「导入持仓」页面重构 UX（模式切换、可编辑结果、批量上传、tag 确认），在「总览」页面增加变更历史面板和撤销能力。

**技术栈：** Python, Streamlit, pandas, pytest

---

## 文件结构

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/quant_assistant/history.py` | 创建 | 持仓变更历史记录：计算 delta、追加记录、读取历史、撤销到上一版本 |
| `src/quant_assistant/importer.py` | 修改 | 增强 `_infer_tag` 覆盖更多规则；保持其他 importer 功能不变 |
| `app.py` | 修改 | 导入页面重构（模式切换、可编辑结果、批量截图、tag 确认）；总览页面增加 history 面板和撤销按钮 |
| `tests/test_history.py` | 创建 | history.py 的单元测试 |
| `tests/test_importer.py` | 创建（或扩展） | tag 推断规则的单元测试 |

---

## 任务 1：增强 tag 推断规则

**文件：**
- 修改：`src/quant_assistant/importer.py` 中的 `_infer_tag` 函数
- 测试：`tests/test_importer.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_importer.py` 中新建：

```python
from quant_assistant.importer import _infer_tag


def test_infer_tag_wide_index():
    assert _infer_tag("易方达中证500") == "wide_index"
    assert _infer_tag("华夏沪深300ETF") == "wide_index"
    assert _infer_tag("中证A500指数") == "wide_index"


def test_infer_tag_overseas():
    assert _infer_tag("华宝纳斯达克精选") == "overseas"
    assert _infer_tag("博时标普500ETF联接") == "overseas"
    assert _infer_tag("大成纳斯达克100") == "overseas"
    assert _infer_tag("纳指大成") == "overseas"


def test_infer_tag_tactical_ai():
    assert _infer_tag("天弘中证人工智能") == "tactical_ai"


def test_infer_tag_healthcare():
    assert _infer_tag("广发中证创新药ETF") == "healthcare"
    assert _infer_tag("易方达创新药") == "healthcare"


def test_infer_tag_defensive():
    assert _infer_tag("易方达稳健收益") == "defensive"


def test_infer_tag_unknown_returns_imported():
    assert _infer_tag("沃尔核材") == "imported"
    assert _infer_tag("某个不认识的基金") == "imported"
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_importer.py -v
```

预期：6 个 FAIL，因为 `tests/test_importer.py` 不存在或 `_infer_tag` 缺少规则。

- [ ] **步骤 3：修改 `_infer_tag` 实现**

打开 `src/quant_assistant/importer.py`，替换 `_infer_tag` 函数：

```python
def _infer_tag(name: str) -> str:
    rules = [
        ("wide_index", ["中证500", "A500", "沪深300", "宽基"]),
        ("tactical_ai", ["人工智能", "AI"]),
        ("power_grid", ["电网"]),
        ("military", ["军工"]),
        ("semiconductor", ["半导体", "芯片"]),
        ("robot", ["机器人"]),
        ("overseas", ["纳指", "纳斯达克", "标普", "标普500"]),
        ("healthcare", ["创新药", "医药"]),
        ("defensive", ["稳健", "债", "货币"]),
    ]
    for tag, keywords in rules:
        if any(keyword in name for keyword in keywords):
            return tag
    return "imported"
```

注意：`("overseas", ["纳指", "纳斯达克", "标普", "标普500"])` 这一条，要确保"标普500"排在"中证500"之后检查，否则不会冲突因为名称中不会同时含这两个。实际上当前实现是按列表顺序匹配的，"中证500"会先匹配到 wide_index，这是正确的。

- [ ] **步骤 4：运行测试验证通过**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_importer.py -v
```

预期：全部 PASS。

- [ ] **步骤 5：Commit**

```bash
cd "E:\PROJECT FROM CODEX"
git add src/quant_assistant/importer.py tests/test_importer.py
git commit -m "$(cat <<'EOF'
feat: expand tag inference rules for new holdings

Add overseas, healthcare, defensive rules to _infer_tag.
EOF
)"
```

---

## 任务 2：历史记录模块

**文件：**
- 创建：`src/quant_assistant/history.py`
- 测试：`tests/test_history.py`

- [ ] **步骤 1：编写失败测试（compute_delta）**

在 `tests/test_history.py` 中：

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from quant_assistant.history import compute_delta, record_change, read_history, rollback


def test_compute_delta_adds_updates_and_ignores_unchanged():
    existing = [
        {"name": "半导体", "market_value": 200.0, "shares": 100},
        {"name": "机器人", "market_value": 300.0, "shares": 200},
    ]
    imported = [
        {"name": "半导体", "market_value": 250.0, "shares": 100},
        {"name": "沃尔核材", "market_value": 1000.0, "shares": 50},
    ]
    delta = compute_delta(existing, imported)
    assert delta["updated"] == ["半导体"]
    assert delta["added"] == ["沃尔核材"]
    assert delta["removed"] == ["机器人"]


def test_compute_delta_empty_lists_when_no_changes():
    existing = [{"name": "A", "market_value": 100.0}]
    imported = [{"name": "A", "market_value": 100.0}]
    delta = compute_delta(existing, imported)
    assert delta["updated"] == []
    assert delta["added"] == []
    assert delta["removed"] == []
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_history.py::test_compute_delta_adds_updates_and_ignores_unchanged -v
```

预期：FAIL - `ModuleNotFoundError: No module named 'quant_assistant.history'`

- [ ] **步骤 3：创建 `history.py` 并实现 compute_delta**

创建 `src/quant_assistant/history.py`：

```python
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


CHINA_TZ = timezone(timedelta(hours=8))
HISTORY_FILE = Path("portfolio_history.jsonl")


def compute_delta(
    existing_positions: list[dict[str, Any]],
    imported_positions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Compare existing and imported positions, return lists of added/updated/removed names."""
    existing_by_name = {p["name"]: p for p in existing_positions if p.get("name")}
    imported_by_name = {p["name"]: p for p in imported_positions if p.get("name")}

    added = []
    updated = []
    removed = []

    for name, imp in imported_by_name.items():
        if name not in existing_by_name:
            added.append(name)
        elif _position_changed(existing_by_name[name], imp):
            updated.append(name)

    for name in existing_by_name:
        if name not in imported_by_name:
            removed.append(name)

    return {"added": added, "updated": updated, "removed": removed}


def _position_changed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Check if any numeric or string field differs (excluding id)."""
    for key, new_value in new.items():
        if key == "id":
            continue
        old_value = old.get(key)
        if isinstance(new_value, (int, float)) and isinstance(old_value, (int, float)):
            if round(float(new_value), 6) != round(float(old_value), 6):
                return True
        elif new_value != old_value:
            return True
    return False
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_history.py::test_compute_delta_adds_updates_and_ignores_unchanged tests/test_history.py::test_compute_delta_empty_lists_when_no_changes -v
```

预期：PASS。

- [ ] **步骤 5：编写失败测试（record_change, read_history, rollback）**

在 `tests/test_history.py` 中追加：

```python
def test_record_and_read_history():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"

        record_change(
            history_file,
            change_type="ocr_import",
            account="stock",
            delta={"added": ["A"], "updated": [], "removed": []},
            summary={"total_assets": 1000.0},
            previous_snapshot={"positions": []},
        )

        history = read_history(history_file)
        assert len(history) == 1
        assert history[0]["type"] == "ocr_import"
        assert history[0]["account"] == "stock"
        assert history[0]["changes"]["added"] == ["A"]


def test_rollback_restores_previous_snapshot():
    with TemporaryDirectory() as tmpdir:
        history_file = Path(tmpdir) / "test_history.jsonl"
        snapshot = {"positions": [{"name": "半导体", "market_value": 200.0}]}

        record_change(
            history_file,
            change_type="ocr_import",
            account="stock",
            delta={"added": ["A"], "updated": [], "removed": []},
            summary={"total_assets": 1000.0},
            previous_snapshot=snapshot,
        )

        result = rollback(history_file)
        assert result == snapshot
```

- [ ] **步骤 6：运行测试验证失败**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_history.py -v
```

预期：2 个 FAIL - `record_change`, `read_history`, `rollback` 未定义。

- [ ] **步骤 7：实现 record_change, read_history, rollback**

在 `src/quant_assistant/history.py` 中追加：

```python

def record_change(
    history_file: Path,
    change_type: str,
    account: str,
    delta: dict[str, list[str]],
    summary: dict[str, Any] | None,
    previous_snapshot: dict[str, Any] | None = None,
) -> None:
    """Append a change record to the history file."""
    record = {
        "timestamp": datetime.now(CHINA_TZ).isoformat(),
        "type": change_type,
        "account": account,
        "changes": {
            "added": delta.get("added", []),
            "updated": delta.get("updated", []),
            "removed": delta.get("removed", []),
            "summary": summary or {},
        },
    }
    if previous_snapshot is not None:
        record["previous_snapshot"] = previous_snapshot

    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_history(history_file: Path, limit: int = 50) -> list[dict[str, Any]]:
    """Read the most recent N history records (newest first)."""
    if not history_file.exists():
        return []

    records: list[dict[str, Any]] = []
    with open(history_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return list(reversed(records[-limit:]))


def rollback(history_file: Path) -> dict[str, Any] | None:
    """Restore the portfolio snapshot from the most recent history record."""
    history = read_history(history_file, limit=1)
    if not history:
        return None
    return history[0].get("previous_snapshot")
```

- [ ] **步骤 8：运行测试验证通过**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest tests/test_history.py -v
```

预期：全部 PASS。

- [ ] **步骤 9：Commit**

```bash
cd "E:\PROJECT FROM CODEX"
git add src/quant_assistant/history.py tests/test_history.py
git commit -m "$(cat <<'EOF'
feat: add portfolio change history tracking

Add history.py with compute_delta, record_change, read_history, rollback.
EOF
)"
```

---

## 任务 3：app.py 导入页面重构（模式切换 + 可编辑结果 + 批量截图）

**文件：**
- 修改：`app.py` 中 `elif page == "导入持仓":` 区块的 OCR 导入部分

- [ ] **步骤 1：备份当前 app.py 并理解现有 OCR 导入代码**

现有 OCR 导入代码位于 `app.py:333-434`。核心流程：
1. 上传截图 → 预览（`st.image`）
2. `run_ocr(image_bytes)` 识别文字
3. 用户在表单中粘贴/编辑 OCR 文本
4. 点击"解析截图文本" → `parse_ocr_positions` → DataFrame
5. 显示结果 + 确认更新

我们将重构为：
1. 模式切换：截图识别 / 纯文本粘贴
2. 截图模式：上传（可多选）→ 逐张识别 → 合并结果 → `st.data_editor` 编辑
3. 文本模式：直接粘贴文本 → 解析 → `st.data_editor` 编辑
4. 两种模式最终都进入统一的确认流程

- [ ] **步骤 2：替换 OCR 导入区块**

在 `app.py` 中，找到 `st.subheader("从截图导入")` 开始的部分（约第 333 行），替换整个区块。

保留原有的 `run_ocr` 函数不变。

新的代码结构：

```python
    st.subheader("从截图导入")

    import_mode = st.segmented_control(
        "导入模式",
        options=["截图识别", "纯文本粘贴"],
        default="截图识别",
        key="import_mode",
    )

    ocr_prefill = ""

    if import_mode == "截图识别":
        image_files = st.file_uploader(
            "上传截图 JPG / PNG（可多选）",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="multi_screenshot",
        )
        if image_files:
            all_parsed: list[pd.DataFrame] = []
            image_col, text_col = st.columns([1, 2])
            for idx, image_file in enumerate(image_files):
                with image_col:
                    st.image(image_file, caption=f"截图 {idx + 1}", width=240)
                image_bytes = image_file.getvalue()
                with st.spinner(f"正在识别截图 {idx + 1}..."):
                    recognized = run_ocr(image_bytes)
                if recognized:
                    parsed = parse_ocr_positions(recognized)
                    if not parsed.empty:
                        all_parsed.append(parsed)
                else:
                    st.warning(f"截图 {idx + 1} 未识别到文字。")

            if all_parsed:
                merged_parsed = _merge_parsed_frames(all_parsed)
                with text_col:
                    st.success(f"共识别 {len(merged_parsed)} 条持仓，可编辑后确认。")
                    edited = st.data_editor(merged_parsed, use_container_width=True, hide_index=True, key="ocr_editor")
                    ocr_prefill = "\n".join(
                        f"{row['name']} | " + " | ".join(str(v) for v in row if pd.notna(v) and v != row['name'])
                        for _, row in edited.iterrows()
                    )
            else:
                st.info("未从截图中识别到有效持仓，请切换到纯文本粘贴模式手动输入。")

    if import_mode == "纯文本粘贴" or ocr_prefill:
        with st.form("ocr_import_form"):
            preset = st.selectbox("解析格式", ["股票截图", "基金截图", "通用"], index=0)
            ocr_text = st.text_area(
                "截图 OCR 文本（自动识别或手动粘贴）",
                value=ocr_prefill,
                height=180,
                placeholder=(
                    "股票：半导体 | 203.50 | 100 | 100 | 2.035 | 2.071 | -3.60 | -1.74%\n"
                    "基金：易方达中证500 | 5594.65 | -1.54% | -76.65 | -1.35%"
                ),
            )
            parse_submitted = st.form_submit_button("解析并预览", type="primary")

        if parse_submitted and ocr_text.strip():
            parsed = parse_ocr_positions(ocr_text)
            summary = parse_ocr_summary(f"{preset}\n{ocr_text}")
            st.session_state["ocr_import_parsed"] = parsed
            st.session_state["ocr_import_summary"] = summary
            st.session_state["ocr_import_positions"] = dataframe_to_positions(parsed)
```

注意：`_merge_parsed_frames` 需要在 `app.py` 中新增一个辅助函数。

- [ ] **步骤 3：添加 _merge_parsed_frames 辅助函数**

在 `app.py` 中，在 `_quote_frame` 函数之后添加：

```python

def _merge_parsed_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple parsed DataFrames, keeping the latest row for duplicate names."""
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    if combined.empty or "name" not in combined.columns:
        return combined
    # Keep the last occurrence of each name (latest screenshot wins)
    return combined.drop_duplicates(subset=["name"], keep="last").reset_index(drop=True)
```

- [ ] **步骤 4：运行 Streamlit 验证界面正常**

```bash
cd "E:\PROJECT FROM CODEX"
python -m streamlit run app.py
```

在浏览器中打开 http://localhost:8501，切换到「导入持仓」页面，验证：
- 模式切换按钮存在且可点击
- 截图模式可上传多张图片
- 纯文本粘贴模式可正常输入
- 解析结果以可编辑表格展示

- [ ] **步骤 5：Commit**

```bash
cd "E:\PROJECT FROM CODEX"
git add app.py
git commit -m "$(cat <<'EOF'
feat: restructure screenshot import with mode switch and editable results

Add segmented control for screenshot vs text-paste mode.
Support multi-image upload with merged deduplication.
Display parsed results in st.data_editor for user correction.
EOF
)"
```

---

## 任务 4：app.py 导入页面 — 新增持仓 tag 确认 + 变更预览增强

**文件：**
- 修改：`app.py` 中 OCR 导入的确认更新部分

- [ ] **步骤 1：修改确认更新区块，新增 tag 选择**

在 `app.py` 中，找到 OCR 导入结果确认部分（约第 394-434 行的区块）。替换为：

```python
        parsed = st.session_state.get("ocr_import_parsed")
        summary = st.session_state.get("ocr_import_summary")
        parsed_positions = st.session_state.get("ocr_import_positions", [])

        if parsed is not None:
            if summary:
                summary_frame = pd.DataFrame([summary]).dropna(axis=1, how="all")
                if not summary_frame.empty:
                    st.dataframe(summary_frame, use_container_width=True, hide_index=True)

            if parsed.empty:
                st.warning("未识别到持仓行。建议保留：名称、市值、持股、现价、成本、盈亏率。")
            else:
                st.success(f"已识别 {len(parsed)} 条持仓。")
                st.dataframe(parsed, use_container_width=True, hide_index=True)

                # Tag assignment for new positions
                detected_account = summary.get("account_type") if summary else None
                if not detected_account:
                    has_shares = any(p.get("shares") for p in parsed_positions)
                    detected_account = "stock" if has_shares else "fund"

                target_account = portfolio["accounts"][detected_account]
                existing_names = {p["name"] for p in target_account["positions"]}
                imported_names = {p["name"] for p in parsed_positions}
                new_names = imported_names - existing_names
                update_names = existing_names & imported_names

                # Tag selection for new holdings
                tag_choices = [
                    "wide_index", "tactical_ai", "power_grid", "military",
                    "semiconductor", "robot", "overseas", "healthcare",
                    "defensive", "core_ai_dca", "imported"
                ]
                if new_names:
                    st.subheader("为新持仓选择策略标签")
                    for pos in parsed_positions:
                        if pos["name"] in new_names:
                            suggested = _infer_tag(pos["name"])
                            idx = tag_choices.index(suggested) if suggested in tag_choices else tag_choices.index("imported")
                            pos["tag"] = st.selectbox(
                                f"`{pos['name']}` 的策略标签",
                                tag_choices,
                                index=idx,
                                key=f"tag_select_{pos['name']}",
                            )

                st.divider()
                st.subheader("变更预览")
                preview_cols = st.columns(3)
                with preview_cols[0]:
                    st.metric("新增", len(new_names))
                with preview_cols[1]:
                    st.metric("更新", len(update_names))
                with preview_cols[2]:
                    st.metric("保留", len(existing_names - imported_names))

                with st.expander("详细对比", expanded=True):
                    if new_names:
                        st.write("🟢 新增:", ", ".join(new_names))
                    if update_names:
                        st.write("🟡 更新:", ", ".join(update_names))
                    unchanged = existing_names - imported_names
                    if unchanged:
                        st.write("⚪ 保留:", ", ".join(unchanged))

                # History tracking integration
                from quant_assistant.history import compute_delta, record_change

                if st.button("确认更新持仓", type="primary", key="ocr_update_btn"):
                    # Save snapshot before change
                    previous_snapshot = dict(target_account)

                    merged_positions = merge_positions(target_account["positions"], parsed_positions)
                    if summary:
                        updated_account = merge_account_summary(target_account, summary)
                    else:
                        updated_account = dict(target_account)
                    updated_account["positions"] = merged_positions
                    portfolio["accounts"][detected_account] = updated_account
                    portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")

                    # Record change history
                    delta = compute_delta(previous_snapshot.get("positions", []), parsed_positions)
                    account_summary = {
                        "total_assets": updated_account.get("total_assets"),
                        "total_positions": len(merged_positions),
                    }
                    history_file = ROOT / "portfolio_history.jsonl"
                    record_change(
                        history_file,
                        change_type="ocr_import",
                        account=detected_account,
                        delta=delta,
                        summary=account_summary,
                        previous_snapshot=previous_snapshot,
                    )

                    save_json(ROOT / "portfolio.json", portfolio)
                    reload_portfolio()
                    for key in ("ocr_import_parsed", "ocr_import_summary", "ocr_import_positions", "ocr_editor"):
                        st.session_state.pop(key, None)
                    st.success(f"已更新 {detected_account} 持仓，共 {len(merged_positions)} 条。变更已记录到历史。")
                    st.rerun()
```

注意：`from quant_assistant.importer import _infer_tag` 需要在 `app.py` 的 import 区域添加。

- [ ] **步骤 2：添加 _infer_tag import**

在 `app.py` 的 import 区块中，找到 `from quant_assistant.importer import (` 部分，追加 `_infer_tag`：

```python
from quant_assistant.importer import (
    ...,
    _infer_tag,
    ...,
)
```

- [ ] **步骤 3：运行 Streamlit 验证 tag 选择和确认流程**

```bash
cd "E:\PROJECT FROM CODEX"
python -m streamlit run app.py
```

验证：
- 导入新持仓时弹出 tag 选择框
- 默认推荐值基于 `suggest_tag`
- 变更预览显示新增/更新/保留数量
- 点击确认后 portfolio.json 更新
- portfolio_history.jsonl 生成并包含记录

- [ ] **步骤 4：运行 pytest**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest -v
```

预期：全部 PASS（没有破坏现有测试）。

- [ ] **步骤 5：Commit**

```bash
cd "E:\PROJECT FROM CODEX"
git add app.py
git commit -m "$(cat <<'EOF'
feat: add tag selection for new holdings and change preview

New positions require explicit tag selection with smart default.
Show add/update/keep counts before confirmation.
Integrate change history recording on import.
EOF
)"
```

---

## 任务 5：app.py 总览页面 — 持仓变更历史面板 + 撤销

**文件：**
- 修改：`app.py` 中 `if page == "总览":` 区块

- [ ] **步骤 1：在总览页面底部添加 history 面板**

在 `app.py` 的 `if page == "总览":` 区块中，找到「完整建议」expander 之后（约第 196 行），添加：

```python
    # Change history panel
    with st.expander("📋 持仓变更记录"):
        from quant_assistant.history import read_history, rollback

        history_file = ROOT / "portfolio_history.jsonl"
        history = read_history(history_file, limit=10)

        if not history:
            st.info("暂无变更记录。导入持仓后会自动记录。")
        else:
            for record in history:
                ts = record.get("timestamp", "")[:16].replace("T", " ")
                account = "股票" if record.get("account") == "stock" else "基金"
                changes = record.get("changes", {})
                added = changes.get("added", [])
                updated = changes.get("updated", [])
                removed = changes.get("removed", [])

                parts = []
                if added:
                    parts.append(f"新增 {len(added)} 条")
                if updated:
                    parts.append(f"更新 {len(updated)} 条")
                if removed:
                    parts.append(f"移除 {len(removed)} 条")

                summary_text = "，".join(parts) if parts else "无变更"
                st.write(f"**{ts}** | {account} | {record.get('type', 'unknown')} | {summary_text}")

                detail_parts = []
                if added:
                    detail_parts.append(f"🟢 新增: {', '.join(added)}")
                if updated:
                    detail_parts.append(f"🟡 更新: {', '.join(updated)}")
                if removed:
                    detail_parts.append(f"🔴 移除: {', '.join(removed)}")
                if detail_parts:
                    st.caption("  ".join(detail_parts))

            # Rollback button
            st.divider()
            if st.button("↩️ 撤销上次导入", help="恢复到上一次导入前的持仓状态"):
                restored = rollback(history_file)
                if restored:
                    account_key = history[0].get("account") if history else None
                    if account_key and account_key in portfolio["accounts"]:
                        portfolio["accounts"][account_key] = restored
                        portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        save_json(ROOT / "portfolio.json", portfolio)
                        reload_portfolio()
                        st.success(f"已撤销上次导入，{account_key} 持仓已恢复。")
                        st.rerun()
                else:
                    st.warning("无可用的历史记录用于撤销。")
```

- [ ] **步骤 2：运行 Streamlit 验证 history 面板**

```bash
cd "E:\PROJECT FROM CODEX"
python -m streamlit run app.py
```

验证：
- 总览页面底部有「持仓变更记录」折叠面板
- 导入持仓后在此显示记录
- 撤销按钮可用且能恢复状态

- [ ] **步骤 3：运行 pytest**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest -v
```

预期：全部 PASS。

- [ ] **步骤 4：Commit**

```bash
cd "E:\PROJECT FROM CODEX"
git add app.py
git commit -m "$(cat <<'EOF'
feat: add change history panel and rollback on overview page

Show last 10 import operations with add/update/remove counts.
Add rollback button to restore previous portfolio snapshot.
EOF
)"
```

---

## 任务 6：CSV/Excel 导入也集成 history 记录

**文件：**
- 修改：`app.py` 中 CSV 导入确认更新部分

- [ ] **步骤 1：修改 CSV 导入的确认按钮回调**

在 `app.py` 中找到 CSV 导入确认部分（约第 323-331 行）：

```python
        if st.button("确认更新持仓", type="primary", key="csv_update_btn"):
            from quant_assistant.history import compute_delta, record_change

            target = portfolio["accounts"][csv_account_choice]
            previous_snapshot = dict(target)

            merged = merge_positions(target["positions"], positions)
            target["positions"] = merged
            portfolio["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")

            delta = compute_delta(previous_snapshot.get("positions", []), positions)
            account_summary = {
                "total_assets": target.get("total_assets"),
                "total_positions": len(merged),
            }
            record_change(
                ROOT / "portfolio_history.jsonl",
                change_type="csv_import",
                account=csv_account_choice,
                delta=delta,
                summary=account_summary,
                previous_snapshot=previous_snapshot,
            )

            save_json(ROOT / "portfolio.json", portfolio)
            reload_portfolio()
            st.success(f"已更新 {csv_account_choice} 持仓，共 {len(merged)} 条。变更已记录到历史。")
            st.rerun()
```

- [ ] **步骤 2：运行 pytest**

```bash
cd "E:\PROJECT FROM CODEX"
python -m pytest -v
```

预期：全部 PASS。

- [ ] **步骤 3：Commit**

```bash
cd "E:\PROJECT FROM CODEX"
git add app.py
git commit -m "$(cat <<'EOF'
feat: integrate history tracking into CSV import

CSV imports now record change history alongside OCR imports.
EOF
)"
```

---

## 自检

### 规格覆盖度

| 规格需求 | 实现任务 |
|---------|---------|
| 模式切换（截图/粘贴） | 任务 3 |
| 可编辑识别结果 | 任务 3 |
| 批量截图上传 | 任务 3 |
| 识别失败提示切换模式 | 任务 3（已有界面提示） |
| 多张截图冲突处理 | 任务 3（`_merge_parsed_frames` drop_duplicates keep="last"） |
| portfolio_history.jsonl | 任务 2 |
| history 记录结构 | 任务 2 |
| 总览页面 history 面板 | 任务 5 |
| 变更前后对比 | 任务 5 + 任务 4（详细对比 expander） |
| 撤销功能 | 任务 5 |
| 新增持仓 tag 建议 | 任务 1 + 任务 4 |
| 新增持仓必须选 tag | 任务 4 |
| 确认按钮前置条件 | 任务 4（变更预览始终展开） |
| CSV 导入也记录 history | 任务 6 |
| 错误处理 | 各任务中已覆盖 |

### 占位符扫描

- 无 "待定"、"TODO"、"后续实现"
- 每个步骤都有实际代码
- 无 "类似任务 N" 的引用
- 测试代码完整

### 类型一致性

- `compute_delta` 返回 `dict[str, list[str]]` 在所有调用处一致
- `record_change` 参数在各调用处一致
- `previous_snapshot` 类型为 `dict[str, Any]` 一致

---

## 执行选项

**计划已完成并保存到 `docs/superpowers/plans/2026-05-15-phase1-ux-improvement.md`。两种执行方式：**

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
