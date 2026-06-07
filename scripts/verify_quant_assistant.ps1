param(
    [switch]$SkipPytest,
    [switch]$SkipCli
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

function Invoke-VerificationStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "== $Name =="
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Get-OptionalFileHash {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Assert-FileHashUnchanged {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [AllowNull()]
        [string]$BeforeHash
    )

    $AfterHash = Get-OptionalFileHash -Path $Path
    if (($null -eq $BeforeHash) -and ($null -ne $AfterHash)) {
        throw "$Path was created during verification"
    }
    if (($null -ne $BeforeHash) -and ($null -eq $AfterHash)) {
        throw "$Path was removed during verification"
    }
    if (($null -ne $BeforeHash) -and ($BeforeHash -ne $AfterHash)) {
        throw "$Path changed during verification"
    }
}

Write-Host "Quant Assistant verification"
Write-Host "Repo: $RepoRoot"
Write-Host "PYTHONPATH: $env:PYTHONPATH"

Invoke-VerificationStep "Git status" {
    git status --short
}

Invoke-VerificationStep "Python syntax" {
    py -m py_compile app.py
}

if (-not $SkipPytest) {
    Invoke-VerificationStep "Pytest" {
        py -m pytest
    }
}

if (-not $SkipCli) {
    $PortfolioHashBefore = Get-OptionalFileHash -Path "portfolio.json"
    $JournalHashBefore = Get-OptionalFileHash -Path "data/journal.csv"
    Invoke-VerificationStep "CLI no-live smoke" {
        py -m quant_assistant.cli --config config.json --portfolio portfolio.json --no-live
    }
    Invoke-VerificationStep "CLI no-write guard" {
        Assert-FileHashUnchanged -Path "portfolio.json" -BeforeHash $PortfolioHashBefore
        Assert-FileHashUnchanged -Path "data/journal.csv" -BeforeHash $JournalHashBefore
    }
}

Invoke-VerificationStep "Git diff whitespace check" {
    git diff --check
}

Write-Host ""
Write-Host "All read-only verification checks completed."
