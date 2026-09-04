#include "retrofit.h"
#include "stm32f4xx_gpio.h"
#include "stm32f4xx_rcc.h"
#include "stm32f4xx_tim.h"
#include "stm32f4xx_usart.h"
#include "stm32f4xx_iwdg.h"
#include <string.h>

/* ---------------- pin map (v0.7 s13.2) ----------------
   USART6: PC6 TX / PC7 RX, 115200 8N1, link to Raspberry Pi
   knife relays x3: PD4 PD5 PD6 (through 74HC245, active high)
   middle tool stepper: PULSE=PB6 (TIM4_CH1 AF2) DIR=PB5 EN=PB7
   limit switches: PD15 (origin) PD10 (left) PD11 (right), pull-up, active low
   wheel speed capture: TIM3 CH1-4 = PA6 PA7 PB0 PB1
--------------------------------------------------------- */

#define LINK_TIMEOUT_MS   500   /* no PC frame -> estop */
#define STEPPER_PULSE_HZ  2000  /* max pulse rate */
#define STEPPER_STEPS_PER_MM 25.0f  /* 8mm lead / 200 steps * microstep 16 -> 400/mm; tune on bench */

/* ---------- state ---------- */
static uint8_t  mode = MODE_MANUAL;
static uint8_t  estop_latched = 0;
static volatile uint32_t tick_ms = 0;
static volatile uint32_t last_pc_ms = 0;    /* last nav/heartbeat from PC */
static volatile uint32_t sbus_last_ms = 0;  /* updated by telecontrol.c on SBUS RX */
static uint16_t tx_seq = 0;

/* latest commands */
static float cmd_vl, cmd_vr;        /* AUTO target wheel speeds m/s */
static float tool_offset_mm;        /* middle slide target */
static uint8_t lift_bits;           /* bit0..2 = beams 1..3 raised */
static volatile uint32_t last_tool_ms = 0;

/* wheel speed (TIM3 capture) */
static volatile uint32_t cap_period[4] = {0,0,0,0};
static volatile uint32_t cap_edge_ms[4] = {0,0,0,0};
static float wheel_speed_mps[4];    /* estimated per wheel */

/* ---------------- small helpers ---------------- */
static uint32_t ms(void) { return tick_ms; }

static void gpio_out(GPIO_TypeDef *port, uint16_t pin, uint8_t on)
{
    if (on) GPIO_SetBits(port, pin);
    else GPIO_ResetBits(port, pin);
}

/* ---------------- UART6 link ---------------- */
static uint8_t rx_byte;
static prot_frame_t rx_frame;

void USART6_IRQHandler(void)
{
    if (USART_GetITStatus(USART6, USART_IT_RXNE) != RESET) {
        rx_byte = (uint8_t)USART_ReceiveData(USART6);
        if (prot_parse_byte(rx_byte, &rx_frame)) {
            last_pc_ms = ms();
            switch (rx_frame.type) {
            case TYPE_NAV:
                retrofit_on_nav_frame(rx_frame.payload, rx_frame.payload_len, rx_frame.seq);
                break;
            case TYPE_TOOL:
                retrofit_on_tool_frame(rx_frame.payload, rx_frame.payload_len);
                break;
            case TYPE_ESTOP:
                retrofit_on_estop();
                break;
            case TYPE_HEARTBEAT:
            default:
                break;  /* heartbeat just refreshes watchdog via last_pc_ms */
            }
        }
    }
}

static void uart6_send(const uint8_t *data, uint16_t len)
{
    uint16_t i;
    for (i = 0; i < len; i++) {
        while (USART_GetFlagStatus(USART6, USART_FLAG_TXE) == RESET);
        USART_SendData(USART6, data[i]);
    }
}

/* ---------------- protocol dispatch (called from parser) ---------------- */
void retrofit_on_nav_frame(const uint8_t *payload, uint16_t len, uint16_t seq)
{
    (void)seq;
    if (len < 9 || estop_latched || mode == MODE_MANUAL) return;
    /* payload: vL f32le, vR f32le, flags u8 */
    memcpy(&cmd_vl, &payload[0], 4);
    memcpy(&cmd_vr, &payload[4], 4);
    /* guard: sane range only */
    if (cmd_vl < -1.0f) cmd_vl = -1.0f;
    if (cmd_vl >  1.0f) cmd_vl =  1.0f;
    if (cmd_vr < -1.0f) cmd_vr = -1.0f;
    if (cmd_vr >  1.0f) cmd_vr =  1.0f;
    mode = MODE_AUTO;
}

void retrofit_on_tool_frame(const uint8_t *payload, uint16_t len)
{
    if (len < 5 || estop_latched) return;
    last_tool_ms = tick_ms;
    memcpy(&tool_offset_mm, &payload[0], 4);
    lift_bits = payload[4];
    if (tool_offset_mm >  50.0f) tool_offset_mm =  50.0f;
    if (tool_offset_mm < -50.0f) tool_offset_mm = -50.0f;
}

void retrofit_on_estop(void)
{
    estop_latched = 1;
    mode = MODE_ESTOP;
    cmd_vl = cmd_vr = 0.0f;
    tool_offset_mm = 0.0f;
    lift_bits = 0x07;             /* all beams up */
}

void retrofit_clear_estop(void)
{
    estop_latched = 0;
    mode = MODE_MANUAL;
    lift_bits = 0;
}

/* F2 note: the independent hardware watchdog is the board's existing
   IWDG (main.c: IWDG_Init(4,500) ~= 1 s, fed in the main loop).  A second
   IWDG instance is not possible on the same peripheral; retrofit coverage
   comes from the fact that any retrofit/TIM6 lock-up also stops the main
   loop's feeding and triggers that reset. */

/* ---------------- F1: command slew-rate limiter ----------------
   AUTO/MANUAL and estop transitions are step changes; the limiter bounds
   wheel-speed slew at SLEW_ACC so the chassis never jumps. */
#define SLEW_ACC 0.2f   /* m/s per second */

static float out_vl = 0.0f, out_vr = 0.0f;

static void slew_step(void)
{
    float target_l = estop_latched ? 0.0f : cmd_vl;
    float target_r = estop_latched ? 0.0f : cmd_vr;
    float max_d = SLEW_ACC * 0.001f;   /* per 1 ms tick */
    float dl = target_l - out_vl;
    float dr = target_r - out_vr;
    if (dl >  max_d) dl =  max_d;
    if (dl < -max_d) dl = -max_d;
    if (dr >  max_d) dr =  max_d;
    if (dr < -max_d) dr = -max_d;
    out_vl += dl;
    out_vr += dr;
}

uint8_t retrofit_mode(void)
{
    return mode;
}

void retrofit_get_wheel_cmd(float *vl, float *vr)
{
    *vl = out_vl;
    *vr = out_vr;
}

/* ---------------- wheel speed: TIM3 4-channel capture ---------------- */
static void wheel_speed_update(void)
{
    /* period ticks between rising edges at 1 MHz timer clock;
       wheel circumference C meters, N pulses/rev -> v = C/(N*T) */
    const float c_per_pulse = 0.0005f;  /* meters per pulse — calibrate on bench */
    int i;
    for (i = 0; i < 4; i++) {
        uint32_t p = cap_period[i];
        if (p == 0 || (uint32_t)(ms() - cap_edge_ms[i]) > 300) {
            wheel_speed_mps[i] = 0.0f;  /* no pulses in 300 ms -> stopped */
        } else {
            wheel_speed_mps[i] = c_per_pulse * 1000000.0f / p;
        }
    }
}

float retrofit_wheel_speed(void)  /* average magnitude, m/s */
{
    float s = (wheel_speed_mps[0] + wheel_speed_mps[1] +
               wheel_speed_mps[2] + wheel_speed_mps[3]) * 0.25f;
    return s < 0 ? -s : s;
}

/* ---------------- status frame 0x10 @ 20 Hz ---------------- */
static float adc_current_a(void)  /* TODO bench: wire to iic.c ADS1115 AD5 */
{
    return 0.0f;
}

static uint8_t read_limits(void)
{
    /* PD15 origin, PD10 left, PD11 right; active low with pull-up */
    uint8_t v = 0;
    if (!GPIO_ReadInputDataBit(GPIOD, GPIO_Pin_15)) v |= 0x01;
    if (!GPIO_ReadInputDataBit(GPIOD, GPIO_Pin_10)) v |= 0x02;
    if (!GPIO_ReadInputDataBit(GPIOD, GPIO_Pin_11)) v |= 0x04;
    return v;
}

static void status_report(void)
{
    uint8_t pl[14];
    uint8_t frame[2 + 5 + 14 + 2];
    float speed = retrofit_wheel_speed();
    float cur = adc_current_a();
    float bat = 48.0f;  /* TODO: ADC divider channel */
    memcpy(&pl[0], &speed, 4);
    memcpy(&pl[4], &cur, 4);
    memcpy(&pl[8], &bat, 4);
    pl[12] = read_limits();
    pl[13] = mode;
    {
        uint16_t n = prot_build(TYPE_STATUS, tx_seq++, pl, sizeof(pl), frame);
        uart6_send(frame, n);
    }
}

/* ---------------- actuation outputs ---------------- */
static void apply_outputs(void)
{
    uint8_t auto_active = (mode == MODE_AUTO) && !estop_latched;
    uint8_t i;

    /* knife relays PD4/5/6: in AUTO commanded by lift_bits (1=up);
       in MANUAL all follow lift request but relays default released;
       ESTOP forces all up (open relay = beam raised) */
    /* MANUAL default-safe: a manual tool command is only honoured within
       500 ms of the last TOOL frame; otherwise knives stay UP. */
    uint8_t tool_cmd_fresh =
        (uint32_t)(tick_ms - last_tool_ms) < 500;
    for (i = 0; i < 3; i++) {
        uint8_t up;
        if (estop_latched) up = 1;
        else if (auto_active) up = (lift_bits >> i) & 1;
        else up = tool_cmd_fresh ? (lift_bits >> i) & 1 : 1;
        gpio_out(GPIOD, (uint16_t)(GPIO_Pin_4 << i), up);
    }

    /* chassis: in AUTO the mapped speeds are applied by the existing
       Out_Pwm() path via veloc[]; we only write the shared command vars
       that a small patch in car_control.c consumes (see integration notes).
       In MANUAL the SBUS path keeps control. No writes here. */
}

/* ---------------- middle tool stepper (TIM4 CH1 PWM pulse train) ---- */
static void stepper_update(void)
{
    static float applied_mm = 0.0f;
    float err_mm = tool_offset_mm - applied_mm;
    float hz;
    uint16_t arr;
    uint8_t lim_origin, lim_left, lim_right;
    lim_origin = GPIO_ReadInputDataBit(GPIOD, GPIO_Pin_15);
    lim_left  = GPIO_ReadInputDataBit(GPIOD, GPIO_Pin_10);
    lim_right = GPIO_ReadInputDataBit(GPIOD, GPIO_Pin_11);
    /* active-low switches: 0 = hit.  Block motion that would drive INTO a hit */
    if (lim_left == 0 && err_mm > 0) err_mm = 0.0f;
    if (lim_right == 0 && err_mm < 0) err_mm = 0.0f;
    if (lim_origin == 0) err_mm = 0.0f;   /* origin: hold position */
    if (!estop_latched && err_mm != 0.0f) {
        /* direction: positive offset -> DIR high */
        gpio_out(GPIOB, GPIO_Pin_5, err_mm > 0);
        /* pulse frequency proportional to |err|, capped */
        hz = err_mm * STEPPER_STEPS_PER_MM * 20.0f; /* 20 mm/s max */
        if (hz < 0) hz = -hz;
        if (hz > STEPPER_PULSE_HZ) hz = STEPPER_PULSE_HZ;
        if (hz < 50.0f) hz = 50.0f;
        arr = (uint16_t)(1000000.0f / hz) - 1;   /* timer clk 1 MHz */
        TIM_SetAutoreload(TIM4, arr);
        TIM_SetCompare1(TIM4, arr / 2);
        TIM_Cmd(TIM4, ENABLE);
        applied_mm += (err_mm > 0 ? 1 : -1) *
                      (hz / STEPPER_STEPS_PER_MM) * 0.001f; /* ms tick */
        if ((err_mm > 0 && applied_mm > tool_offset_mm) ||
            (err_mm < 0 && applied_mm < tool_offset_mm))
            applied_mm = tool_offset_mm;
    } else {
        TIM_Cmd(TIM4, DISABLE);
        if (estop_latched) applied_mm = 0.0f;
    }
}

/* ---------------- 1 ms tick ---------------- */
void retrofit_poll_1ms(void)
{
    tick_ms++;

    /* link watchdog: in AUTO, no PC frame for 500 ms -> estop */
    if (mode == MODE_AUTO && !estop_latched &&
        (uint32_t)(tick_ms - last_pc_ms) > LINK_TIMEOUT_MS) {
        retrofit_on_estop();
    }

    /* SBUS heartbeat: telecontrol sets sbus_last_ms on valid frame;
      遥控断链在 MANUAL 下也照常，不自动切 AUTO（安全默认为手动） */

    slew_step();
    wheel_speed_update();
    apply_outputs();
    stepper_update();

    if ((tick_ms % 50) == 0) status_report();   /* 20 Hz */
}

/* ---------------- init ---------------- */
static void tim6_1ms_init(void);
void retrofit_init(void)
{
    GPIO_InitTypeDef g;
    USART_InitTypeDef u;
    NVIC_InitTypeDef n;
    TIM_TimeBaseInitTypeDef tb;
    TIM_OCInitTypeDef oc;

    RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA | RCC_AHB1Periph_GPIOB | RCC_AHB1Periph_GPIOC | RCC_AHB1Periph_GPIOD, ENABLE);
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM4 | RCC_APB1Periph_TIM3, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART6, ENABLE);

    /* outputs: PD4/5/6 relays, PB5 dir, PB7 enable(1) */
    g.GPIO_Mode = GPIO_Mode_OUT;
    g.GPIO_OType = GPIO_OType_PP;
    g.GPIO_Speed = GPIO_Speed_2MHz;
    g.GPIO_PuPd = GPIO_PuPd_NOPULL;
    g.GPIO_Pin = GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_6;
    GPIO_Init(GPIOD, &g);
    g.GPIO_Pin = GPIO_Pin_5 | GPIO_Pin_7;
    GPIO_Init(GPIOB, &g);
    gpio_out(GPIOB, GPIO_Pin_7, 1);  /* stepper enabled */

    /* inputs: PD15/PD10/PD11 limits, pull-up */
    g.GPIO_Mode = GPIO_Mode_IN;
    g.GPIO_PuPd = GPIO_PuPd_UP;
    g.GPIO_Pin = GPIO_Pin_15 | GPIO_Pin_10 | GPIO_Pin_11;
    GPIO_Init(GPIOD, &g);

    /* USART6 PC6/PC7 AF8 */
    g.GPIO_Mode = GPIO_Mode_AF;
    g.GPIO_OType = GPIO_OType_PP;
    g.GPIO_PuPd = GPIO_PuPd_UP;
    g.GPIO_Pin = GPIO_Pin_6 | GPIO_Pin_7;
    GPIO_Init(GPIOC, &g);
    GPIO_PinAFConfig(GPIOC, GPIO_PinSource6, GPIO_AF_USART6);
    GPIO_PinAFConfig(GPIOC, GPIO_PinSource7, GPIO_AF_USART6);
    u.USART_BaudRate = 115200;
    u.USART_WordLength = USART_WordLength_8b;
    u.USART_StopBits = USART_StopBits_1;
    u.USART_Parity = USART_Parity_No;
    u.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    u.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART6, &u);
    USART_ITConfig(USART6, USART_IT_RXNE, ENABLE);
    USART_Cmd(USART6, ENABLE);
    n.NVIC_IRQChannel = USART6_IRQn;
    n.NVIC_IRQChannelPreemptionPriority = 2;
    n.NVIC_IRQChannelSubPriority = 0;
    n.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&n);

    /* TIM4 CH1 on PB6 AF2: 1 MHz timebase, PWM pulse train for stepper */
    g.GPIO_Pin = GPIO_Pin_6;
    GPIO_Init(GPIOB, &g);
    GPIO_PinAFConfig(GPIOB, GPIO_PinSource6, GPIO_AF_TIM4);
    tb.TIM_Prescaler = 84 - 1;      /* APB1*2 = 84 MHz -> 1 MHz */
    tb.TIM_Period = 999;
    tb.TIM_ClockDivision = TIM_CKD_DIV1;
    tb.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM4, &tb);
    oc.TIM_OCMode = TIM_OCMode_PWM1;
    oc.TIM_OutputState = TIM_OutputState_Enable;
    oc.TIM_Pulse = 500;
    TIM_OC1Init(TIM4, &oc);
    TIM_OC1PreloadConfig(TIM4, TIM_OCPreload_Enable);
    TIM_ARRPreloadConfig(TIM4, ENABLE);

    /* TIM3 4-channel input capture 1 MHz (wheel speed) — restores the
       commented capture block in pwm.c on PA6/PA7/PB0/PB1 with AF2 */
    g.GPIO_Pin = GPIO_Pin_6 | GPIO_Pin_7;
    g.GPIO_PuPd = GPIO_PuPd_NOPULL;
    GPIO_Init(GPIOA, &g);           /* PA6/PA7 */
    g.GPIO_Pin = GPIO_Pin_0 | GPIO_Pin_1;
    GPIO_Init(GPIOB, &g);           /* PB0/PB1 */
    GPIO_PinAFConfig(GPIOA, GPIO_PinSource6, GPIO_AF_TIM3);
    GPIO_PinAFConfig(GPIOA, GPIO_PinSource7, GPIO_AF_TIM3);
    GPIO_PinAFConfig(GPIOB, GPIO_PinSource0, GPIO_AF_TIM3);
    GPIO_PinAFConfig(GPIOB, GPIO_PinSource1, GPIO_AF_TIM3);
    tb.TIM_Prescaler = 84 - 1;      /* 1 MHz */
    tb.TIM_Period = 0xFFFF;
    TIM_TimeBaseInit(TIM3, &tb);
    {
        TIM_ICInitTypeDef ic;
        uint16_t ch;
        ic.TIM_ICPolarity = TIM_ICPolarity_Rising;
        ic.TIM_ICSelection = TIM_ICSelection_DirectTI;
        ic.TIM_ICPrescaler = TIM_ICPSC_DIV1;
        ic.TIM_ICFilter = 0x0;
        for (ch = 1; ch <= 4; ch++) {
            ic.TIM_Channel = (uint16_t)(ch - 1) * 4; /* CH1=0x00..CH4=0x0C */
            TIM_ICInit(TIM3, &ic);
        }
        TIM_ITConfig(TIM3, TIM_IT_CC1 | TIM_IT_CC2 | TIM_IT_CC3 | TIM_IT_CC4, ENABLE);
    }
    TIM_Cmd(TIM3, ENABLE);
    n.NVIC_IRQChannel = TIM3_IRQn;
    n.NVIC_IRQChannelPreemptionPriority = 1;
    n.NVIC_IRQChannelSubPriority = 1;
    NVIC_Init(&n);

    tim6_1ms_init();
}

/* TIM3 capture ISR: measure high-resolution period between rising edges.
   Wired into the project by appending to stm32f4xx_it.c if absent. */
void TIM3_IRQHandler(void)
{
    static uint16_t last[4] = {0,0,0,0};
    if (TIM_GetITStatus(TIM3, TIM_IT_CC1) != RESET) {
        uint16_t now = TIM_GetCapture1(TIM3);
        cap_period[0] = (uint16_t)(now - last[0]);
        cap_edge_ms[0] = tick_ms;
        last[0] = now;
        TIM_ClearITPendingBit(TIM3, TIM_IT_CC1);
    }
    if (TIM_GetITStatus(TIM3, TIM_IT_CC2) != RESET) {
        uint16_t now = TIM_GetCapture2(TIM3);
        cap_period[1] = (uint16_t)(now - last[1]);
        cap_edge_ms[1] = tick_ms;
        last[1] = now;
        TIM_ClearITPendingBit(TIM3, TIM_IT_CC2);
    }
    if (TIM_GetITStatus(TIM3, TIM_IT_CC3) != RESET) {
        uint16_t now = TIM_GetCapture3(TIM3);
        cap_period[2] = (uint16_t)(now - last[2]);
        cap_edge_ms[2] = tick_ms;
        last[2] = now;
        TIM_ClearITPendingBit(TIM3, TIM_IT_CC3);
    }
    if (TIM_GetITStatus(TIM3, TIM_IT_CC4) != RESET) {
        uint16_t now = TIM_GetCapture4(TIM3);
        cap_period[3] = (uint16_t)(now - last[3]);
        cap_edge_ms[3] = tick_ms;
        last[3] = now;
        TIM_ClearITPendingBit(TIM3, TIM_IT_CC4);
    }
}

/* ---------------- integration hooks (added at bring-up) ---------------- */

void retrofit_notify_sbus(void)   /* called by telecontrol.c on valid SBUS frame */
{
    sbus_last_ms = tick_ms;
}

/* TIM6: 1 ms tick source for retrofit_poll_1ms (TIM6 unused in project) */
static void tim6_1ms_init(void)
{
    TIM_TimeBaseInitTypeDef tb;
    NVIC_InitTypeDef n;
    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM6, ENABLE);
    tb.TIM_Prescaler = 84 - 1;          /* 84 MHz -> 1 MHz */
    tb.TIM_Period = 1000 - 1;           /* 1 kHz update */
    tb.TIM_ClockDivision = TIM_CKD_DIV1;
    tb.TIM_CounterMode = TIM_CounterMode_Up;
    TIM_TimeBaseInit(TIM6, &tb);
    TIM_SelectOutputTrigger(TIM6, TIM_TRGOSource_Update);
    TIM_ITConfig(TIM6, TIM_IT_Update, ENABLE);
    TIM_ClearFlag(TIM6, TIM_FLAG_Update);
    n.NVIC_IRQChannel = TIM6_DAC_IRQn;
    n.NVIC_IRQChannelPreemptionPriority = 3;
    n.NVIC_IRQChannelSubPriority = 0;
    n.NVIC_IRQChannelCmd = ENABLE;
    NVIC_Init(&n);
    TIM_Cmd(TIM6, ENABLE);
}

void TIM6_DAC_IRQHandler(void)
{
    if (TIM_GetITStatus(TIM6, TIM_IT_Update) != RESET) {
        TIM_ClearITPendingBit(TIM6, TIM_IT_Update);
        retrofit_poll_1ms();
    }
}
