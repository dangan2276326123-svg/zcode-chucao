# -*- coding: utf-8 -*-
"""D7 constraint tests: STATUS reception must never raise, bad frames
counted and alarmed, not silently swallowed."""
import pytest
from common import protocol as P
from pc.status_rx import StatusReceiver


def good_status(seq=1):
    return P.pack_frame(P.TYPE_STATUS,
                        P.pack_status(0.12, 1.5, 25.9, 0b010, 1), seq)


def test_good_status_parsed():
    rx = StatusReceiver()
    st = rx.handle(good_status(7), now=0.0)
    assert st['seq'] == 7 and st['limits'] == 0b010 and st['mode'] == 1
    assert st['speed_mps'] == pytest.approx(0.12, abs=1e-6)
    assert st['battery_v'] == pytest.approx(25.9, abs=1e-3)
    assert rx.good == 1 and rx.bad == 0 and rx.last == st


def test_bad_length_never_raises():
    # firmware sent a STATUS payload of the wrong length -> ValueError
    # inside handle(), counted, no exception escapes (D7 hard constraint)
    rx = StatusReceiver()
    raw = P.pack_frame(P.TYPE_STATUS, b'\x00' * 13, 1)   # 14 expected
    assert rx.handle(raw, now=0.0) is None
    assert rx.bad == 1 and rx.good == 0 and rx.last is None


def test_corrupt_and_wrong_type_counted():
    rx = StatusReceiver()
    f = bytearray(good_status())
    f[10] ^= 0xFF                       # CRC mismatch
    assert rx.handle(bytes(f), now=0.0) is None
    assert rx.handle(P.pack_frame(P.TYPE_NAV, P.pack_nav(0, 0), 2), now=0.1) is None
    assert rx.bad == 2


def test_garbage_datagram_never_raises():
    rx = StatusReceiver()
    assert rx.handle(b'\x01\x02\x03', now=0.0) is None
    assert rx.handle(b'', now=0.0) is None
    assert rx.bad == 2


def test_alarm_window_rate():
    rx = StatusReceiver()
    t = 100.0
    # 4 bad frames within the trailing 1 s window -> no alarm
    for i in range(4):
        rx.handle(b'\x00', now=t + 0.5 + i * 0.1)
    assert not rx.alarm(now=t + 1.0)
    # a 5th inside the window crosses the threshold
    rx.handle(b'\x00', now=t + 1.1)
    assert rx.alarm(now=t + 1.2)
    # window slides: 1 s after the burst it clears
    assert not rx.alarm(now=t + 2.5)


def test_good_frames_do_not_trigger_alarm():
    rx = StatusReceiver()
    for i in range(20):
        rx.handle(good_status(i), now=i * 0.01)
    assert not rx.alarm(now=0.5)
    assert rx.good == 20


# ---- R5 (2026-09-14 re-review): freshness & sequence monotonicity --------

def test_stale_before_any_frame():
    rx = StatusReceiver()
    assert rx.stale(now=0.0)          # never received -> link considered down


def test_stale_on_silence_and_fresh_on_receipt():
    rx = StatusReceiver()
    rx.handle(good_status(1), now=0.0)
    assert not rx.stale(now=0.5)
    assert rx.stale(now=2.0)          # > STALE_S with no new frame


def test_old_seq_does_not_overwrite_fresh_state():
    rx = StatusReceiver()
    rx.handle(good_status(20), now=0.0)
    assert rx.handle(good_status(19), now=0.1) is None   # stale seq rejected
    assert rx.last['seq'] == 20
    assert rx.out_of_order == 1 and rx.good == 1


# ---- E1① MCU 重启后的序号重新同步（09-21 复审修正判据）----------------
def test_reboot_monotonic_run_resyncs_after_stale_window():
    """seq1000 后 MCU 重启回到 1..N：旧逻辑要一直拒到对方追平（最坏约 27 min）。
    现在连续 50 帧"互不相同且递增"且已判 stale，即重新同步。"""
    rx = StatusReceiver()
    assert rx.handle(good_status(1000), now=0.0) is not None
    accepted = None
    t = 1.0
    for s in range(1, 60):
        r = rx.handle(good_status(s), now=t)
        t += 0.05
        if r is not None:
            accepted = (s, r['seq'])
            break
    assert accepted is not None, '重启后一直没有重新同步'
    assert accepted[1] == 50 and rx.resynced == 1
    assert rx.good == 2 and rx.out_of_order == 49


def test_repeated_identical_old_frame_never_resyncs():
    """复审指出的关键反例：同一旧帧重复 50 次不是重启证据。"""
    rx = StatusReceiver()
    rx.handle(good_status(1000), now=0.0)
    for i in range(200):
        assert rx.handle(good_status(7), now=10.0 + i * 0.05) is None
    assert rx.resynced == 0 and rx.good == 1


def test_descending_garbage_run_never_resyncs():
    rx = StatusReceiver()
    rx.handle(good_status(1000), now=0.0)
    for i, s in enumerate(range(999, 799, -1)):
        assert rx.handle(good_status(s), now=1.0 + i * 0.05) is None
    assert rx.resynced == 0


def test_resync_does_not_happen_while_status_is_still_fresh():
    """还没判 stale 就不该认定重启。"""
    rx = StatusReceiver()
    rx.handle(good_status(1000), now=0.0)
    for i in range(1, 40):
        assert rx.handle(good_status(i), now=0.2) is None   # now 一直停在新鲜窗口内
    assert rx.resynced == 0


def test_normal_wraparound_still_accepted_without_resync():
    rx = StatusReceiver()
    rx.handle(good_status(65535), now=0.0)
    assert rx.handle(good_status(0), now=0.05) is not None
    assert rx.resynced == 0 and rx.out_of_order == 0


# ---- E3 批 1b Task 4：STATUS v2 解包 / 执行面停摆 / 拒绝原因人话 ----------
# spec §3.2（19 B 载荷）、§3.5（新旧混跑，按载荷长度分派）、§5.4（HUD 用人话）

def _v2(seq, loop_alive, reject=0, mode=1, profile=2, authority=1, build=0x3A):
    payload = P.pack_status_v2(0.0, 0.0, 48.0, 0, mode, profile,
                               authority, loop_alive, build, reject)
    return P.pack_frame(P.TYPE_STATUS, payload, seq=seq)


def _v1(seq, speed=0.1, mode=0):
    return P.pack_frame(P.TYPE_STATUS,
                        P.pack_status(speed, 0.0, 48.0, 0, mode), seq=seq)


def test_v2_fields_land_in_last():
    rx = StatusReceiver()
    st = rx.handle(_v2(1, 7), now=100.0)
    assert st['v'] == 2 and st['profile'] == 2 and st['authority'] == 1
    assert st['loop_alive'] == 7 and st['build_id'] == 0x3A
    assert rx.status_version == 2


def test_v1_frame_keeps_e3_keys_none_and_does_not_crash():
    """A8 混跑用例一：旧固件帧 + 新 PC。"""
    rx = StatusReceiver()
    payload = P.pack_status(0.1, 0.0, 48.0, 0, 0)
    st = rx.handle(P.pack_frame(P.TYPE_STATUS, payload, seq=1), now=100.0)
    assert st is not None and st['v'] == 1
    assert st['profile'] is None and st['loop_alive'] is None
    assert rx.status_version == 1
    assert not rx.loop_stalled()          # v1 无从判断，绝不谎报停摆


def test_v2_frame_keeps_the_original_key_names():
    """原有五个键名一个都不能改：Task 6 的 run_log 列与 tools/bench_status.py
    都按 speed_mps/current_a/battery_v/limits/mode 取值（键名变了就是静默丢列）。"""
    rx = StatusReceiver()
    payload = P.pack_status_v2(0.37, 2.5, 47.3, 0b101, 2, 2, 1, 77, 0x3A, 0)
    st = rx.handle(P.pack_frame(P.TYPE_STATUS, payload, seq=3), now=0.0)
    assert st['speed_mps'] == pytest.approx(0.37, abs=1e-6)
    assert st['current_a'] == pytest.approx(2.5, abs=1e-6)
    assert st['battery_v'] == pytest.approx(47.3, abs=1e-3)
    assert st['limits'] == 0b101 and st['mode'] == 2 and st['seq'] == 3
    assert rx.last is not None and rx.last['v'] == 2


def test_v2_payload_first_14_bytes_keep_v1_offsets():
    """A8 混跑用例二：新固件帧 + 旧 PC（v2 帧被只有 v1 视野的消费者读取）。

    旧 PC 只读前 14 字节，所以 v2 的前 14 字节必须与 v1 同偏移同语义。
    谁把字段顺序动了，这条先红——而不是等台架上 PC 与固件静默错位。
    """
    payload = P.pack_status_v2(0.37, 2.5, 47.3, 0b101, 2, 1, 3, 77, 0x3A, 0)
    assert len(payload) == P.STATUS_V2_LEN
    old = P.unpack_status(payload[:P.STATUS_V1_LEN])   # 旧解析器视野：前 14 字节
    new = P.unpack_status_any(payload)                 # 新 PC 的 v2 路径
    assert old[0] == new['speed_mps']
    assert old[1] == new['current_a']
    assert old[2] == new['battery_v']
    assert old[3] == new['limits']
    assert old[4] == new['mode']


def test_19_byte_frames_do_not_trip_the_desync_alarm():
    """本任务的原始症状：批 1a 的固件发 19 B，PC 若只吃 14 B，则**每一帧**都被计坏帧
    丢弃，alarm() 在一秒后喊"固件/Python 协议错位"——听起来像链路坏了，
    其实是我们自己的解析没跟上（spec §3.4 点名的那类事故）。
    """
    rx = StatusReceiver()
    for i in range(20):                      # 20 Hz x 1 s，就是固件的发送节奏
        assert rx.handle(_v2(200 + i, i % 256), now=700.0 + i * 0.05) is not None
    assert rx.good == 20 and rx.bad == 0
    assert not rx.alarm(now=701.0)
    assert not rx.stale(now=701.0)
    assert not rx.loop_stalled()


def test_other_status_lengths_still_counted_as_bad():
    """§3.5：14/19 之外的长度一律计坏帧并拒绝，不许静默截断或多读。

    这条钉的是"改走 unpack_status_any 之后分派仍然严格按长度"——如果将来有人
    写成 `payload[:14]` 之类的宽容读法，19 B 之外的畸形帧会被当成好帧收进来。
    """
    rx = StatusReceiver()
    for n in (13, 15, 18, 20):
        raw = P.pack_frame(P.TYPE_STATUS, b'\x00' * n, 1 + n)
        assert rx.handle(raw, now=0.0) is None
    assert rx.bad == 4 and rx.good == 0 and rx.last is None
    assert rx.status_version is None


def test_loop_stalled_needs_five_identical_reads():
    rx = StatusReceiver()
    for i in range(4):
        rx.handle(_v2(10 + i, 3), now=100.0 + i * 0.05)
    assert not rx.loop_stalled()          # 4 帧还不够
    rx.handle(_v2(14, 3), now=100.2)
    assert rx.loop_stalled()              # 第 5 帧仍不变 -> 执行面停摆


def test_loop_stalled_false_when_counter_moves():
    rx = StatusReceiver()
    for i in range(6):
        rx.handle(_v2(20 + i, i), now=200.0 + i * 0.05)
    assert not rx.loop_stalled()


def test_loop_stalled_wraps_at_255():
    rx = StatusReceiver()
    for i, v in enumerate([253, 254, 255, 0, 1]):
        rx.handle(_v2(30 + i, v), now=300.0 + i * 0.05)
    assert not rx.loop_stalled()          # u8 回绕不算停摆


def test_five_v1_frames_are_never_read_as_stalled():
    """连续 6 帧 v1 也不得报停摆：把"字段不存在"当成一个可比较的值就会红在这里。"""
    rx = StatusReceiver()
    for i in range(6):
        rx.handle(_v1(300 + i), now=800.0 + i * 0.05)
    assert rx.status_version == 1 and rx.good == 6
    assert not rx.loop_stalled()          # v1 固件：无从判断 != 停摆


def test_loop_stalled_frames_argument_overrides_the_default():
    rx = StatusReceiver()
    for i in range(3):
        rx.handle(_v2(80 + i, 7), now=800.0 + i * 0.05)
    assert not rx.loop_stalled()          # 默认 STALL_FRAMES=5，3 帧不够
    assert rx.loop_stalled(frames=3)      # 显式放宽就立刻成立


def test_v1_frame_after_v2_clears_the_stall_reading():
    """降级到旧固件时不能继续拿 v2 的历史判停摆：没有这个字段就清零、不猜。"""
    from pc.status_rx import STALL_FRAMES
    assert STALL_FRAMES == 5              # spec §3.2：连续 5 帧（250 ms）不变
    rx = StatusReceiver()
    for i in range(STALL_FRAMES):
        rx.handle(_v2(60 + i, 42), now=600.0 + i * 0.05)
    assert rx.loop_stalled()
    assert rx.handle(_v1(70), now=601.0) is not None
    assert not rx.loop_stalled()          # v1 帧：绝不谎报
    assert rx.status_version == 1


def test_rejected_frames_do_not_enter_the_stall_history():
    """R5 拒收的旧帧连载荷都不该信（它可能属于已被丢弃的那一段）。"""
    rx = StatusReceiver()
    for i in range(4):
        rx.handle(_v2(100 + i, 7), now=1000.0 + i * 0.05)
    assert rx.handle(_v2(50, 99), now=1000.3) is None    # 旧序号 + 不同计数
    assert rx.handle(_v2(51, 98), now=1000.35) is None
    rx.handle(_v2(104, 7), now=1000.4)
    assert rx.loop_stalled()              # 历史里是 7,7,7,7,7 而不是掺进 99/98
    assert rx.out_of_order == 2 and rx.resynced == 0


def test_reject_text_is_human_readable():
    rx = StatusReceiver()
    rx.handle(_v2(40, 1, reject=P.REJECT_FIELD_SWITCH), now=400.0)
    assert rx.reject_text() == P.REJECT_TEXT[P.REJECT_FIELD_SWITCH]
    rx.handle(_v2(41, 2, reject=P.REJECT_NONE), now=400.05)
    assert rx.reject_text() == ''


def test_reject_text_empty_before_any_status_and_on_v1():
    rx = StatusReceiver()
    assert rx.reject_text() == ''         # 还没收到 STATUS
    assert rx.status_version is None
    rx.handle(_v1(1), now=0.0)
    assert rx.reject_text() == ''         # v1 没有 reject 字段：空串，不是 'None'


def test_unknown_reject_code_falls_back_without_raising():
    """reject 是 u8，固件将来加码不代表 PC 在控制循环里抛异常——兜底文案带数字。"""
    rx = StatusReceiver()
    rx.handle(_v2(50, 9, reject=99), now=500.0)
    text = rx.reject_text()
    assert text and '99' in text
    assert text not in set(P.REJECT_TEXT.values())


# ---- Task 6 前置（Task 4 审查点给 Task 6）：loop_stalled 的 frames 实参 fail-open ----
def test_loop_stalled_frames_beyond_the_window_raises():
    """传**大于** STALL_FRAMES 的值，旧实现得到的是永远 False（历史窗口 maxlen=5），
    而 docstring 当时写"只用于收紧判据"——方向正好说反。
    窗口只有这么长，超出就是不可能的判据，必须当场拒绝而不是静默不报停摆。
    """
    from pc.status_rx import STALL_FRAMES
    rx = StatusReceiver()
    for i in range(STALL_FRAMES):
        rx.handle(_v2(10 + i, 7), now=100.0 + i * 0.05)
    assert rx.loop_stalled()                     # 默认判据：5 帧同值 = 停摆
    with pytest.raises(ValueError):
        rx.loop_stalled(frames=STALL_FRAMES + 1)
    with pytest.raises(ValueError):
        rx.loop_stalled(frames=99)               # 不会因为"永远 False"而更安全


def test_loop_stalled_frames_below_one_is_clamped_to_one():
    """frames=0 旧实现里 [-0:] == [0:] = 取**整个窗口**，与 frames=1 语义不一致：
    窗口内 5 帧互不相同时 0 给 False、1 给 True，同一个调用点换个写法就翻脸。
    修法 max(1, int(frames)) 之后两者同义（都等于"最后一帧自比"，恒真，
    只许在探针里用，控制循环里必须用默认判据）。
    """
    from pc.status_rx import STALL_FRAMES
    rx = StatusReceiver()
    for i in range(STALL_FRAMES):
        rx.handle(_v2(40 + i, i), now=200.0 + i * 0.05)   # 5 帧互不相同 = 没停摆
    assert not rx.loop_stalled()
    assert rx.loop_stalled(frames=1)
    assert rx.loop_stalled(frames=0) == rx.loop_stalled(frames=1)
    assert rx.loop_stalled(frames=-3) == rx.loop_stalled(frames=1)


def test_loop_stalled_frames_is_coerced_to_int():
    """float 实参旧实现直接 TypeError（切片不接受浮点）——控制循环里抛异常
    就是把 HUD 打掉，所以这里就地 int()。"""
    rx = StatusReceiver()
    for i in range(3):
        rx.handle(_v2(50 + i, 11), now=5.0 + i * 0.05)    # 3 帧同值
    assert rx.loop_stalled(frames=2.5)
    assert rx.loop_stalled(frames=3.0)
