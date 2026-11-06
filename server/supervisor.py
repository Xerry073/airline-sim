# -*- coding: utf-8 -*-
"""后端监督进程。

start.cmd / start.ps1 实际启动这个进程；它再启动 server/app.py。
app.py 收到「保存并重启」后以退出码 42 结束，本脚本会原参数重新拉起它；
收到「保存并退出」后以 0 结束，本脚本随之退出。

这样前端不需要浏览器权限，也不依赖外部脚本就能完成安全重启。
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "server" / "app.py"
RESTART_CODE = 42


def main():
    args = [str(a) for a in sys.argv[1:]]
    # 首次启动允许 --no-resume；但前端触发的重启必须恢复自动存档。
    restart_args = [a for a in args if a != "--no-resume"]
    cmd = [sys.executable, str(APP), *args, "--supervised"]
    proc = None
    try:
        while True:
            proc = subprocess.Popen(cmd, cwd=ROOT)
            code = proc.wait()
            if code != RESTART_CODE:
                return code
            print("\n[supervisor] 收到重启请求，正在重新启动后端…")
            time.sleep(0.4)
            cmd = [sys.executable, str(APP), *restart_args, "--supervised"]
    except KeyboardInterrupt:
        print("\n[supervisor] 正在停止后端…")
        if proc and proc.poll() is None:
            proc.terminate()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
