# -*- coding: utf-8 -*-
"""后端冒烟测试：真起一个进程，验「保存并重启」与「保存并退出」。

回归背景：``server/app.py`` 的重启分支在 ``finally`` 里用了 ``sys.stdout.flush()``，
但文件顶部漏了 ``import sys``。内核自测全过、前端检查也全过，只有真去点一次页面上的
「保存并重启」才会 NameError → 退出码 1 → supervisor 不再拉起后端。
所以这个用例不 mock，直接跑子进程。

用 ``AIRLINE_SIM_SAVES`` 把存档目录指到临时目录，不会碰到玩家的 ``saves/``。

运行：python tools/server_check.py
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS, FAIL = [], []


def check(desc, cond, detail=""):
    (PASS if cond else FAIL).append((desc, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {desc}" + (f"  → {detail}" if detail and not cond else ""))


def free_port():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def get_json(port, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post_json(port, path, body=None, timeout=10):
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_health(port, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return get_json(port, "/api/health", timeout=1)
        except Exception:
            time.sleep(0.2)
    return None


def start_server(port, saves_dir, log_path):
    """启动后端。输出落文件而不是管道：受限环境里管道 stdio 可能被拒绝。"""
    env = dict(os.environ, AIRLINE_SIM_SAVES=str(saves_dir))
    log = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "server" / "app.py"),
         "--port", str(port), "--ai", "2", "--seed", "7",
         "--no-resume", "--autosave-seconds", "0", "--day-seconds", "60"],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    proc.dsh_log = log          # 进程结束后由 read_log 关掉
    return proc


def read_log(proc, log_path):
    try:
        proc.dsh_log.close()
    except Exception:
        pass
    try:
        return Path(log_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def stop(proc, timeout=20):
    """等退出；超时就杀掉。返回退出码，超时为 None。"""
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None


def main():
    # 不用 tempfile.mkdtemp：它建出来的目录权限是 0o700，在受限沙箱里连子目录都建不了。
    # 用普通 mkdir 在仓库里开一个临时目录，跑完删掉（.gitignore 已忽略 .smoke-*）。
    base = ROOT / f".smoke-{os.getpid()}"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    try:
        return run(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def run(tmp):
    saves = tmp / "saves"
    saves.mkdir()

    # ---------- 1. 启动 → 健康检查 ----------
    real_autosave = ROOT / "saves" / "autosave.json"
    real_before = real_autosave.stat().st_mtime_ns if real_autosave.is_file() else None
    port = free_port()
    log1 = tmp / "server1.log"
    proc = start_server(port, saves, log1)
    health = wait_health(port)
    check("后端能启动，/api/health 返回 day",
          bool(health) and health.get("ok") is True and "day" in health,
          f"{health} / 日志：{read_log(proc, log1)[-400:] if not health else ''}")
    if not health:
        proc.kill()
        return finish()

    # ---------- 2. 保存并重启（页面右上角那个按钮）----------
    try:
        res = post_json(port, "/api/restart")
        ok = bool(res.get("ok"))
    except Exception as exc:
        ok = False
        res = f"{type(exc).__name__}: {exc}"
    check("POST /api/restart 返回 ok 且已存档", ok, str(res))

    code = stop(proc)
    out = read_log(proc, log1)
    check("重启时后端以退出码 42 结束（supervisor 靠它拉起新进程）",
          code == 42, f"实际退出码 {code}；日志：{out[-400:]}")
    check("重启过程没有抛异常（sys/threading 这类漏导入会在这里暴露）",
          "Traceback" not in out, out[-400:])

    real_after = real_autosave.stat().st_mtime_ns if real_autosave.is_file() else None
    check("存档写进了独立的 AIRLINE_SIM_SAVES 目录，没碰工作区的 saves/",
          (saves / "autosave.json").is_file() and real_after == real_before,
          f"临时目录有档={(saves / 'autosave.json').is_file()}；"
          f"工作区 autosave 未变={real_after == real_before}")

    # ---------- 3. 保存并退出 ----------
    port2 = free_port()
    log2 = tmp / "server2.log"
    proc2 = start_server(port2, saves, log2)
    health2 = wait_health(port2)
    check("用同一份存档能重新启动（自动存档可读）", bool(health2), str(health2))
    if not health2:
        proc2.kill()
        read_log(proc2, log2)
        return finish()

    try:
        res = post_json(port2, "/api/quit")
        ok = bool(res.get("ok"))
    except Exception as exc:
        ok = False
        res = f"{type(exc).__name__}: {exc}"
    check("POST /api/quit 返回 ok", ok, str(res))

    code2 = stop(proc2)
    out2 = read_log(proc2, log2)
    check("退出时后端以退出码 0 结束", code2 == 0,
          f"实际退出码 {code2}；日志：{out2[-400:]}")
    return finish()


def finish():
    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    if FAIL:
        print("失败项：")
        for desc, detail in FAIL:
            print(f"  {desc}  {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
