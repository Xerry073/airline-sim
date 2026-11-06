# Package the game into release/airline-sim-v<Version>/ plus a zip.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools/package.ps1 -Version 1.0
#   powershell -ExecutionPolicy Bypass -File tools/package.ps1 -Version 1.0 -SkipTests
#
# Notes:
#   - ASCII only, no BOM needed.
#   - Excludes saves/*.json, __pycache__, .git, release/ and handover notes.
#   - Runs the full test suite inside the package before zipping.

param(
    [string]$Version = "1.0",
    [switch]$SkipTests,
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$name = "airline-sim-v$Version"
$out = Join-Path $root "release\$name"
$zip = Join-Path $root "release\$name.zip"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }

Say "============================================" Cyan
Say "  packaging $name" Cyan
Say "============================================" Cyan

if (Test-Path $out) { Remove-Item -Recurse -Force $out }
foreach ($d in @("server", "sim", "web", "web\css", "web\js", "web\data", "tools", "calibration", "docs", "saves")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $out $d) | Out-Null
}

$rootFiles = @("README.md", "README-玩家.md", "README-开发者.md", "CONTRIBUTING.md",
               "CHANGELOG.md", ".editorconfig", ".gitignore",
               "start.cmd", "start.ps1", "play.cmd", "quit.cmd", "quit.ps1")
foreach ($f in $rootFiles) { Copy-Item (Join-Path $root $f) -Destination $out }

Copy-Item (Join-Path $root "server\*.py") -Destination (Join-Path $out "server")
Copy-Item (Join-Path $root "sim\*.py") -Destination (Join-Path $out "sim")
Copy-Item (Join-Path $root "sim\aircraft.csv"), (Join-Path $root "sim\README.md"), (Join-Path $root "sim\run_report.md") -Destination (Join-Path $out "sim")
Copy-Item (Join-Path $root "web\index.html") -Destination (Join-Path $out "web")
Copy-Item (Join-Path $root "web\css\*") -Destination (Join-Path $out "web\css")
Copy-Item (Join-Path $root "web\js\*") -Destination (Join-Path $out "web\js")
Copy-Item (Join-Path $root "web\data\*") -Destination (Join-Path $out "web\data")
Copy-Item (Join-Path $root "tools\*_check.js"), (Join-Path $root "tools\fetch_basemap.py") -Destination (Join-Path $out "tools")
Copy-Item (Join-Path $root "calibration\*") -Destination (Join-Path $out "calibration")
Copy-Item (Join-Path $root "docs\*") -Destination (Join-Path $out "docs")
New-Item -ItemType File -Force -Path (Join-Path $out "saves\.gitkeep") | Out-Null

# ---------- verify what must NOT ship ----------
$badPatterns = @("交接*", "*.pyc", "__pycache__", ".git", "release")
$bad = Get-ChildItem -Recurse -Force $out | Where-Object {
    $rel = $_.FullName.Substring($out.Length + 1)
    ($badPatterns | Where-Object { $rel -like $_ }) -or ($rel -like "saves\*.json")
}
if ($bad) {
    Say ("[FAIL] unexpected files in package: " + (($bad | ForEach-Object { $_.Name }) -join ", ")) Red
    exit 1
}
Say "  layout ok (no saves/*.json, no __pycache__, no handover notes)" Green

# ---------- tests inside the package ----------
if (-not $SkipTests) {
    $py = $null
    foreach ($c in @("python", "python3", "py")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { $py = $cmd.Source; break }
    }
    $node = (Get-Command node -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $py) { Say "[FAIL] python not found, cannot run tests (use -SkipTests to bypass)" Red; exit 1 }

    Push-Location $out
    try {
        & $py sim/selftest.py | Select-Object -Last 2
        if ($LASTEXITCODE -ne 0) { throw "selftest failed" }
        & $py -m compileall -q server sim calibration | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "compileall failed" }
        if ($node) {
            & $node.Source tools/asset_check.js | Select-Object -Last 1
            if ($LASTEXITCODE -ne 0) { throw "asset_check failed" }
            & $node.Source tools/map_check.js | Select-Object -Last 1
            if ($LASTEXITCODE -ne 0) { throw "map_check failed" }
            & $node.Source tools/goal_check.js | Select-Object -Last 1
            if ($LASTEXITCODE -ne 0) { throw "goal_check failed" }
            & $node.Source tools/panel_check.js | Select-Object -Last 1
            if ($LASTEXITCODE -ne 0) { throw "panel_check failed" }
            & $node.Source tools/route_gui_check.js | Select-Object -Last 1
            if ($LASTEXITCODE -ne 0) { throw "route_gui_check failed" }
        } else {
            Say "  [warn] node not found, skipped JS checks" Yellow
        }
    } finally {
        Pop-Location
        Get-ChildItem -Recurse -Directory $out -Filter "__pycache__" | Remove-Item -Recurse -Force
    }
    Say "  tests passed" Green
}

# ---------- zip ----------
if (-not $NoZip) {
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Compress-Archive -Path $out -DestinationPath $zip -CompressionLevel Optimal
    $kb = [math]::Round((Get-Item $zip).Length / 1KB, 1)
    Say ("  zip: $zip  ($kb KB)") Green
}

$files = (Get-ChildItem -Recurse -File -Force $out).Count
Say ("  done: $out  ($files files)") Cyan
