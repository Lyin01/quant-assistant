# Quant Assistant

Quant Assistant 是一个本地/半云端的个人量化复盘助手。它读取持仓快照、行情代理和策略规则，生成买入、卖出、限价买入或持有观察建议。

本项目只生成复盘和操作建议，不接入真实下单 API，不保存券商密码，不保证投资结果。

## 当前入口

- Streamlit 应用：[app.py](app.py)
- 默认配置：[config.json](config.json)
- 默认持仓快照：[portfolio.json](portfolio.json)
- 核心代码：[src/quant_assistant](src/quant_assistant)
- 测试：[tests](tests)

## 功能

- 总览：账户资产、行情快照、今日操作清单、观察项、策略覆盖检查。
- 历史 K 线：加载标的历史行情并显示 MA20 / MA60 / 布林带。
- 信号 / ETF 排行：生成均线信号和 ETF 涨跌幅排行。
- 回测：MA 趋势回测。
- 导入持仓：CSV / Excel / 截图 OCR（含上传预览）/ 粘贴 OCR 文本 / 手动录入。
- 分析：资产分布、收益曲线、风险指标、月度收益。
- 市场扫描：ETF 多因子技术面扫描。
- 宏观/产业：宏观指标、产业链价格、政策新闻。

## 本地运行

PowerShell:

```powershell
cd "E:\PROJECT FROM CODEX"
py -m pip install -r requirements.txt
$env:PYTHONPATH = Join-Path (Get-Location) "src"
py -m streamlit run app.py
```

如果已经确认 `python` 指向正确的项目解释器，也可以使用：

```powershell
streamlit run app.py
```

## CLI 复盘

使用本地持仓快照，不请求实时行情：

```powershell
cd "E:\PROJECT FROM CODEX"
$env:PYTHONPATH = Join-Path (Get-Location) "src"
py -m quant_assistant.cli --config config.json --portfolio portfolio.json --no-live
```

保存建议日志：

```powershell
py -m quant_assistant.cli --config config.json --portfolio portfolio.json --no-live --save-log
```

## 测试

```powershell
cd "E:\PROJECT FROM CODEX"
py -m pytest
```

`pytest.ini` 已配置项目内临时目录，避免 Windows 默认 Temp 目录权限导致 `tmp_path` fixture 报错。

如果 `python` 指向 Codex/Hermes 自带环境，可能缺少 `pip` 或项目依赖；Windows 本机验证优先使用 `py -m pytest`。

完整只读验证可以直接运行：

```powershell
.\scripts\verify_quant_assistant.ps1
```

该脚本会执行 `git status --short`、`py -m py_compile app.py`、`py -m pytest`、CLI 本地快照复盘、真实持仓/日志文件哈希不变检查和 `git diff --check`。

## 数据校验

应用启动和 CLI 复盘会先做轻量结构校验：

- `config.json` 必须包含 `cash_plan`、`rules`、`quotes.proxies`。
- `portfolio.json` 必须包含 `fund` 和 `stock` 两个账户。
- 每个账户的 `positions` 必须是数组，每条持仓至少要有 `name`。

阻断级别问题会暂停应用或让 CLI 返回退出码 `2`；提示级别问题只展示提醒。

## 部署

Streamlit Cloud 使用仓库根目录作为部署根，入口文件是：

```text
app.py
```

推送 `main` 后会触发 Streamlit Cloud 重新部署。部署前确认不要提交：

- `.streamlit/secrets.toml`
- 真实券商账号、密码、身份证、银行卡信息
- API key 或 OAuth secret
- 与部署无关的大文件、视频、试验目录

当前工作区里 `agent-trials/`、`portfolio-app/`、`video-projects/`、`depcheck-grade-fixture*/`、`codex-clawbot-bridge/` 和 `*.mp4` 属于本地试验或历史产物，默认不进入部署提交。

提交时不要使用 `git add .`。本工作区长期存在本地备份、截图、实验目录和用户数据快照；请只添加本次任务实际修改的文件。2026-06-05 收尾变更的建议提交范围见 `reports/change_set_audit_2026-06-05.md`。

## 目录说明

```text
src/quant_assistant/
  analytics.py              指标、信号、回测
  analytics_panel.py        资产分析面板数据处理
  auth.py                   Streamlit OAuth 登录
  cli.py                    命令行复盘入口
  data_provider.py          EastMoney / Tencent 行情 fallback；AkShare 需显式环境变量开启
  importer.py               CSV、Excel、OCR 文本解析和持仓合并
  import_review.py          导入前校验、目标账户判定、截图解析结果合并
  market_data.py            K 线和 ETF 排行
  market_scanner.py         ETF 多因子扫描
  recommendation_view.py    建议展示和策略覆盖检查
  schema.py                 config / portfolio 轻量结构校验
  strategy.py               策略建议生成
  strategy_engine.py        策略模板条件引擎
  user_data.py              多用户持仓数据隔离
```
