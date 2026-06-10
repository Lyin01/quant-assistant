param(
    [ValidateSet("etf", "stock", "all")]
    [string]$Universe = "etf",
    [int]$TopN = 30,
    [int]$Limit = 20,
    [int]$Workers = 6,
    [ValidateSet("strict", "balanced", "aggressive")]
    [string]$Mode = "balanced",
    [switch]$IncludeDefensive
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$NodeCandidates = @(
    "C:\Users\18312\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
    "E:\cursor\resources\app\resources\helpers\node.exe",
    "E:\python\Lib\site-packages\playwright\driver\node.exe",
    "node"
)

$Node = $null
foreach ($Candidate in $NodeCandidates) {
    if ($Candidate -ne "node" -and (Test-Path -LiteralPath $Candidate)) {
        $Node = $Candidate
        break
    }
    $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if ($Command) {
        $Node = $Command.Source
        break
    }
}

if (-not $Node) {
    throw "No available Node.js found. Install Node.js 18+ or use the Python scanner."
}

$ScriptPath = Join-Path $Root "scripts\scan_market_trends.mjs"
$NodeArgs = @($ScriptPath, "--universe", $Universe, "--top-n", $TopN, "--limit", $Limit, "--workers", $Workers, "--mode", $Mode)
if ($IncludeDefensive) {
    $NodeArgs += "--include-defensive"
}
& $Node @NodeArgs
