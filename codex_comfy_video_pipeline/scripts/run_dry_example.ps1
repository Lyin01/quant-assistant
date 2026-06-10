$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python -m codex_video_pipeline run --config .\config.json --topic "未来城市的一天" --scene-count 2 --dry-run
