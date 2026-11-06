# -*- coding: utf-8 -*-
"""路径与运行环境。

- 定位项目根目录（server/ 的上一级）
- 把 sim/ 放进 sys.path，并把内核模块暴露为 ``S``
- 静态目录、存档目录、存档 ID 正则

其它后端模块都从这里拿路径与内核引用，避免各处重复算路径。

存档目录默认是项目内的 ``saves/``；环境变量 ``AIRLINE_SIM_SAVES`` 可以把它指到别处，
用来做冒烟测试或同时跑多份互不干扰的对局（``tools/server_check.py`` 就靠它隔离）。
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sim"))

import simulate as S   # noqa: E402  内核（sim/simulate.py 门面）

WEB = ROOT / "web"
SAVES = Path(os.environ.get("AIRLINE_SIM_SAVES") or (ROOT / "saves"))
SAVES.mkdir(parents=True, exist_ok=True)
SAVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


