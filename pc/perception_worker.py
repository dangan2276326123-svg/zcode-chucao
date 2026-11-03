# -*- coding: utf-8 -*-
"""感知移出主拍：一条后台线程跑 `per.process()`，主拍只取"最新结果 + 它有多旧"。

为什么要这个（11-03，作者报"0.1s 还是不动"）：手操的速度是**每拍采一次键**，而
`per.process()` 实测中位 **339 ms**（`results/crab_13` 用 `beat_gap_s` 减 `latency_ms`
同拍相减算出来的，登记在台账 Pc-15 末列），于是每一拍算出的"距上次按键多久"都 ≈ 0.39 s
> 固定窗口 `wire.TELEOP_HOLD_S = 0.1` ⇒ 每一拍都判"已经松手"，`vL/vR` 恒 0.000，
HUD 与日志都不报异常。10-21 那次 W 能用是**那天合成流根本没开**（1749 拍全 `no_frame`、
`latency_ms=0.0`），空转的拍是 45 ms——它证明的是"没有推理时 W 会动"。
窗口那个数是安全量（0.1 s × 0.2 m/s = 2 cm 的松手滑行；作者 11-03 裁定不许为"能动"抬高）
⇒ 要动的是"推理不许挡在主拍上"，不是窗口。

形状沿用本仓已经做过一次的 E2-4 决定（`common/mjpeg.py`：**慢的 producer 放线程里，
主拍取"最新的一条 + 它多旧"，取不到就按没有处理**，绝不阻塞在这一拍里）。比它多的一条是
**单槽信箱**：推理约 3 fps 而流约 15 fps，排队等于故意让指令作用在越来越旧的画上，
所以新帧进来就顶掉还没处理的那一张，被顶掉的计入 `stats()['dropped']`。

`process` / `clock` / `sleep` 全部注入 ⇒ 本模块能在没装 torch 的场合单测，
真线程冒烟那一条也只喂一个假的 `process`。
"""
import threading
import time


class Reading(object):
    """一次已完成的感知结果，加上它的来历时刻（判新旧与算管道延迟都要用）。"""

    __slots__ = ('res', 'seq', 'picked_at', 'frame_age_s', 'infer_ms')

    def __init__(self, res, seq, picked_at, frame_age_s, infer_ms):
        self.res = res
        self.seq = seq                  # 第几次发布（1 起）：主拍用它认"这一拍有没有新结果"
        self.picked_at = picked_at      # 提交那张画的 monotonic 时刻
        self.frame_age_s = frame_age_s  # 提交时那张画在流里已经多旧（`StreamFeed.get` 给的）
        self.infer_ms = infer_ms        # 这一次 `process()` 花了多久

    def delay_s(self, now):
        """这张画的**最后一字节**到 `now` 隔了多久。

        控制律真正该补的是这个数——它才是"按现在这个偏差下的令，作用到多早的状态上"。
        旧写法拿"本拍自身耗时"当它，那是推理挡在主拍上时的一个近似；推理搬到后台以后
        近似不再成立（拍 20 ms、结果 340 ms 旧），所以这里显式算出来并单列进 CSV。
        """
        return self.frame_age_s + max(0.0, now - self.picked_at)


class AsyncPerception(object):
    """单槽信箱 + 一条工作线程。主拍 `submit()` 一张画、`latest()` 取最新结果，都不阻塞。"""

    def __init__(self, process, clock=time.monotonic, name='perception', start=True):
        self._process = process
        self._clock = clock
        self._name = name
        self._lock = threading.Lock()
        self._has_work = threading.Condition(self._lock)
        self._pending = None          # (frame, picked_at, frame_age_s)
        self._latest = None           # Reading
        self._processed = 0
        self._dropped = 0
        self._error = None            # 最近一次 process() 抛的异常：不吞，主拍要能看见
        self._stop = threading.Event()
        self._thread = None
        if start:
            self.start()

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        with self._has_work:
            self._has_work.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self.stats()

    # ---- producer side ---------------------------------------------------
    def submit(self, frame, picked_at=None, frame_age_s=0.0):
        """放进信箱；返回 True 表示**顶掉了**一张还没处理的旧帧。

        `picked_at` 缺省取当前 `clock()`——测试里喂假时钟就能不靠真等待算出延迟。
        空帧（`None`）不进信箱：live 模式每拍都可能没有新帧，那不是"一张新画"。
        """
        if frame is None:
            return False
        if picked_at is None:
            picked_at = self._clock()
        with self._has_work:
            dropped = self._pending is not None
            if dropped:
                self._dropped += 1
            self._pending = (frame, picked_at, frame_age_s)
            self._has_work.notify()
        return dropped

    # ---- consumer side ---------------------------------------------------
    def latest(self):
        with self._lock:
            return self._latest

    def stats(self):
        with self._lock:
            return {'processed': self._processed, 'dropped': self._dropped,
                    'pending': self._pending is not None,
                    'infer_ms': None if self._latest is None else self._latest.infer_ms,
                    'error': repr(self._error) if self._error is not None else ''}

    # ---- worker ----------------------------------------------------------
    def _run(self):
        while not self._stop.is_set():
            with self._has_work:
                if self._pending is None:
                    self._has_work.wait(timeout=0.05)
                    if self._pending is None:
                        continue
                frame, picked_at, frame_age_s = self._pending
                self._pending = None
            t0 = self._clock()
            try:
                res = self._process(frame)
                err = None
            except Exception as exc:
                # 不吞、也不让线程死掉：主拍取不到新结果就按"没有可用感知"走
                # （`main.py` 那边 usable=False ⇒ AUTO 锁零、两秒后 vision_loss）。
                res, err = None, exc
            infer_ms = (self._clock() - t0) * 1000.0
            if res is None:
                with self._lock:
                    self._error = err
                continue
            with self._lock:
                self._processed += 1
                self._error = None
                self._latest = Reading(res, self._processed, picked_at,
                                       frame_age_s, infer_ms)
