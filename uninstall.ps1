[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $env:LOCALAPPDATA -or -not $env:APPDATA) {
    throw "LOCALAPPDATA and APPDATA must be defined."
}

$programFilesRoot = Join-Path $env:LOCALAPPDATA "Programs"
$programFilesRoot = [IO.Path]::GetFullPath($programFilesRoot)
$programFilesRoot = $programFilesRoot.TrimEnd(
    [IO.Path]::DirectorySeparatorChar
) + [IO.Path]::DirectorySeparatorChar
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\TokenQuotaWidget"
$installRoot = [IO.Path]::GetFullPath($installRoot)

if (-not $installRoot.StartsWith(
    $programFilesRoot,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Refusing to remove a path outside the expected directory: $installRoot"
}

$programsDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startMenuShortcut = Join-Path $programsDir "Token Quota.lnk"
$startupShortcut = Join-Path $programsDir "Startup\Token Quota.lnk"
$settingsRoot = Join-Path $env:LOCALAPPDATA "TokenQuotaWidget"

Set-Location ([IO.Path]::GetTempPath())
if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}
foreach ($shortcut in @($startMenuShortcut, $startupShortcut)) {
    if (Test-Path -LiteralPath $shortcut) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}

Write-Output "Token Quota Widget was uninstalled."
Write-Output "Settings were retained at: $settingsRoot"
