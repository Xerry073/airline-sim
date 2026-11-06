# -*- coding: utf-8 -*-
"""路径与运行环境。

- 定位项目根目录（server/ 的上一级）
- 把 sim/ 放进 sys.path，并把内核模块暴露为 ``S``
- 静态目录、存档目录、存档 ID 正则

其它后端模块都从这里拿路径与内核引用，避免各处重复算路径。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sim"))

import simulate as S   # noqa: E402  内核（sim/simulate.py 门面）

WEB = ROOT / "web"
SAVES = ROOT / "saves"
SAVES.mkdir(exist_ok=True)
SAVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


