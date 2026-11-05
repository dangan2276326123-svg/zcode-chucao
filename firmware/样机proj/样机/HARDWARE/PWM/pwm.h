#ifndef _TIMER_H
#define _TIMER_H
#include "sys.h"
#include "stm32f4xx.h"
//////////////////////////////////////////////////////////////////////////////////	 
//本程序只供学习使用，未经作者许可，不得用于其它任何用途
//ALIENTEK STM32F407开发板
//定时器 驱动代码	   
//正点原子@ALIENTEK
//技术论坛:www.openedv.com
//创建日期:2014/6/16
//版本：V1.0
//版权所有，盗版必究。
//Copyright(C) 广州市星翼电子科技有限公司 2014-2024
//All rights reserved									  
////////////////////////////////////////////////////////////////////////////////// 	


#define M1_dead_voltage_erro                60 //定义电机1.2.3.4的死区电压起步值50
#define M1_dead_voltage_erro_max             148  //185  //定义电机1.2.3.4的最大死区电压起步值 4.2V  对应着210？？？？？

//#define M2_dead_voltage_erro               80   //定义电机2的死区电压起步值
//#define M3_dead_voltage_erro               80   //定义电机3的死区电压起步值
//#define M4_dead_voltage_erro               80   //定义电机4的死区电压起步值


#define start_pwm               10    //定义电机的电压起步值，保证计算安全 小于这个比较值就不赋行走p波   相当于自己在软件 上设置了一个死区

//void TIM14_PWM_Init(u32 arr,u32 psc);
void TIM1_PWM_Init(u32 arr,u32 psc);
//void TIM2_PWM_Init(u32 arr,u32 psc);
//void TIM5_PWM_Init(u32 arr,u32 psc);

void BigRelayPWM_Init(u32 arr,u32 psc);
	
// void TIM9_PWM_Init(u16 arr,u16 psc);

void test_Init(void);
void Rolling_Control_Init(void);
void Strains_Control_Init(void);

//void TIM10_CH1_Cap_Init(u16 arr,u16 psc);
//void TIM11_CH1_Cap_Init(u16 arr,u16 psc);
//void TIM3_CH1_Cap_Init(u16 arr,u16 psc);
//void TIM13_CH1_Cap_Init(u16 arr,u16 psc);
//void TIM14_CH1_Cap_Init(u16 arr,u16 psc);

#define Roll_Brake_1   PGout(5)
#define Roll_Brake_2   PGout(6)
#define Roll_Brake_3   PGout(7)
#define Roll_Brake_4   PGout(8)

void Test_Driving(void);
void Motor_Init(u16 arr_b,u16 psc_b);
void Ch_Cap(void);
void Rolling_Brake(int a_1,int a_2,int a_3,int a_4);


void pwm_veloc(u8 adress,double veloc);

void Encoder1_TIM4_init(void); //实际的左侧车轮编码器
void Encoder1_TIM1_init(void);//实际的右侧车轮编码器
int TIM1_Encoder_Read(void);

#endif
