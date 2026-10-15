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
   0 straight / 1 left / 2 right.  3 is RESERVED for lateral (crab) and stays
   refused: the crab angle needs the real track/wheelbase, and none of the four
   geometry constants in this firmware matches what was measured (ledger Hw-23),
   so shipping 45 deg now would scrub the tyres. */
#define TELEOP_GEAR_STRAIGHT 0
#define TELEOP_GEAR_LEFT     1
#define TELEOP_GEAR_RIGHT    2
#define TELEOP_GEAR_LATERAL  3   /* crab attempt: all four wheels same sign */
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
/* STATUS has no spare byte, so the accepted gear is echoed through the
   current_a placeholder (adc_current_a() returns 0.0f; Fw-5 TODO).  THE A FIELD
   IS NOT AMPS WHILE THIS IS 1.  Same borrowed-slot trick as the Hw-17 battery_v
   probe; set to 0 and rebuild to give the slot back. */
#define RETRO_REPORT_TELEOP_GEAR 1
#define RETRO_TELEOP_MAX 0.2f

/* ---- MODE.request (must equal common/protocol.py) ---- */
#define MODE_REQ_MANUAL       0x00
#define MODE_REQ_AUTO         0x01
#define MODE_REQ_TELEOP       0x02
#define MODE_REQ_CLEAR_ESTOP  0x10
#define MODE_REQ_PROFILE      0x20

/* ---- vehicle profile: burned in, handshake compares against the PC yaml ---- */
#define PROFILE_PREV 1     /* previous vehicle, 3.25 m */
#define PROFILE_REAL 2     /* prototype, 2.15 m */
#define PROFILE_ID   PROFILE_PREV   /* change vehicle = edit this line + rebuild; never hot-switched at run time */

/* ---- entry permit (A5): compile-time constant, NEVER sent by the PC ---- */
#define PERMIT_GATE_N 1    /* gate N: run along the row only, knives forced up, no lateral travel */
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
uint8_t retrofit_estop_latched(void);   /* 1 while ESTOP latched */


/* integration hooks */
void retrofit_notify_sbus(void);
void retrofit_get_wheel_cmd(float *vl, float *vr);
#endif
