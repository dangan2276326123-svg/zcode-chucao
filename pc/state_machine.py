# -*- coding: utf-8 -*-
"""Safety state machine: MANUAL / AUTO / LIFT / ESTOP.

ESTOP is latched — only clear_estop() (wired to a physical reset) leaves it.
Pure-python, pytest-covered.

E3 批 1b（spec §2/§5.2/§5.3，台账 Pc-8）加了第二根轴：执行许可位 permit
（门 N / 门 F）决定 AUTO 是否允许落刀；needs_confirm 是 L2.5 的人工闸门。
许可位与"持权"两个概念都取自 pc.wire——状态机与线上层不许各写一份数字。
"""
from pc import wire


class StateMachine:
    MANUAL = 'MANUAL'
    AUTO = 'AUTO'
    TELEOP = 'TELEOP'      # 手操档（2026-10-13 拆档）：PC 持权，速度来自人按的键
    LIFT = 'LIFT'
    ESTOP = 'ESTOP'

    def __init__(self, permit=wire.GATE_N):
        self.state = self.MANUAL
        self.permit = permit          # E3 §2：门 N / 门 F 执行许可位
        self.needs_confirm = False    # E3 §5.2 L2.5：停车后必须人工确认
        self._events = []

    def _to(self, s):
        if self.state != s:
            self._events.append((self.state, s))
            self.state = s

    # -- events ---------------------------------------------------------
    def go_auto(self, confidence_ok=True):
        """User AUTO request; refused unless confidence is healthy,
        not latched in ESTOP, and the L2.5 confirm gate has been cleared
        (needs_confirm — see confirm_continue())."""
        if self.state == self.ESTOP:
            return False
        if self.needs_confirm:
            return False          # L2.5 未确认前不许再进无人
        if not confidence_ok:
            self._to(self.LIFT)
            return False
        self._to(self.AUTO)
        return True

    def go_teleop(self):
        """手操档进档（2026-10-13 spec §2，作者决定 B1/B2）。

        **与 go_auto 的唯一差别是它不查视觉信心，也不消费 L2.5 闸门**：
        指令源就是人自己，台架上没有行墙、信心永远不够，把无人的判据套过来
        等于这条档位在台架上根本不可达；而 L2.5 那道闸门保护的是"车自己在跑时
        丢了边界要不要继续"，人在开车时这件事由人判。
        唯一拒绝的仍是急停锁存——那是一条状态，不是一个告警（同 confirm_continue
        的 I-2 裁定口径）。
        """
        if self.state == self.ESTOP:
            return False
        self._to(self.TELEOP)
        return True

    def go_manual(self):
        if self.state != self.ESTOP:
            self._to(self.MANUAL)
            return True
        return False

    def vision_loss(self, no_boundary_evidence=True):
        """AUTO 下失视觉 -> LIFT（可恢复，线上发 NAV0 + TOOL 提刀）。

        E3 §5.2：无墙且**无独立边界依据**时置 needs_confirm（L2.5 保守档）——
        不声称能区分"到行尾"与"感知失败"，两类都交人判。有独立边界依据时
        （no_boundary_evidence=False）只降 LIFT，不要求人工确认。

        H2.1 旧契约保留：MANUAL 下失视觉不改状态——MANUAL 是遥控持权，PC 从不
        在那里发 NAV，若经 LIFT 出去会发出 NAV(0,0)，MCU 解释为"进 AUTO"=
        静默夺走遥控权限（review 2026-09-14）。MANUAL 下的丢失只作 HUD/日志告警。
        """
        if self.state != self.AUTO:
            return
        if no_boundary_evidence:
            self.needs_confirm = True
        self._to(self.LIFT)

    def vision_ok(self):
        """只从 LIFT 恢复到 MANUAL；**不清 needs_confirm**，也不自动回 AUTO
        （E3 §5.1：视觉恢复不得自动回无人，必须人工再按一次）。"""
        if self.state == self.LIFT:
            self._to(self.MANUAL)
            return True
        return False

    def confirm_continue(self):
        """L2.5 的人工确认键：清标志。返回是否真的清掉了。

        ESTOP 态一律拒绝（任务审查 I-2）：急停不是"告警消除"。若让确认键在 ESTOP
        里返回 True 并清掉标志，"无墙且无独立边界依据必须人工确认"这道闸门就被
        消费掉了，复归之后可以直接无确认进无人——ESTOP 与 L2.5 是两个不同问题，
        各确认各的（fail-closed：闸门保留到 clear_estop() 之后再按一次为止）。
        """
        if self.state == self.ESTOP:
            return False
        if not self.needs_confirm:
            return False
        self.needs_confirm = False
        return True

    def estop(self, source='sw'):
        """Hard or soft estop. Latched: nothing below clears it."""
        self._to(self.ESTOP)
        return source

    def clear_estop(self):
        """Physical reset path only."""
        if self.state == self.ESTOP:
            self._to(self.MANUAL)
            return True
        return False

    # -- derived flags for the control loop ------------------------------
    @property
    def holds_authority(self):
        """PC 是否持权 —— 与 wire.HOLDING 同源，别各写一份。"""
        return self.state in wire.HOLDING

    @property
    def wheels_enabled(self):
        """TELEOP 也算"轮子被 PC 驱动"（2026-10-13 拆档）：手操时线上一边是
        人按出来的 NAV，一边是 STATUS 回传，凡按"轮子是否由 PC 给速"分支的地方
        都要把两档一起算上，否则手操会被读成"PC 没在开车"。"""
        return self.state in (self.AUTO, self.TELEOP)

    @property
    def tools_raised(self):
        """E3 §5.3：门 N 下 AUTO 也提刀；只有门 F 的 AUTO 才允许落刀。

        判据写成"**不是门 F**"而不是"== 门 N"（任务审查 I-1，控制器裁定照修）：
        未知/配错的许可位（0、None、没经 wire.PERMIT_BY_NAME 映射的 'gate_f' 串）
        一律按"提刀"处理。依据 = `docs/superpowers/plans/2026-10-08-e3-batch-1a-firmware.md:18`
        那条 fail-closed 约束（"任何拿不到的量都不得当作满足"）——**那句是给固件写的**，
        批 1b 计划的 Global Constraints 里没有它；PC 侧照搬是 E3 批 1b 的任务内决定。
        这与 pc/wire.py 对未知许可位抛 ValueError 是同一个洞的两半。
        合法值行为不变：门 N 的 AUTO = True，门 F 的 AUTO = False。
        """
        return self.state != self.AUTO or self.permit != wire.GATE_F
