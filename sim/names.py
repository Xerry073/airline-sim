# -*- coding: utf-8 -*-
"""AI 航司名称池：给 AI 对手取真实感名字，而不是 AI-01、AI-02。

设计要点：

1. **池子固定 100 个名字**，40 个中文（``XXX航空``）+ 60 个英文（``XXX Airlines``），
   开新局时按种子无放回抽取 ``n_ai`` 个，所以同一局内不会重名，中英文会自然混着出现，
   不同种子抽到的组合也不同。
2. **不消耗对局随机数流**。名字用独立 ``random.Random`` 生成：``Game.rng`` 的序列决定了
   AI 的开线/定价决策，如果在这儿抽名字，同一 seed 的整局走势都会改变（老存档之外的
   行为回归、标定数据、selftest 期望值全部要重算）。名字只影响观感，不该有这个副作用。
3. **不与玩家重名**：``taken`` 里传玩家公司名，抽到就排除。
"""

import random

# 中文名：方向、美好祝愿这类抽象两字词 + 航空，刻意不用具体的江河、山脉、城市地名。
AI_NAMES_CN = (
    "北方航空", "南方航空", "东方航空", "西部航空", "和平航空",
    "太平航空", "大同航空", "中原航空", "华东航空", "华南航空",
    "华北航空", "华中航空", "西南航空", "西北航空", "东北航空",
    "阳光航空", "曙光航空", "旭日航空", "晨曦航空", "晴空航空",
    "长空航空", "碧空航空", "星辰航空", "星辉航空", "明月航空",
    "彩虹航空", "朝霞航空", "清风航空", "顺风航空", "扬帆航空",
    "远航航空", "启航航空", "飞跃航空", "腾飞航空", "鹏程航空",
    "万里航空", "锦绣航空", "卓越航空", "通达航空", "康宁航空",
)

# 英文名：单个意象词 + Airlines，跟 Spirit / Eastern / Ocean 一个风格。
AI_NAMES_EN = (
    "Spirit Airlines", "Eastern Airlines", "Ocean Airlines", "Horizon Airlines",
    "Summit Airlines", "Aurora Airlines", "Pioneer Airlines", "Comet Airlines",
    "Zenith Airlines", "Eclipse Airlines", "Nova Airlines", "Orbit Airlines",
    "Falcon Airlines", "Albatross Airlines", "Pelican Airlines", "Heron Airlines",
    "Sparrow Airlines", "Swift Airlines", "Kestrel Airlines", "Condor Airlines",
    "Bison Airlines", "Antelope Airlines", "Puma Airlines", "Otter Airlines",
    "Lynx Airlines", "Ibex Airlines", "Mammoth Airlines", "Walrus Airlines",
    "Marlin Airlines", "Tarpon Airlines", "Coral Airlines", "Reef Airlines",
    "Lagoon Airlines", "Harbor Airlines", "Anchor Airlines", "Compass Airlines",
    "Meridian Airlines", "Crest Airlines", "Ridge Airlines", "Canyon Airlines",
    "Prairie Airlines", "Tundra Airlines", "Monsoon Airlines", "Zephyr Airlines",
    "Breeze Airlines", "Solstice Airlines", "Equinox Airlines", "Galaxy Airlines",
    "Nebula Airlines", "Quasar Airlines", "Voyager Airlines", "Wayfarer Airlines",
    "Trailblazer Airlines", "Northstar Airlines", "Polaris Airlines", "Borealis Airlines",
    "Australis Airlines", "Sundial Airlines", "Lantern Airlines", "Beacon Airlines",
)

AI_NAME_POOL = AI_NAMES_CN + AI_NAMES_EN


def pick_ai_names(count, seed, taken=()):
    """按 ``seed`` 抽 ``count`` 个不重复的 AI 公司名。

    池子不够（``count > 100``）时先用完整池子，再用 ``AI-nn`` 兜底，保证名字仍然唯一。
    同一 ``seed`` + 同一 ``taken`` 的结果是确定的，且与 ``Game.rng`` 的状态无关。
    """
    count = max(0, int(count))
    excluded = {str(n) for n in taken if n}
    pool = [n for n in AI_NAME_POOL if n not in excluded]
    rng = random.Random((int(seed) + 1) * 1000003 + len(excluded))
    names = rng.sample(pool, min(count, len(pool)))
    for i in range(len(names), count):
        names.append(f"AI-{i + 1:02d}")
    return names
