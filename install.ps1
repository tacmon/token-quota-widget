[CmdletBinding()]
param(
    [string]$Python,
    [switch]$Autostart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-PythonExecutable {
    param([string]$RequestedPython)

    $arguments = @()
    if ($RequestedPython) {
        if (Test-Path -LiteralPath $RequestedPython -PathType Leaf) {
            $command = [IO.Path]::GetFullPath($RequestedPython)
        }
        else {
            $command = (Get-Command $RequestedPython -ErrorAction Stop).Source
        }
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $command = (Get-Command py).Source
        $arguments = @("-3")
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $command = (Get-Command python).Source
    }
    else {
        throw "Python 3.11+ was not found. Install Python or pass -Python with a python.exe path."
    }

    $output = @(& $command @arguments -c "import sys; print(sys.executable)")
    if ($LASTEXITCODE -ne 0 -or $output.Count -eq 0) {
        throw "The selected Python could not be executed: $command"
    }
    return [IO.Path]::GetFullPath($output[-1].Trim())
}

function New-ApplicationShortcut {
    param(
        [string]$Path,
        [string]$Pythonw,
        [string]$WorkingDirectory
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($Path)
        $shortcut.TargetPath = $Pythonw
        $shortcut.Arguments = "-m token_quota_widget"
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.Description = "Token Quota Widget"
        $shortcut.IconLocation = "$Pythonw,0"
        $shortcut.Save()
    }
    finally {
        if ($null -ne $shell) {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
        }
    }
}

if (-not $env:LOCALAPPDATA -or -not $env:APPDATA) {
    throw "LOCALAPPDATA and APPDATA must be defined."
}

$pythonExe = Resolve-PythonExecutable -RequestedPython $Python
& $pythonExe -c "import sys, tkinter; assert sys.version_info >= (3, 11), 'Python 3.11+ required'; assert tkinter.TkVersion >= 8.6, 'Tk 8.6+ required'"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11+ and Tk 8.6+ are required."
}

$pythonw = Join-Path (Split-Path -Parent $pythonExe) "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    throw "pythonw.exe was not found: $pythonw"
}

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\TokenQuotaWidget"
$packageRoot = Join-Path $installRoot "token_quota_widget"
$programsDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startupDir = Join-Path $programsDir "Startup"
$startMenuShortcut = Join-Path $programsDir "Token Quota.lnk"
$startupShortcut = Join-Path $startupDir "Token Quota.lnk"

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot "token_quota_widget\*") -Destination $packageRoot -Recurse -Force
foreach ($name in @("README.md", "README.en.md", "LICENSE", "uninstall.ps1")) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $installRoot -Force
}

New-ApplicationShortcut -Path $startMenuShortcut -Pythonw $pythonw -WorkingDirectory $installRoot
if ($Autostart) {
    New-ApplicationShortcut -Path $startupShortcut -Pythonw $pythonw -WorkingDirectory $installRoot
}

Write-Output "Installed: $installRoot"
Write-Output "Start Menu: $startMenuShortcut"
if ($Autostart) {
    Write-Output "Autostart: $startupShortcut"
}
