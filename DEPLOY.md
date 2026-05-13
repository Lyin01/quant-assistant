# 部署到 Streamlit Community Cloud

当前项目不能直接点本地页面右上角的“部署”，必须先放到 GitHub 仓库。

## 1. 创建 GitHub 仓库

在 GitHub 新建一个仓库，例如：

```text
quant-assistant
```

可以设为 Private。Streamlit Community Cloud 支持连接私有仓库，但需要授权。

## 2. 推送本地项目

PowerShell:

```powershell
cd "E:\PROJECT FROM CODEX"
git init
git add .
git commit -m "Initial quant assistant"
git branch -M main
git remote add origin https://github.com/<你的GitHub用户名>/quant-assistant.git
git push -u origin main
```

如果你用 GitHub Desktop，也可以直接选择 `E:\PROJECT FROM CODEX` 作为本地仓库，然后 Publish repository。

## 3. 在 Streamlit Cloud 部署

1. 打开 Streamlit Community Cloud。
2. 选择 `New app`。
3. 选择刚才的 GitHub 仓库。
4. Branch 选择 `main`。
5. Main file path 填：

```text
app.py
```

6. 点击 Deploy。

## 4. 更新数据

部署后如果要更新持仓，需要修改并推送：

- `portfolio.json`
- `config.json`

每次推送到 GitHub 后，Streamlit Cloud 会自动重新部署。

## 5. 安全说明

不要把券商账号、密码、身份证、银行卡、API Key 写进仓库。本项目目前不接真实下单 API，只生成操作建议。
