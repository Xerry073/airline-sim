# -*- coding: utf-8 -*-
"""航空公司模拟经营 Ver1.0 —— 模拟内核（兼容门面）

真正的实现按分层拆在同目录的模块里；旧的 `import simulate as S` 与
`python simulate.py --days 720` 用法保持不变。

分层（只允许自上而下依赖）::

    config    路径、成本与经济系数、目标常量
    names     AI 公司名池（独立随机数流，不影响对局 rng）
    util      工具函数（含 FR-403 时刻触及计数）
    model     World / Aircraft / Route / Airline
    products  行程产品构建
    market    需求分配（logit + 段容量）
    settle    日结算
    ai        AI 决策与开线校验
    goals     目标模式判定
    game      Game：推进、玩家指令、快照、存档
    report    批量模拟、报告、CLI

改代码请直接改对应模块；本文件只做 re-export，不要在这里加逻辑。
"""

from config import *          # noqa: F401,F403
from names import *           # noqa: F401,F403
from util import *            # noqa: F401,F403
from model import *           # noqa: F401,F403
from products import *        # noqa: F401,F403
from market import *          # noqa: F401,F403
from settle import *          # noqa: F401,F403
from ai import *              # noqa: F401,F403
from goals import *           # noqa: F401,F403
from game import *            # noqa: F401,F403
from report import *          # noqa: F401,F403

if __name__ == "__main__":
    raise SystemExit(main())
