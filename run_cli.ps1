$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root "src"
python -m quant_assistant.cli --config (Join-Path $root "config.json") --portfolio (Join-Path $root "portfolio.json") --no-live --save-log
