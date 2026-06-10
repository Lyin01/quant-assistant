# Codex ComfyUI Video Pipeline

本项目把 Codex、ComfyUI、Hyperframes 和 ffmpeg 串成一个本地自动化视频流。

## 已配置路径

- 项目：`E:\PROJECT FROM CODEX\codex_comfy_video_pipeline`
- ComfyUI 程序：`E:\PROJECT FROM CODEX\tools\ComfyUI`
- ComfyUI 模型：`E:\ComfyUI_models`
- ffmpeg：`E:\PROJECT FROM CODEX\tools\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe`

## 启动

ComfyUI 已配置启动脚本：

```powershell
& "E:\PROJECT FROM CODEX\tools\ComfyUI\start_codex_comfyui.ps1"
```

项目检查：

```powershell
python -m codex_video_pipeline check --config .\config.json
```

生成计划和 Hyperframes 微调任务：

```powershell
python -m codex_video_pipeline run --config .\config.json --topic "未来城市的一天" --scene-count 2 --dry-run
```

## Workflows

`workflows\flux_text_to_image.api.json` 是基于当前 ComfyUI `/object_info` 和本机模型生成的真实 API workflow，使用：

- `flux1-dev-fp8.safetensors`
- `clip_l.safetensors`
- `t5xxl_fp8_e4m3fn.safetensors`
- `ae.safetensors`

`workflows\wan_text_to_video_api.api.json` 使用当前 ComfyUI 内置 Wan API 节点，适合作为视频生成占位/云端节点接入。若要跑本地 Wan 模型视频，需要继续安装对应本地 Wan 视频节点和完整 workflow。
