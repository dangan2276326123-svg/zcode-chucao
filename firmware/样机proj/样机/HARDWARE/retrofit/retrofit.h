#ifndef _RETROFIT_H
#define _RETROFIT_H
/* Weeding retrofit module: dual-command-source chassis control, knife
   interlock, UDP-link watchdog, middle-tool stepper, wheel-speed capture,
   status reporting.  Pins per v0.7 section 13.2 — do not touch existing
   allocations (PA10 SBUS, TIM1 PE9/11/13/14, PA5/PF10/PF8 relays). */
#include <stdint.h>
#include "protocol.h"

/* mode reported to PC */
#define MODE_MANUAL 0
#define MODE_AUTO   1
#define MODE_ESTOP  2
#define MODE_TELEOP 3      /* PC 手操档：速度来自人按的键（2026-10-13 填上批 1a 留的空位） */
/* 手操档速度上限（spec §5）。与 pc/wire.py 的 TELEOP_MAX_MPS 各写一份、都要写：
   两层的值一旦漂开，现场真正生效的是漂移的那一个，所以两边都别偷偷改。 */
/* Teleop steering gear, carried in NAV.flags -- the byte that has been on the
   wire since batch 1a and that nobody read until 2026-10-14.
   0 straight / 1 left / 2 right / 3 lateral (crab).  3 was refused until
   2026-10-21, when it stopped being "a bigger LEFT" and became the vendor's own
   lateral mode: the body turns as a whole by Switch_direction, so it needs no
   track/wheelbase number and the tyre-scrubbing worry (ledger Hw-23) does not
   apply to it.  LEFT/RIGHT are still the placeholder pair at TELEOP_STEER_DEG,
   and their numbers are NOT calibrated. */
#define TELEOP_GEAR_STRAIGHT 0
#define TELEOP_GEAR_LEFT     1
#define TELEOP_GEAR_RIGHT    2
#define TELEOP_GEAR_LATERAL  3   /* the vendor lateral: 4 servos one number + paired speeds */
#define TELEOP_GEAR_MAX      TELEOP_GEAR_LATERAL
/* Steering magnitude for the manual gears.  20 deg is NOT derived here -- the
   NUMBER is the one the vendor uses at path_plan.c:97-110, but that block is
   stopped-vehicle residue (gated on sbus_channel[4]<1300, runs after
   telecontrol()) and its +/- pair is NOT the shape of a turn: the live
   path_plan.c:651-681 writes both front angles with the SAME sign for a left
   turn.  See main.c's TELEOP block for the 2026-10-15 correction -- the
   magnitude is still a placeholder, the shape is now the vendor's own.
   Author ruling 2026-10-14: ship it for the previous generation of the
   vehicle and fix it against what is actually observed; the sample machine
   must be re-checked before inheriting any of it. */
#define TELEOP_STEER_DEG     20.0
/* LATERAL is not a bigger LEFT: it is the vendor's own Switch_direction =
   1.570796 (path_plan.c:212-218), i.e. all four wheels at 90 deg to the
   chassis.  That is the only shape that makes this vehicle travel toward
   the tool side -- the author's "1", which is the weeding direction
   (ledger Hw-30, 2026-10-21).  LEFT/RIGHT keep TELEOP_STEER_DEG.  Author
   ruling the same day: prove it in TELEOP first, AUTO gets the offset next.
   The sign was settled by eye on 2026-10-26 on the RC path: lateral + throttle,
   no reverse button -> four wheels at ONE servo number and the body walking
   toward "3".  As of 10-27 the number is +90: the gear keeps the LOOK the RC
   lateral shows (four wheels right way round) and the SIDE the body walks comes
   from main.c negating all four wheel speeds in a crab posture.  Per wheel that
   is a 180 deg servo flip plus a drive flip, which cancels - the body rolls as
   the bench just saw it, only the tyres look different.  Same state the RC reaches
   with lateral + reverse button (path_plan.c:721-731 puts -velocity on all four).
   Neither the look nor the side has been re-watched on this build. */
#define TELEOP_LATERAL_DEG  +90.0   /* 10-27: the right-way-round look; the walked side is set by the flipped speeds */
/* STATUS has no spare byte, so the accepted gear is echoed through the
   current_a placeholder (adc_current_a() returns 0.0f; Fw-5 TODO).  THE A FIELD
   IS NOT AMPS WHILE THIS IS 1.  Same borrowed-slot trick as the Hw-17 battery_v
   probe; set to 0 and rebuild to give the slot back. */
#define RETRO_REPORT_TELEOP_GEAR 1
#define RETRO_TELEOP_MAX 0.2f
/* AUTO crab (2026-10-22, ledger Hw-30).  The vendor's "straight ahead" zero
   physically points at the author's "2" (vehicle left), while weeding travels
   toward "1" -- the side the knives hang on.  The vendor's own lateral mode
   is exactly this offset: path_plan.c:212-218 writes Switch_direction =
   1.570796 rad = 90 deg and main.c adds it to all four wheels with per-side
   signs, so all four stay parallel and the chassis shifts sideways.
   Fw-11 zeroed that sum in AUTO/TELEOP (correctly, so the RC cannot steer an
   unmanned vehicle); the replacement is a PC-supplied trim on top of a
   compile-time base, not the RC switch.
   Sign story = three bench looks, none of them a derivation: on 10-24 this base
   at +90 walked toward "3"; on 10-26 the RC lateral at +90 (vendor forward
   pairing) walked toward "3" too; on 10-27 the -90 base with the same pairing
   turned all four wheels reversed and the author asked to make them right.  So
   the base is +90 again and the walked side rides on the four flipped wheel
   speeds in main.c - lateral + reverse button, written into the firmware.  What
   has NOT been re-watched here: whether the wheels read right way round, and
   which side the body walks. */
#define AUTO_CRAB_BASE_DEG  +90.0   /* 10-27: the RC lateral LOOK; direction from the flipped speeds */
/* How far the PC may bend that base per frame.  15 deg is an envelope, not a
   tuned gain: the trim law itself is not wired yet (pc/main.py still steers
   AUTO differentially), this only opens the channel. */
#define AUTO_CRAB_TRIM_MAX   15.0
/* The 90 degrees and the wheel speeds are PAIRED.  The author's question "then why can the RC
   do it with all four wheels the same way?" found the missing half on 2026-10-26: the vendor's
   lateral mode does TWO things - Switch_direction = +90 reaches all four servos with the same
   sign (path_plan.c:212-218 + the four send_angle calls), and path_plan.c:548-555 immediately
   remaps the wheel speeds so entries 0 and 3 of veloc[] carry the opposite sign to
   entries 1 and 2.  Which physical wheel that is has been corrected twice (see the
   numbering doc), so this note stays index-level; the vendor's own comment at :548
   adds that which wheels are grouped is a per-model PCB wiring question.
   Both half-measures were run on the bench today and both were wrong: same-sign servos with
   un-paired speeds fought side against side; opposite-sign servos with un-paired speeds walk
   fine but two wheels look mirrored back.  That forward pairing is the reference the
   drive block below, taken verbatim, cross-assignment included: the negated wheels
   number - invisible while vl == vr, a different wheel speed under differential.  Copy
   rather than paraphrase, because the whole route (planner signs, this offset, DIR_SWAP,
   pwm_veloc) is the one the author has watched work with the RC in the lateral position.
   10-27: the sign below is +90 (four wheels right way round, the RC lateral look)
   and ALL FOUR wheel speeds are negated against that forward pattern - per wheel a
   servo flip plus a drive flip cancels, so the body keeps rolling the way the -90
   build rolled it; only the look changed.  That is the RC's reverse button on the
   lateral, done in firmware.  Ledger Hw-30. */

/* ---- MODE.request (must equal common/protocol.py) ---- */
#define MODE_REQ_MANUAL       0x00
#define MODE_REQ_AUTO         0x01
#define MODE_REQ_TELEOP       0x02
#define MODE_REQ_CLEAR_ESTOP  0x10
#define MODE_REQ_PROFILE      0x20

/* 新实车工程（样机，2026-11-05）：从"大车proj（上代车）"整份复制而来，故意不共用一份代码——
   两车的硬件差异（轮 4 舵机镜像安装，台账 Hw-34）落在 USER/main.c 的符号上，
   共用一份就要靠编译宏来回切，容易烧错车。本工程带轮 4 修正；上代车那份保持逐字节不变。 */
/* ---- vehicle profile: burned in, handshake compares against the PC yaml ---- */
#define PROFILE_PREV 1     /* previous vehicle, 3.25 m */
#define PROFILE_REAL 2     /* prototype, 2.15 m */
#define PROFILE_ID   PROFILE_REAL   /* change vehicle = edit this line + rebuild; never hot-switched at run time */

/* ---- entry permit (A5): compile-time constant, NEVER sent by the PC ---- */
#define PERMIT_GATE_N 1    /* gate N: run along the row only, knives forced up, no
                              * LATERAL SLIDE travel -- "lateral" here is the middle
                              * tool offset (tool_offset_mm), NOT the chassis.  The
                              * four shared wheel angles are a different axis entirely
                              * (ledger Hw-30, corrected 2026-10-21 after this comment
                              * was read as "AUTO may not crab"). */
#define PERMIT_GATE_F 2    /* gate F: knives may drop and lateral travel is allowed */
#define ENTRY_PERMIT  PERMIT_GATE_N

/* ---- who may drive right now (firmware-internal, not on the wire) ---- */
#define OWNER_RC   0
#define OWNER_PC   1
#define OWNER_NONE 2

/* ---- STATUS.authority = reason of the last authority transition ---- */
#define AUTH_BOOT              0
#define AUTH_PC_GRANTED        1
#define AUTH_FIELD_TAKEOVER    2   /* reserved number; this firmware never reports it */
#define AUTH_RCS_LOST          3
#define AUTH_LINK_LOST_ESTOP   4
#define AUTH_PC_CLEAR_ESTOP    5
#define AUTH_PC_RELEASE        6
#define AUTH_HEARTBEAT_RELEASE 7

/* ---- STATUS.reject (short REJ_* here, REJECT_* in common/protocol.py, same values) ---- */
#define REJ_NONE          0
#define REJ_PROFILE       1
#define REJ_RCS_STALE     2
#define REJ_FIELD_SWITCH  3   /* reserved number; this firmware never reports it */
#define REJ_ESTOP_LATCHED 4
#define REJ_LOOP_STALLED  5
#define REJ_NOT_IMPL      6
#define REJ_FIELD_LATCHED 7   /* reserved number; this firmware never reports it */
#define REJ_PERMIT        8
#define REJ_GEAR          9   /* NAV.flags held an unknown or locked gear */

/* ---- field takeover switch (A4): 10-10 AUTHOR RULING, NOT WRITTEN ----
   The six FIELD_* macros (FIELD_CH, FIELD_SW_CALIBRATED, FIELD_ALLOW_HI,
   FIELD_MID_LO, FIELD_MID_HI, FIELD_LATCH_MS) are deliberately NOT added to
   this header: entry to unmanned mode no longer requires a field lever
   (spec 4.2 condition 3 and spec 4.3 were revoked on 10-10), and a macro that
   takes no part in the decision would be dead code.
   REJ_FIELD_SWITCH(3) / REJ_FIELD_LATCHED(7) / AUTH_FIELD_TAKEOVER(2) above
   keep their numbers, because common/protocol.py and pc/wire.py already carry
   them on the mainline.  Their meaning here is "reserved by the protocol,
   never produced by this firmware".  Do not renumber, do not reuse.
   The design shape (channel, three thresholds, latch + >=1 s debounce) is
   archived in the batch 1a plan, Task 2 / Task 3 Step 2, if gate F ever needs
   a field takeover again. */

/* ---- execution-plane liveness (A12a / Fw-21) ---- */
#define LOOP_STALL_FRAMES 5   /* 5 STATUS periods (250 ms) with no change; equals STALL_FRAMES in pc/status_rx.py */

/* ---- E3 API (implemented in retrofit.c by batch 1a Tasks 3-5) ---- */
void retrofit_on_mode_frame(const uint8_t *payload, uint16_t len);
void retrofit_notify_loop(void);      /* call once per main-loop iteration */
uint8_t retrofit_owner(void);
uint8_t retrofit_reject(void);
uint8_t retrofit_permit(void);
uint8_t retrofit_profile(void);

void retrofit_init(void);          /* call once from main() after peripherals */
void retrofit_poll_1ms(void);      /* call from a 1 ms tick (SysTick or TIM) */
void retrofit_on_nav_frame(const uint8_t *payload, uint16_t len, uint16_t seq);
void retrofit_on_tool_frame(const uint8_t *payload, uint16_t len);
void retrofit_on_estop(void);      /* latched, needs manual clear */
void retrofit_clear_estop(void);   /* manual reset only (key/button path) */

/* mode getter for main loop / telemetry */
uint8_t retrofit_mode(void);
uint8_t retrofit_sbus_ok(void); /* H2.3: SBUS fresh within timeout? */
uint8_t retrofit_teleop_gear(void);  /* 2026-10-14: gear read by main.c */
double retrofit_auto_angle(void);
/* Crab posture: AUTO always, TELEOP only in the LATERAL gear. Everything that has to
   be "paired" (the servo offset AND the wheel-speed grouping) asks this one question,
   so the two halves can never disagree. Manual is never a crab posture. */
uint8_t retrofit_crab_posture(void);
/* The 90 degrees, on the SERVO side: main.c adds it to all four send_angle() calls
   with the SAME sign, exactly like the vendor's Switch_direction does in lateral mode
   (so no wheel looks mirrored back). Radians; 0.0 outside a crab posture. */
double retrofit_auto_offset(void);    /* 2026-10-21: AUTO base + PC trim, radians */
uint8_t retrofit_estop_latched(void);   /* 1 while ESTOP latched */


/* integration hooks */
void retrofit_notify_sbus(void);
void retrofit_get_wheel_cmd(float *vl, float *vr);
#endif
