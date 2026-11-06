# -*- coding: utf-8 -*-
"""一局游戏的后端会话：时钟推进、玩家指令、存档读写、市场查询。"""

import json
import math
import secrets
import threading
import time
from datetime import datetime

from paths import S, SAVES, SAVE_ID_RE

# ============================================================
# 游戏时钟：后端权威推进，前端只读
# ============================================================

class Session:
    """一个对局：持有 Game 实例与推进线程"""

    def __init__(self, n_ai, seed, cash, speed, hub, day_seconds=60.0,
                 resume=True, autosave_seconds=60, mode=None):
        self.n_ai = n_ai
        self.seed = seed
        self.cash = cash
        self.hub = hub
        self.default_speed = speed
        self.game = S.Game(n_ai=n_ai, seed=seed, start_cash=cash,
                           player_hub=hub, with_player=True)
        self.lock = threading.RLock()
        self.game.speed = speed
        self.game.paused = (speed == 0)
        self.day_seconds = day_seconds
        self.autosave_seconds = max(0, int(autosave_seconds))
        self.quit_requested = False
        self.restart_requested = False
        self._stop = False
        self._last = time.time()
        self._last_autosave = time.time()
        self.boot_choice = None
        resumed = False
        if resume:
            try:
                self.load_game("autosave")
                resumed = True
                # 恢复后先暂停，等页面选择「继续上次对局」还是「开新对局」
                self.boot_choice = {"day": self.game.day, "name": "自动存档",
                                    "was_paused": bool(self.game.paused)}
                self.game.paused = True
                print(f"  已恢复自动存档：第 {self.game.day} 天（等待选择）")
            except Exception as exc:
                if "不存在" not in str(exc):
                    print(f"  [警告] 自动存档恢复失败：{exc}")
        if not resumed:
            if mode:
                self.game.configure_mode(mode)
            else:
                # 新对局先停留在模式选择，页面通过 /api/new_game 选择后开跑
                self.game.mode = "sandbox"
                self.game.mode_chosen = False
                self.game.paused = True
        if not self.game.mode_chosen:
            self.game.paused = True
        self._last_autosave = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def new_game(self, mode):
        """按页面选择重建第 0 天对局；沙盒/目标模式都从完整新局开始。"""
        if mode not in ("sandbox", "goals"):
            raise ValueError("模式必须是 sandbox 或 goals")
        with self.lock:
            g = S.Game(n_ai=self.n_ai, seed=self.seed, start_cash=self.cash,
                       player_hub=self.hub, with_player=True)
            g.configure_mode(mode)
            g.speed = self.default_speed
            g.paused = (self.default_speed == 0)
            self.game = g
            self.boot_choice = None
            self._last = time.time()
            self._last_autosave = time.time()
            return {"ok": True, "goals": g.goals_snapshot()}

    def _loop(self):
        """1 游戏日 = day_seconds 真实时间 / 倍速（正式版 day_seconds = 60）"""
        while not self._stop:
            time.sleep(0.05)
            with self.lock:
                g = self.game
                if g.paused or g.speed <= 0:
                    self._last = time.time()
                    continue
                need = self.day_seconds / g.speed
                now = time.time()
                if now - self._last >= need:
                    g.advance_day()
                    self._last = now
                if (self.autosave_seconds > 0 and g.day > 0
                        and now - self._last_autosave >= self.autosave_seconds):
                    try:
                        self.save_autosave()
                    except Exception as exc:
                        print(f"  [警告] 自动存档失败：{exc}")
                    self._last_autosave = now

    def stop(self):
        self._stop = True

    def snapshot(self):
        with self.lock:
            snap = self.game.snapshot()
            snap["boot"] = self.boot_choice
            return snap

    def boot_continue(self):
        """玩家选择继续上次对局：清掉启动提示，恢复到存档时的暂停状态"""
        with self.lock:
            choice = self.boot_choice or {}
            self.boot_choice = None
            if not choice.get("was_paused", False):
                self.game.paused = False
            self._last = time.time()
            return {"ok": True, "paused": self.game.paused}

    def apply(self, action, args):
        with self.lock:
            if not self.game.mode_chosen:
                return {"ok": False, "reason": "请先选择沙盒或目标模式"}
            if self.game.settlement:
                return {"ok": False, "reason": "目标模式已结算，请重新开局或切换模式"}
            return self.game.apply(action, args)

    def control(self, paused, speed):
        with self.lock:
            if not self.game.mode_chosen:
                wants_run = (paused is False) or (speed is not None and int(speed) > 0)
                self.game.paused = True
                return {"paused": True, "speed": self.game.speed,
                        "reason": "请先选择沙盒或目标模式" if wants_run else None}
            if self.game.settlement:
                wants_run = (paused is False) or (speed is not None and int(speed) > 0)
                self.game.paused = True
                return {"paused": True, "speed": self.game.speed,
                        "reason": "目标模式已结算，请重新开局或切换模式" if wants_run else None}
            return self.game.control(paused, speed)

    # ---------- 存档 / 读档 ----------

    @staticmethod
    def _save_path(save_id):
        sid = str(save_id or "")
        if not SAVE_ID_RE.fullmatch(sid):
            raise ValueError("存档 ID 非法")
        path = (SAVES / f"{sid}.json").resolve()
        if path.parent != SAVES.resolve():
            raise ValueError("存档路径非法")
        return path

    @staticmethod
    def _meta(save_id, data):
        gd = data.get("game") or {}
        player = next((a for a in gd.get("airlines", []) if a.get("is_player")), {})
        return {
            "id": save_id,
            "name": data.get("name") or f"第 {gd.get('day', 0)} 天",
            "saved_at": data.get("saved_at"),
            "day": gd.get("day", 0),
            "player": player.get("name", "—"),
            "cash": player.get("cash", 0.0),
            "routes": len(player.get("routes") or []),
            "fleet": len(player.get("fleet") or []),
            "ai": sum(1 for a in gd.get("airlines", []) if not a.get("is_player")),
            "auto": bool(data.get("auto")),
        }

    def list_saves(self):
        out = []
        for path in sorted(SAVES.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("format") != S.SAVE_FORMAT:
                    continue
                out.append(self._meta(path.stem, data))
            except Exception:
                continue
        return out

    def _write_save(self, save_id, name=None, auto=False):
        with self.lock:
            g = self.game
            player = g.player
            day = g.day
            clean = " ".join(str(name or "").split())[:40]
            if not clean:
                clean = f"第 {day} 天 · {player.name if player else '对局'}"
            now = datetime.now().astimezone()
            data = g.to_save()
            data["name"] = clean
            data["auto"] = bool(auto)
            data["saved_at"] = now.isoformat(timespec="seconds")
            path = self._save_path(save_id)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
            tmp.replace(path)
            return {"ok": True, "save": self._meta(save_id, data)}

    def save_game(self, name=None):
        now = datetime.now().astimezone()
        save_id = now.strftime("save_%Y%m%d-%H%M%S") + "_" + secrets.token_hex(3)
        return self._write_save(save_id, name, False)

    def save_autosave(self):
        return self._write_save("autosave", "自动存档", True)

    def load_game(self, save_id):
        path = self._save_path(save_id)
        if not path.is_file():
            raise ValueError("存档不存在")
        data = json.loads(path.read_text(encoding="utf-8"))
        with self.lock:
            game = S.Game.from_save(data)
            if not game.mode_chosen or game.settlement:
                game.paused = True
            self.game = game
            self._last = time.time()
        return {"ok": True, "save": self._meta(save_id.split(".")[0], data)}

    def delete_save(self, save_id):
        path = self._save_path(save_id)
        if not path.is_file():
            raise ValueError("存档不存在")
        path.unlink()
        return {"ok": True}

    def market(self, iata_a, iata_b):
        """某对机场之间的市场情报：需求池、现有运力、竞争者、建议班次与票价"""
        with self.lock:
            w = self.game.world
            if iata_a not in w.airports or iata_b not in w.airports:
                return {"ok": False, "reason": "机场代码不存在"}
            ca, cb = w.airports[iata_a]["city"], w.airports[iata_b]["city"]
            if ca == cb:
                return {"ok": False, "reason": "同城机场之间不构成航线"}
            d = w.dist(ca, cb)
            total, air = w.demand_air(ca, cb)

            seats, firms, my_seats = 0.0, {}, 0.0
            for al in self.game.airlines:
                if not al.alive:
                    continue
                for r in al.routes:
                    seg_cities = [w.airports[s]["city"] for s in r.segments]
                    hit = (ca in seg_cities and cb in seg_cities)
                    if not hit:
                        continue
                    t = w.ac(r.ac_type)
                    cap = r.daily_flights * t["seats"] * r.op_factor()
                    seats += cap
                    firms[al.name] = firms.get(al.name, 0.0) + cap
                    if al.is_player:
                        my_seats += cap

            typ = "A320"
            per_flight = w.ac(typ)["seats"]
            need_lf = 0.80
            suggest = max(1, math.ceil((air * need_lf) / max(1, per_flight)))
            suggest = min(14, suggest)

            tb = max(w.airports[s]["tier"] for s in [iata_a, iata_b])
            ta = min(w.airports[s]["tier"] for s in [iata_a, iata_b])
            b = max(0.04, min(0.30, 0.04 + 0.010 * (ta + tb) + 0.00004 * d))

            return {
                "ok": True, "from": iata_a, "to": iata_b,
                "cities": [ca, cb], "distance_km": round(d, 0),
                "demand_total": round(total, 0),
                "demand_air": round(air, 0),
                "supply_seats": round(seats, 0),
                "load_ratio": round(seats / air, 3) if air > 0 else None,
                "competitors": sorted(
                    [{"name": k, "seats": round(v, 0)} for k, v in firms.items()],
                    key=lambda x: -x["seats"])[:6],
                "my_seats": round(my_seats, 0),
                "suggest_flights": suggest,
                "p_ref_eco": round(w.p_ref(d, "eco"), 0),
                "p_ref_biz": round(w.p_ref(d, "biz"), 0),
                "biz_share": round(b, 3),
                "hub_flags": [iata_a in (self.game.player.hubs if self.game.player else []),
                              iata_b in (self.game.player.hubs if self.game.player else [])],
            }


