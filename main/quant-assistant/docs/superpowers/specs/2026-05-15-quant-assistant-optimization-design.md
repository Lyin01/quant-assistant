# Quant Assistant 优化与扩展设计文档

## 概述

本文档描述 Quant Assistant（量化助手）的四个阶段优化计划。整体原则是体验优先、逐阶段独立交付、不阻塞下一阶段。

| 属性 | 值 |
|------|-----|
| 项目 | Quant Assistant |
| 日期 | 2026-05-15 |
| 作者 | Claude Code |
| 状态 | 待实现 |

---

## 阶段一：体验优化

### 目标
让截图导入流程顺滑、持仓变更可追溯、日常操作无摩擦。

### 1.1 截图导入 UX 改进

#### 现状问题
- OCR 识别失败时用户缺乏明确指引
- 识别结果不可直接编辑修正
- 仅支持单张截图，多张需重复操作
- 粘贴文本与真 OCR 的切换不直观

#### 设计

顶部增加模式切换（截图识别 / 纯文本粘贴），两种模式互斥但可一键切换。

识别结果放在可编辑的 `st.data_editor` 中，用户可直接修改数值后重新解析。

支持多张截图批量上传，每张独立识别后合并去重（同一标的取最新一张，冲突时提示用户核对）。

识别失败时明确提示："OCR 未识别到文字，建议切换到粘贴模式手动输入。"

#### 界面结构

```
┌─────────────────────────────────────────┐
│  [截图识别] [纯文本粘贴]                 │
│                                         │
│  [上传截图] 支持 JPG/PNG，可多选        │
│                                         │
│  ┌─────────┐  ┌──────────────────────┐ │
│  │ 预览图  │  │ 识别结果（可编辑）   │ │
│  │  320px  │  │ [重新识别] [清空]    │ │
│  └─────────┘  └──────────────────────┘ │
│                                         │
│  [ + 添加更多截图 ]                     │
│                                         │
│  解析预览: 新增 2 条, 更新 1 条         │
│  [确认更新持仓]                         │
└─────────────────────────────────────────┘
```

#### 数据流

```
用户上传截图
  → run_ocr(image_bytes) → 识别文本
  → parse_ocr_positions(text) → DataFrame
  → st.data_editor 展示可编辑表格
  → 用户编辑后点击「重新解析」→ 更新 DataFrame
  → 多张截图时 merge_positions 合并去重
  → 用户确认 → 写入 portfolio.json + 记录 history
```

### 1.2 持仓变更历史记录

#### 现状问题
- 每次导入直接覆盖 portfolio.json，变更不可见
- 无法追踪"上周持仓是什么"
- 误操作无法回退

#### 设计

新增 `portfolio_history.jsonl`（JSON Lines 格式，按行追加）：

```jsonl
{"timestamp":"2026-05-15T14:32:00","type":"ocr_import","account":"stock","changes":{"updated":["半导体"],"added":["沃尔核材"],"removed":[],"summary":{"total_assets":6245.08,"total_positions":4}}}
{"timestamp":"2026-05-15T10:15:00","type":"csv_import","account":"fund","changes":{"updated":["中证500","人工智能大仓"],"added":[],"removed":[]}}
```

**History 记录结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| timestamp | ISO 8601 | 操作时间 |
| type | string | 操作类型：ocr_import / csv_import / manual_add / rollback |
| account | string | 目标账户：fund / stock |
| changes.updated | string[] | 数值有变更的持仓名称 |
| changes.added | string[] | 新增的持仓名称 |
| changes.removed | string[] | 删除的持仓名称 |
| changes.summary | object | 操作后的账户摘要（总资产、持仓数等） |
| previous_snapshot | object | 可选：操作前完整持仓快照（用于回滚） |

**界面新增：**

- 总览页面底部增加「持仓变更记录」折叠面板
- 显示最近 10 次操作的摘要（时间、方式、影响持仓数）
- 点击某条记录可展开变更前后对比（表格 diff 样式：绿色=新增，黄色=更新，红色=删除）
- 提供「撤销上次导入」按钮（从 history 恢复上一版本）

#### 数据流

```
用户确认导入
  → merge_positions() 计算 delta（added / updated / removed）
  → 保存当前 portfolio 快照到 previous_snapshot
  → 写入 portfolio.json
  → 追加记录到 portfolio_history.jsonl
  → UI 刷新显示最新状态 + history
```

### 1.3 导入结果预览增强

#### 现状问题
- 变更预览在折叠面板里，容易被忽略
- 没有"撤销"能力
- 新增持仓没有自动建议 tag

#### 设计

**确认按钮前置条件：**
1. 必须在展开状态下查看变更预览（不可直接跳过）
2. 新增持仓需用户确认或选择 tag，不自动写 `imported`
3. 提供「撤销上次导入」按钮（从 history 恢复）

**新增持仓 tag 建议（启发式）：**

```python
def suggest_tag(name: str) -> str | None:
    rules = [
        (lambda n: "500" in n or "沪深300" in n, "wide_index"),
        (lambda n: "纳指" in n or "标普" in n or "纳斯达克" in n, "overseas"),
        (lambda n: "军工" in n, "military"),
        (lambda n: "电网" in n, "power_grid"),
        (lambda n: "半导体" in n or "芯片" in n, "semiconductor"),
        (lambda n: "机器人" in n, "robot"),
        (lambda n: "人工智能" in n or "AI" in n, "tactical_ai"),
        (lambda n: "创新药" in n or "医药" in n, "healthcare"),
    ]
    for predicate, tag in rules:
        if predicate(name):
            return tag
    return None  # 让用户手动选择
```

### 1.4 错误处理

| 场景 | 行为 |
|------|------|
| OCR 识别为空 | 提示切换到粘贴模式，不阻塞流程 |
| 多张截图识别结果冲突 | 取最新一张的值，高亮提示用户核对 |
| history 文件写入失败 | 不影响 portfolio 更新，只记录 warning log |
| 导入后 portfolio.json 损坏 | 保留 `.bak` 备份，可手动恢复 |
| 撤销时 history 记录缺失 | 提示"无可用的历史记录用于撤销" |

### 1.5 测试计划

- **单元测试：** `merge_positions` 的 delta 计算（added/updated/removed）
- **单元测试：** OCR 结果编辑后的重新解析
- **单元测试：** `suggest_tag` 启发式规则覆盖主要关键词
- **单元测试：** history 记录的追加和读取
- **单元测试：** 撤销操作正确恢复上一版本
- **手动测试：** 批量截图上传 → 识别 → 合并 → 确认 → 查看 history → 撤销

---

## 阶段二：策略扩展

### 目标
把硬编码的策略规则从 `strategy.py` 中抽离，变成用户可配置的策略模板。

### 2.1 策略模板引擎

#### 设计

扩展 `config.json` 增加策略模板库：

```json
{
  "strategy_templates": {
    "tactical_sell": {
      "description": "tactical 止盈模板：涨幅达标+收益达标则卖出",
      "conditions": [
        {"field": "daily_pct", "op": ">=", "value": 1.5},
        {"field": "holding_pnl_pct", "op": ">=", "value": 12}
      ],
      "action": {"type": "SELL_MONEY", "amount": 500}
    },
    "limit_buy": {
      "description": "限价买入模板",
      "conditions": [
        {"field": "price", "op": "<=", "value_ref": "limit_buy_price"}
      ],
      "action": {"type": "BUY_SHARES", "amount_ref": "limit_buy_shares"}
    },
    "profit_sell": {
      "description": "收益止盈模板",
      "conditions": [
        {"field": "holding_pnl_pct", "op": ">=", "value_ref": "sell_profit_pct"}
      ],
      "action": {"type": "SELL_SHARES", "amount_ref": "sell_shares"}
    }
  },
  "strategy_bindings": {
    "tactical_ai": "tactical_sell",
    "semiconductor": "limit_buy",
    "healthcare": "profit_sell"
  }
}
```

**条件字段支持：** `daily_pct`, `holding_pnl_pct`, `price`, `deployable_cash`

**操作类型：** `BUY_MONEY`, `SELL_MONEY`, `BUY_SHARES`, `SELL_SHARES`, `LIMIT_BUY`, `HOLD`

**条件运算符：** `>=`, `<=`, `>`, `<`, `==`

**值引用：**
- 硬编码值：`{"value": 1.5}`
- 引用 config 规则：`{"value_ref": "sell_profit_pct"}`（从 `config.rules.semiconductor.sell_profit_pct` 读取）

#### 关键改动

- `strategy.py` 的 `generate_recommendations` 重构为模板引擎
- 遍历持仓 → 通过 `strategy_bindings` 查找模板 → 用实时行情/快照填充条件变量 → 逐条评估 → 生成 Recommendation
- 保留现有规则作为**内置默认模板**，向后兼容（config 中未定义模板时回退到内置逻辑）
- UI 新增「策略配置」页面：查看模板列表、为持仓 tag 分配模板、临时禁用某条规则

#### 数据流

```
持仓 tag
  → strategy_bindings[tag] → 模板名称
  → strategy_templates[模板名称] → 条件列表 + 动作
  → 逐条评估 conditions（用实时行情或快照填充 field 值）
  → 全部满足 → 生成 Recommendation（action + amount + reason）
  → 部分满足 → HOLD
```

### 2.2 新持仓自动模板推荐

导入新持仓时，先通过 `suggest_tag(name)` 推荐 tag，再根据 tag 查找已绑定的模板。若 tag 无绑定模板，提示用户手动选择。

### 2.3 错误处理

| 场景 | 行为 |
|------|------|
| 模板条件字段未知 | 跳过该条件，记录 warning，继续评估其他条件 |
| 模板绑定指向不存在的模板 | 回退到内置默认逻辑 |
| 条件运算符未知 | 视为不满足，记录 warning |
| value 和 value_ref 同时缺失 | 视为不满足，记录 warning |

---

## 阶段三：数据增强

### 目标
提升行情可靠性和数据丰富度。

### 3.1 行情源健康度监控

#### 设计

新增 `data_source_health.jsonl` 记录每次行情请求的结果：

```jsonl
{"timestamp":"2026-05-15T09:30:00","provider":"akshare","requested":15,"success":12,"failed":3,"latency_ms":245}
{"timestamp":"2026-05-15T09:30:00","provider":"eastmoney","requested":3,"success":3,"failed":0,"latency_ms":180}
```

**UI 新增：**
- 在「行情源状态」展开面板中增加近 7 天各数据源成功率柱状图
- 显示推荐使用的最佳数据源

### 3.2 本地磁盘缓存

#### 设计

历史 K 线数据增加本地磁盘缓存，避免每次 Streamlit 重启后重拉。

```
data/cache/
  history/
    1.000905_2025-05-15_2026-05-15_qfq.parquet
    1.515070_2025-05-15_2026-05-15_qfq.parquet
```

- 缓存文件按 `(secid, start, end, adjust)` 命名
- 格式：parquet（紧凑、加载快）
- TTL：7 天，过期自动清理
- 加载顺序：内存缓存 → 磁盘缓存 → 网络请求

### 3.3 新增技术指标

在现有 MA20/MA60 基础上，增加：

| 指标 | 计算方式 | 用途 |
|------|---------|------|
| MACD | EMA12 - EMA26, Signal=EMA9 | 趋势动量 |
| RSI(14) | 14日相对强弱指数 | 超买超卖 |
| 布林带(20,2) | MA20 ± 2*STD20 | 波动区间 |

**关键决策：** 新增指标作为「高级信号」独立展示，不改动现有的 MA/回撤信号体系。

### 3.4 错误处理

| 场景 | 行为 |
|------|------|
| 磁盘缓存损坏 | 删除损坏文件，回退到网络请求 |
| 所有数据源同时失败 | 显示明确错误，使用 portfolio.json 快照降级 |
| 指标计算数据不足 | 返回空值，UI 显示"数据不足" |

---

## 阶段四：分析面板

### 目标
新增「分析」页面，提供超越单日复盘的长期视角。

### 4.1 页面结构

```
┌─────────────────────────────────────────┐
│  分析                                   │
├─────────────────────────────────────────┤
│  [资产分布] [收益曲线] [风险评估]        │
│                                         │
│  饼图：股票/基金/现金占比               │
│  折线图：累计净值走势                   │
│  热力图：各标的月度收益矩阵             │
│  风险指标：最大回撤、波动率、夏普比率    │
└─────────────────────────────────────────┘
```

### 4.2 资产分布

- 饼图：按账户（股票/基金）和标的类型（宽基/海外/主题等）双层分布
- 数据来源：实时 `portfolio.json`

### 4.3 收益曲线

- 折线图：累计净值走势
- 数据来源：`portfolio_history.jsonl` 中每次导入的总资产快照
- X 轴：时间，Y 轴：总资产
- **注意：** 如果之前无历史记录，显示"数据不足，需持续导入持仓后生成"

### 4.4 月度收益热力图

- 矩阵：行=标的，列=月份，值=月度收益率%
- 颜色：绿色=正收益，红色=负收益，深浅表示幅度
- 数据来源：各标的历史 K 线日收益按月聚合

### 4.5 风险指标

| 指标 | 计算方式 |
|------|---------|
| 最大回撤 | 历史净值高点到低点的最大跌幅 |
| 年化波动率 | 日收益标准差 × √252 |
| 夏普比率 | (策略收益 - 无风险利率) / 波动率 |

- 按持仓权重加权计算组合层面的指标
- 各标的历史日收益率来自本地 K 线缓存

### 4.6 错误处理

| 场景 | 行为 |
|------|------|
| 历史记录不足 | 显示"持续导入持仓以生成长期分析" |
| K 线缓存缺失 | 提示先访问「历史 K 线」页面加载数据 |
| 某标的历史数据不足 | 该标的不参与组合风险计算，其余正常显示 |

---

## 跨阶段兼容性

### 数据格式兼容

- `portfolio.json` 结构保持不变，新增字段可选
- `config.json` 新增 `strategy_templates` 和 `strategy_bindings`，未定义时回退到内置逻辑
- 新增文件（`portfolio_history.jsonl`, `data_source_health.jsonl`, `data/cache/`）均为增量，不影响现有功能

### 部署策略

每个阶段完成后可独立部署：
1. 阶段一完成后 → 部署，用户体验立即改善
2. 阶段二完成后 → 部署，策略更灵活
3. 阶段三完成后 → 部署，数据更可靠
4. 阶段四完成后 → 部署，分析更全面

---

## 测试总览

| 阶段 | 单元测试重点 | 集成测试重点 |
|------|-------------|-------------|
| 一 | merge delta, OCR re-parse, suggest_tag, history CRUD | 截图→识别→编辑→确认→查看 history |
| 二 | 模板条件评估, 值引用解析, 内置回退 | 持仓→模板匹配→建议生成 |
| 三 | 健康度记录, 磁盘缓存读写, 指标计算 | 行情请求→缓存→指标展示 |
| 四 | 收益聚合, 风险指标计算 | history→收益曲线→风险面板 |

---

## 附录：新增文件清单

| 文件 | 阶段 | 说明 |
|------|------|------|
| `portfolio_history.jsonl` | 一 | 持仓变更历史 |
| `data_source_health.jsonl` | 三 | 行情源健康度记录 |
| `data/cache/history/*.parquet` | 三 | K 线磁盘缓存 |
| `docs/superpowers/specs/` | - | 设计文档目录 |
