# -*- coding: utf-8 -*-
"""Safety state machine: MANUAL / AUTO / LIFT / ESTOP.

ESTOP is latched — only clear_estop() (wired to a physical reset) leaves it.
Pure-python, pytest-covered.
"""


class StateMachine:
    MANUAL = 'MANUAL'
    AUTO = 'AUTO'
    LIFT = 'LIFT'
    ESTOP = 'ESTOP'

    def __init__(self):
        self.state = self.MANUAL
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

    def vision_loss(self):
        """Confidence lost / link timeout -> lift and stop (recoverable)."""
        if self.state == self.ESTOP:
            return
        self._to(self.LIFT)

    def vision_ok(self):
        """Recovery from LIFT only; AUTO resume requires go_auto()."""
        if self.state == self.LIFT:
            self._to(self.MANUAL)
            return True
        return False

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
    def wheels_enabled(self):
        return self.state == self.AUTO

    @property
    def tools_raised(self):
        """Lift command active in every state except AUTO."""
        return self.state != self.AUTO
