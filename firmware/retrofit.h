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

void retrofit_init(void);          /* call once from main() after peripherals */
void retrofit_poll_1ms(void);      /* call from a 1 ms tick (SysTick or TIM) */
void retrofit_on_nav_frame(const uint8_t *payload, uint16_t len, uint16_t seq);
void retrofit_on_tool_frame(const uint8_t *payload, uint16_t len);
void retrofit_on_estop(void);      /* latched, needs manual clear */
void retrofit_clear_estop(void);   /* manual reset only (key/button path) */

/* mode getter for main loop / telemetry */
uint8_t retrofit_mode(void);

#endif
