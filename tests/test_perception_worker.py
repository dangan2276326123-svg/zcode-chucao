# -*- coding: utf-8 -*-
"""`pc/perception_worker.py` —— 感知后台线程的三条契约。

这些测试要钉的不是"线程能不能起"，是三件会直接影响车的事：

  1. **主拍不许被推理挡住**（这是 11-03 这一批存在的唯一理由：`per.process()` 339 ms
     挡在主拍上，手操每拍采一次键 ⇒ 每一拍都判"已松手"，W 恒 0.000，台账 Pc-15）；
  2. **信箱是单槽、最新的那一张赢**——排队等于故意让指令作用在越来越旧的画上；
  3. **结果必须自带来历时刻**（`delay_s()`），因为推理搬到后台以后，"本拍耗时"再也不
     近似于"这张画有多旧"，控制律的时延超前补偿不能拿它当输入。

真线程那几条用 `threading.Event` 卡住 worker，不用 `sleep` 赌时序；纯算式那条喂假数字。
"""
import threading
import time

from pc.perception_worker import AsyncPerception, Reading


def wait_for(pred, timeout=2.0):
    """轮询到条件成立；超时返回 False，由调用方 assert 成一条看得见的失败。"""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.005)
    return False


# ---- 3. 纯算式：延迟怎么算 ----------------------------------------------

def test_delay_is_frame_age_plus_time_since_pick():
    r = Reading({'status': 'dual'}, seq=1, picked_at=100.0, frame_age_s=0.34,
                infer_ms=339.0)
    assert r.delay_s(100.0) == 0.34          # 刚提交：只有"在流里已经多旧"那一段
    assert abs(r.delay_s(100.2) - 0.54) < 1e-9


def test_delay_never_goes_negative_when_the_clock_looks_backwards():
    """单调钟不该出现这种情况，出现了也不许把"负延迟"喂给超前补偿项。"""
    r = Reading({'status': 'dual'}, 1, picked_at=100.0, frame_age_s=0.2, infer_ms=10.0)
    assert r.delay_s(99.0) == 0.2


# ---- 1+2. 真线程：不阻塞、单槽、异常不吞 ----------------------------------

def test_submit_returns_immediately_even_while_the_worker_is_busy():
    """这一条就是症状本身：主拍里 `submit()` 花的钱必须是常数，不是 339 ms。"""
    hold = threading.Event()
    started = threading.Event()

    def slow(frame):
        started.set()
        hold.wait(2.0)
        return {'status': 'dual'}

    w = AsyncPerception(slow)
    try:
        t0 = time.monotonic()
        w.submit('f1')
        assert wait_for(started.is_set), 'worker 没进 process()'
        t1 = time.monotonic()
        assert (t1 - t0) < 0.05, 'submit 被工作线程拖住了：%.3f s' % (t1 - t0)
        assert w.latest() is None          # 还没发布过 ⇒ 主拍按"没有可用感知"走
    finally:
        hold.set()
        w.stop()


def test_mailbox_is_single_slot_and_the_newest_frame_wins():
    """推理 3 fps、流 15 fps：排队就是一条越来越长的旧画队列。"""
    hold = threading.Event()
    got = []
    ready = threading.Event()

    def busy(frame):
        got.append(frame)
        ready.set()
        hold.wait(2.0)
        return {'status': 'dual', 'tag': frame}

    w = AsyncPerception(busy)
    try:
        w.submit('f1')
        assert wait_for(ready.is_set)
        assert w.submit('f2') is False, 'f1 已被取走，f2 不该算顶掉'
        assert w.submit('f3') is True, 'f2 还在信箱里，f3 必须顶掉它'
    finally:
        hold.set()
        assert wait_for(lambda: w.stats()['processed'] >= 2)
        st = w.stop()
    assert got[0] == 'f1'
    assert st['dropped'] == 1, st
    latest = w.latest()
    assert latest.seq == 2 and latest.res['tag'] == 'f3', latest.res
    assert latest.picked_at != 0.0 and latest.infer_ms >= 0.0


def test_none_frame_does_not_enter_the_mailbox():
    """live 模式每拍都可能没有新帧，那不是一张画；进了信箱就会算成"感知在跑"。"""
    w = AsyncPerception(lambda f: {'status': 'dual'}, start=False)
    assert w.submit(None) is False
    assert w.stats()['pending'] is False


def test_process_exception_is_visible_and_the_thread_survives():
    """炸一次不许让线程消失，也不许把结果留成"上一拍那一张"当新结果用。"""
    calls = []

    def flaky(frame):
        calls.append(frame)
        if len(calls) == 1:
            raise RuntimeError('cuda out of memory')
        return {'status': 'dual'}

    w = AsyncPerception(flaky)
    try:
        w.submit('a')
        assert wait_for(lambda: 'cuda' in w.stats()['error']), w.stats()
        assert w.latest() is None, '失败那一拍不许有结果'
        w.submit('b')
        assert wait_for(lambda: w.latest() is not None)
        assert w.stats()['error'] == '', w.stats()
        assert w.latest().seq == 1          # 只有成功那次占序号
    finally:
        w.stop()


def test_stop_joins_and_reports_counters():
    w = AsyncPerception(lambda f: {'status': 'dual'})
    w.submit('x')
    assert wait_for(lambda: w.stats()['processed'] == 1)
    st = w.stop()
    assert st['processed'] == 1 and st['dropped'] == 0, st
    assert w._thread is None or not w._thread.is_alive(), 'stop 之后线程还在 = 孤儿'
