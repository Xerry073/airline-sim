# 航空模拟经营 —— 快捷退出
# 自动存档并停止后端；如果后端不在运行则直接结束。
# 用法：双击 quit.cmd，或 powershell -ExecutionPolicy Bypass -File quit.ps1 [-Port 8777]

param(
    [int]$Port = 8777
)

$ErrorActionPreference = "SilentlyContinue"
$u = "http://127.0.0.1:$Port"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

function Say {
    param([string]$msg = "", [string]$color = "Gray")
    Write-Host $msg -ForegroundColor $color
}

function Test-Alive {
    try {
        $r = Invoke-WebRequest -Uri "${u}/api/health" -TimeoutSec 2 -UseBasicParsing
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Say "============================================" Cyan
Say "  航空模拟经营 · 保存并退出" Cyan
Say "============================================" Cyan

if (-not (Test-Alive)) {
    Say "  没有检测到 $u 上的后端。" Yellow
    Say "  游戏本来就没有在运行，无需退出。" DarkGray
    Start-Sleep -Milliseconds 1200
    exit 0
}

$requested = $false
try {
    $body = '{}'
    $res = Invoke-RestMethod -Uri "${u}/api/quit" -Method Post -ContentType "application/json" `
        -Body $body -TimeoutSec 15
    if ($res.ok) {
        $requested = $true
        Say "  已自动存档，正在停止后端…" Green
    }
} catch {
    Say "  退出请求失败：$($_.Exception.Message)" Red
}

if (-not $requested) {
    Say "  当前后端可能不是新版本，或退出接口不可用。" Yellow
    Say "  请关闭后端 Python 窗口；也可以运行任务管理器结束 python.exe。" DarkGray
    exit 1
}

# 等 supervisor / app 真正退出
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    if (-not (Test-Alive)) {
        Say "  后端已停止，可以关闭浏览器。" Green
        Say "  下次双击桌面「航空模拟」会自动恢复存档。" DarkGray
        Start-Sleep -Milliseconds 1500
        exit 0
    }
}

Say "  后端 10 秒内仍未停止，请手动关闭后端 Python 窗口。" Red
exit 1
