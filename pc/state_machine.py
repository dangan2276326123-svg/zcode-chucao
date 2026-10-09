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
        """User AUTO request; refused unless confidence is healthy and
        not latched in ESTOP."""
        if self.state == self.ESTOP:
            return False
        if self.needs_confirm:
            return False          # L2.5 未确认前不许再进无人
        if not confidence_ok:
            self._to(self.LIFT)
            return False
        self._to(self.AUTO)
        return True

    def go_manual(self):
        """Operator override always allowed (except latched ESTOP)."""
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
        """L2.5 的人工确认键：清标志。返回是否真的清掉了。"""
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
        return self.state == self.AUTO

    @property
    def tools_raised(self):
        """E3 §5.3：门 N 下 AUTO 也提刀；只有门 F 的 AUTO 才允许落刀。"""
        return self.state != self.AUTO or self.permit == wire.GATE_N
