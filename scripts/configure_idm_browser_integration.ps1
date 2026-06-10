[CmdletBinding()]
param(
    [string]$IdmDir = "D:\IDM\Internet Download Manager",
    [switch]$ForceBrowserInstallPolicy
)

$ErrorActionPreference = "Stop"

function Assert-File {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
}

function Set-RegString {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType String -Force | Out-Null
}

function Set-RegDWord {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Value
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType DWord -Force | Out-Null
}

function Set-RegDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    Set-Item -Path $Path -Value $Value
}

function Try-SetRegDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )

    try {
        Set-RegDefault -Path $Path -Value $Value
        return $true
    }
    catch {
        Write-Warning "Skipped ${Path}: $($_.Exception.Message)"
        return $false
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

$ResolvedIdmDir = (Resolve-Path -LiteralPath $IdmDir).Path
$IdmanPath = Join-Path $ResolvedIdmDir "IDMan.exe"
$NativeHostExe = Join-Path $ResolvedIdmDir "IDMMsgHost.exe"
$ChromeNativeManifest = Join-Path $ResolvedIdmDir "IDMMsgHost.json"
$FirefoxNativeManifest = Join-Path $ResolvedIdmDir "IDMMsgHostMoz.json"
$ChromeCrx = Join-Path $ResolvedIdmDir "IDMGCExt.crx"
$EdgeCrx = Join-Path $ResolvedIdmDir "IDMEdgeExt.crx"

Assert-File -Path $IdmanPath
Assert-File -Path $NativeHostExe
Assert-File -Path $ChromeNativeManifest
Assert-File -Path $FirefoxNativeManifest
Assert-File -Path $ChromeCrx
Assert-File -Path $EdgeCrx

$ChromeExtensionId = "ngpampappnmepgilojfohadhhmbhlaek"
$EdgeExtensionId = "llbjbkhnmlidjebalopleeepgdfgcpec"
$FirefoxExtensionId = "mozilla_cc3@internetdownloadmanager.com"

$ChromeVersion = "6.42.42"
$EdgeVersion = "6.42.18.3"

$NativeHostExeJson = $NativeHostExe -replace "\\", "\\"
$ChromeNativeManifestText = @"
{
    "name"               : "com.tonec.idm",
    "description"        : "Internet Download Manager extension helper",
    "type"               : "stdio",
    "allowed_origins"    : [ "chrome-extension://$ChromeExtensionId/", "chrome-extension://$EdgeExtensionId/" ],
    "path"               : "$NativeHostExeJson"
}
"@
Write-Utf8NoBom -Path $ChromeNativeManifest -Content $ChromeNativeManifestText

$FirefoxNativeManifestText = @"
{
    "name"               : "com.tonec.idm",
    "description"        : "Internet Download Manager extension helper",
    "type"               : "stdio",
    "allowed_extensions" : [ "$FirefoxExtensionId" ],
    "path"               : "$NativeHostExeJson"
}
"@
Write-Utf8NoBom -Path $FirefoxNativeManifest -Content $FirefoxNativeManifestText

$DownloadManagerKey = "HKCU:\Software\DownloadManager"
if (-not (Test-Path -LiteralPath $DownloadManagerKey)) {
    New-Item -Path $DownloadManagerKey -Force | Out-Null
}
Set-RegString -Path $DownloadManagerKey -Name "ExePath" -Value $IdmanPath
Set-RegDWord -Path $DownloadManagerKey -Name "LaunchOnStart" -Value 1
Set-RegDWord -Path $DownloadManagerKey -Name "RunIEMonitor" -Value 0
Set-RegDWord -Path $DownloadManagerKey -Name "MonitorUrlClipboard" -Value 0

$AdditionalExtensions = @(
    "CSV", "TSV", "MD", "TXT", "JSON", "XML", "YAML", "YML",
    "DOC", "DOCX", "XLS", "XLSX", "PPT", "PPTX", "PPS", "PPSX",
    "EPUB", "MOBI", "AZW3",
    "WEBM", "FLV", "TS", "M3U8",
    "GGUF", "GGML", "SAFETENSORS", "CKPT", "PT", "PTH", "ONNX",
    "TFLITE", "MLX", "NPZ", "PARQUET", "ARROW", "XZ", "ZST", "ZSTD",
    "DMG", "DEB", "RPM", "APPIMAGE", "TORRENT"
)

$ExistingExtensions = @()
$ExistingSettings = Get-ItemProperty -Path $DownloadManagerKey -Name "Extensions" -ErrorAction SilentlyContinue
if ($ExistingSettings -and $ExistingSettings.Extensions) {
    $ExistingExtensions = $ExistingSettings.Extensions -split "\s+"
}

$MergedExtensions = @($ExistingExtensions + $AdditionalExtensions) |
    Where-Object { $_ -and $_.Trim() } |
    ForEach-Object { $_.Trim().ToUpperInvariant() } |
    Sort-Object -Unique

Set-RegString -Path $DownloadManagerKey -Name "Extensions" -Value ($MergedExtensions -join " ")

$BrowserIntegrations = @(
    @{ Key = "chrome"; Name = "Google Chrome"; WebExt = 0x4e },
    @{ Key = "msedge"; Name = "Microsoft Edge" },
    @{ Key = "Firefox"; Name = "Mozilla Firefox" },
    @{ Key = "OPERA"; Name = "Opera" },
    @{ Key = "IEXPLORE"; Name = "Internet Explorer" },
    @{ Key = "MicrosoftEdgeCP"; Name = "Microsoft Edge Legacy" },
    @{ Key = "Safari"; Name = "Apple Safari" }
)

foreach ($Browser in $BrowserIntegrations) {
    $KeyPath = Join-Path $DownloadManagerKey ("IDMBI\" + $Browser.Key)
    Set-RegString -Path $KeyPath -Name "name" -Value $Browser.Name
    Set-RegDWord -Path $KeyPath -Name "int" -Value 1
    if ($Browser.ContainsKey("WebExt")) {
        Set-RegDWord -Path $KeyPath -Name "webext" -Value $Browser.WebExt
    }
}

Set-RegDefault -Path "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.tonec.idm" -Value $ChromeNativeManifest
Set-RegDefault -Path "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.tonec.idm" -Value $ChromeNativeManifest
Set-RegDefault -Path "HKCU:\Software\Mozilla\NativeMessagingHosts\com.tonec.idm" -Value $FirefoxNativeManifest

Set-RegString -Path "HKCU:\Software\Google\Chrome\Extensions\$ChromeExtensionId" -Name "path" -Value $ChromeCrx
Set-RegString -Path "HKCU:\Software\Google\Chrome\Extensions\$ChromeExtensionId" -Name "version" -Value $ChromeVersion
Set-RegString -Path "HKCU:\Software\Microsoft\Edge\Extensions\$EdgeExtensionId" -Name "path" -Value $EdgeCrx
Set-RegString -Path "HKCU:\Software\Microsoft\Edge\Extensions\$EdgeExtensionId" -Name "version" -Value $EdgeVersion

Try-SetRegDefault -Path "HKLM:\Software\Google\Chrome\NativeMessagingHosts\com.tonec.idm" -Value $ChromeNativeManifest | Out-Null
Try-SetRegDefault -Path "HKLM:\Software\Microsoft\Edge\NativeMessagingHosts\com.tonec.idm" -Value $ChromeNativeManifest | Out-Null
Try-SetRegDefault -Path "HKLM:\Software\Mozilla\NativeMessagingHosts\com.tonec.idm" -Value $FirefoxNativeManifest | Out-Null

if ($ForceBrowserInstallPolicy) {
    Set-RegString -Path "HKCU:\Software\Policies\Google\Chrome\ExtensionInstallForcelist" -Name "1" -Value "$ChromeExtensionId;https://clients2.google.com/service/update2/crx"
    Set-RegString -Path "HKCU:\Software\Policies\Microsoft\Edge\ExtensionInstallForcelist" -Name "1" -Value "$EdgeExtensionId;https://edge.microsoft.com/extensionwebstorebase/v1/crx"
}

Set-RegString -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "IDMan" -Value "$IdmanPath /onboot"

if (-not (Get-Process -Name IDMan -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $IdmanPath -ArgumentList "/onboot" -WindowStyle Hidden
}

Write-Host "IDM browser integration configured."
Write-Host "IDM path: $IdmanPath"
Write-Host "Chrome extension: $ChromeExtensionId"
Write-Host "Edge extension: $EdgeExtensionId"
Write-Host "Firefox extension: $FirefoxExtensionId"
Write-Host "Managed install policy: $ForceBrowserInstallPolicy"
