#ifndef __CAR_CONTROL_H
#define __CAR_CONTROL_H
#include "sys.h"
void pid_init(void);//PID参数初始化 
//float pid_realise(float speed);//实现PID算法 

float pid_realise(float speed,double capture);
void Out_Pwm(void);
void Test_Out_Pwm(void);
#define Roll_LF_En   PCout(3)
#define Roll_LR_En   PCout(5)
#define Roll_RF_En   PCout(4)
#define Roll_RR_En   PGout(0)

#define Roll_LF_Dr   PGout(1)
#define Roll_LR_Dr   PGout(2)
#define Roll_RF_Dr   PGout(3)
#define Roll_RR_Dr   PGout(4)

#define Roll_PWM1   TIM8->CCR1
#define Roll_PWM2   TIM8->CCR2
#define Roll_PWM3   TIM8->CCR3
#define Roll_PWM4   TIM8->CCR4

#define Roll_LF_BK   PGout(5)
#define Roll_LR_BK   PGout(6)
#define Roll_RF_BK   PGout(7)
#define Roll_RR_BK   PGout(8)


////LED端口定义
//#define LED0 PFout(9)	// DS0
//#define LED1 PFout(10)	// DS1	 

//void LED_Init(void);//初始化		 				    
#endif
