<#
.SYNOPSIS
    Creates Desktop and Start Menu shortcuts for the Stress Letterbox client,
    and checks that config.yaml is actually pointed at a real server before
    handing a machine to an employee.

.DESCRIPTION
    Run this once per employee machine, after installing the client
    dependencies (requirements-client.txt) into .venv or venv.

    It does NOT edit config.yaml for you — server_url is deployment-specific
    and shouldn't be silently rewritten. It only warns if the value still
    looks like a local demo address, since shipping a client pointed at
    127.0.0.1 to someone else's machine is the most common rollout mistake.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# ── Find the venv's pythonw.exe (accepts either .venv\ or venv\) ──────────
$PythonW = $null
foreach ($venvName in @(".venv", "venv")) {
    $candidate = Join-Path $ProjectRoot "$venvName\Scripts\pythonw.exe"
    if (Test-Path $candidate) { $PythonW = $candidate; break }
}
if (-not $PythonW) {
    $msg = @"
No .venv\ or venv\ found under $ProjectRoot. Install client dependencies first:
  python -m venv venv
  venv\Scripts\activate
  pip install -r requirements-client.txt
"@
    Write-Error $msg
    exit 1
}
$PythonExe = Join-Path (Split-Path -Parent $PythonW) "python.exe"

# ── Regenerate icon.ico from icon.png, so dropping in new artwork and
# ── re-running this script is all that's needed to update the shortcut.
$IconPng = Join-Path $ProjectRoot "client\ui\icon.png"
$IconIco = Join-Path $ProjectRoot "client\ui\icon.ico"
if (Test-Path $IconPng) {
    $pyScript = @"
from PIL import Image
img = Image.open(r'$IconPng').convert('RGBA')
img.save(r'$IconIco', sizes=[(16,16),(32,32),(48,48),(256,256)])
"@
    & $PythonExe -c $pyScript
    if ($LASTEXITCODE -eq 0) {
        Write-Output "Regenerated icon.ico from icon.png."
    } else {
        Write-Warning "Could not regenerate icon.ico -- check Pillow is installed. Keeping the existing .ico, if any."
    }
} else {
    Write-Warning "No client\ui\icon.png found -- shortcuts will use the default icon."
}

# ── Warn if config.yaml still points at a local/demo address ─────────────
$ConfigPath = Join-Path $ProjectRoot "config.yaml"
if (-not (Test-Path $ConfigPath)) {
    $msg = "No config.yaml found at $ConfigPath. The client needs one -- copy " +
           "config.yaml.example and set client.server_url to the real server's " +
           "address before employees use this machine."
    Write-Warning $msg
} else {
    $serverUrlLine = Select-String -Path $ConfigPath -Pattern "server_url.*http://(127\.0\.0\.1|localhost)" -Quiet
    if ($serverUrlLine) {
        $msg = @"
config.yaml's client.server_url still points at 127.0.0.1/localhost.
That only works if the server also runs on THIS machine. For a real employee
machine, edit config.yaml and set client.server_url to the server's real
LAN address, e.g. http://192.168.1.100:5000 -- see docs/deployment.md.
"@
        Write-Warning $msg
    } else {
        Write-Output "config.yaml's server_url does not look like a local address -- good."
    }
}

# ── Create the shortcuts ──────────────────────────────────────────────────
$WshShell = New-Object -ComObject WScript.Shell
$IconPath = Join-Path $ProjectRoot "client\ui\icon.ico"

function New-ClientShortcut($Path) {
    $shortcut = $WshShell.CreateShortcut($Path)
    $shortcut.TargetPath = $PythonW
    $shortcut.Arguments = "client\main.py"
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.Description = "Launch the Stress Letterbox client widget"
    if (Test-Path $IconPath) {
        $shortcut.IconLocation = $IconPath
    }
    $shortcut.Save()
}

$DesktopPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Stress Letterbox.lnk"
New-ClientShortcut $DesktopPath

$StartMenuPath = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\Stress Letterbox.lnk"
New-ClientShortcut $StartMenuPath

Write-Output ""
Write-Output "Created:"
Write-Output "  $DesktopPath"
Write-Output "  $StartMenuPath"
Write-Output ""
Write-Output "From the Start Menu shortcut, right-click -> Pin to Start / Pin to taskbar if wanted."
