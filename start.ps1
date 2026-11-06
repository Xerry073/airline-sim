# 航空公司模拟经营 —— 启动器
# 用法：双击 start.cmd，或 powershell -ExecutionPolicy Bypass -File start.ps1

param(
    [int]$Port = 8777,
    [int]$Ai = 50,
    [int]$Speed = 4,
    [switch]$NoBrowser,
    [switch]$NoResume
)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$u = "http://127.0.0.1:$Port/"

function Say {
    param([string]$msg = "", [string]$color = "Gray")
    Write-Host $msg -ForegroundColor $color
}

Say "============================================" Cyan
Say "  航空公司模拟经营" Cyan
Say "============================================" Cyan

# ---------- 1. 已有服务在跑就直接开浏览器 ----------
# 不用 Get-NetTCPConnection 判断：本机上它可能看不到监听，但 HTTP 实际是通的
$alive = $false
try {
    $r = Invoke-WebRequest -Uri "${u}api/health" -TimeoutSec 2 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $alive = $true }
} catch { }

if ($alive) {
    Say "  检测到端口 $Port 上已有游戏在运行。" Yellow
    Say "  直接打开浏览器 -> $u" Green
    Say "  重启：页面「存档」→「保存并重启」；也可关旧窗口再运行 start.cmd。" Yellow
    Say "  退出：页面「存档」→「保存并退出」，或关掉旧后端窗口。" DarkGray
    if (-not $NoBrowser) { Start-Process $u }
    Start-Sleep -Milliseconds 800
    exit 0
}

# ---------- 2. 找一个 Python 3.9+（本游戏只用标准库，无需第三方包） ----------
$cands = @()
foreach ($n in @("python", "python3", "py")) {
    $c = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { $cands += $c.Source }
}
$cands += @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
)

$py = $null
$skipped = @()
foreach ($c in $cands) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    $probe = & $c -c "import sys;print(sys.version_info[0],sys.version_info[1])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $probe) {
        $parts = ($probe -split " ")
        if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 9) { $py = $c; break }
    }
    $skipped += $c
}

if (-not $py) {
    Say "[错误] 没有找到 Python 3.9+。" Red
    if ($skipped.Count) { Say ("        尝试过但不可用：" + ($skipped -join " ; ")) DarkYellow }
    Say "        请到 python.org/downloads 安装，安装时勾选 Add python.exe to PATH。" DarkYellow
    Say "        本游戏只用 Python 标准库，不需要 numpy 或其他第三方包。" DarkYellow
    if (-not $NoBrowser) { Read-Host "按回车退出" }
    exit 1
}
Say "  Python : $py"
Say "  端口   : $Port    对手数: $Ai    倍速: ${Speed}x"
Say ""

# ---------- 3. 启动后端（由 supervisor 托管，支持页面内安全重启） ----------
Say "  正在启动后端..." Green
$a = @("server\supervisor.py", "--port", "$Port", "--ai", "$Ai", "--speed", "$Speed")
if ($NoResume) { $a += "--no-resume" }
Start-Process -FilePath $py -ArgumentList $a -WorkingDirectory $root -WindowStyle Normal | Out-Null

# ---------- 4. 等健康检查通过再开浏览器 ----------
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 400
    try {
        $r = Invoke-WebRequest -Uri "${u}api/health" -TimeoutSec 1 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}

if ($ok) {
    Say "  后端已就绪 -> $u" Green
    if (-not $NoBrowser) { Start-Process $u }
    Say ""
    Say "  关掉弹出的后端窗口即停止游戏。" DarkGray
    Say "  页面「存档」里可「保存并退出 / 保存并重启」。" DarkGray
    Say "  退出/重启前会自动写 autosave，下次启动默认恢复。" DarkGray
    exit 0
} else {
    Say "[警告] 没有等到后端响应，请看弹出的后端窗口里的报错。" Red
    if (-not $NoBrowser) { Start-Process $u }
    exit 1
}
