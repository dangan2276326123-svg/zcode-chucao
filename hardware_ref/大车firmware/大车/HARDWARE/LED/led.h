#ifndef __LED_H
#define __LED_H
#include "sys.h"

//////////////////////////////////////////////////////////////////////////////////	 
//本程序只供学习使用，未经作者许可，不得用于其它任何用途
//ALIENTEK STM32F407开发板
//LED驱动代码	   
//正点原子@ALIENTEK
//技术论坛:www.openedv.com
//创建日期:2014/5/2
//版本：V1.0
//版权所有，盗版必究。
//Copyright(C) 广州市星翼电子科技有限公司 2014-2024
//All rights reserved									  
////////////////////////////////////////////////////////////////////////////////// 	


//LED端口定义
//PF9灯作用不明，原未使用，但主函数中有调用??????????
#define LED0 PFout(9)	// DS0   单片机自带

#define LED1 PCout(0)	// DS0    板子带


#define SW_Stop PAout(5)	// 刹车(PWM继电器)
//#define SW_1 PEout(6) 	// SW1

//此处示廓灯GPIO在.c文件中未初始化???????????????
#define Position_light PFout(8)	 // 示廓灯(原PE7)
#define SW_3 PFout(10) 	// SW3  
//预留输出
#define SW_reserv_CH1 PAout(11)	// 预留输出1
#define SW_reserv_CH2 PDout(3)	// 预留输出2
#define SW_reserv_CH3 PDout(4)	// 预留输出3
#define SW_reserv_CH4 PDout(5)	// 预留输出4
#define SW_reserv_CH5 PDout(6)	// 预留输出5
#define SW_reserv_CH6 PDout(7)	// 预留输出6
#define SW_reserv_CH7 PEout(4)	// 预留输出7
#define SW_reserv_CH8 PEout(5)	// 预留输出8

//预留输入
#define IN_reserv_CH1 PDin(15)	// 预留输入1
#define IN_reserv_CH2 PDin(14)	// 预留输入2
#define IN_reserv_CH3 PDin(13)	// 预留输入3
#define IN_reserv_CH4 PDin(12)	// 预留输入4
#define IN_reserv_CH5 PDin(11)	// 预留输入5
#define IN_reserv_CH6 PDin(10)	// 预留输入6
#define IN_reserv_CH7 PDin(9)	// 预留输入7
//#define IN_reserv_CH8 PFin(3)	// 预留输入8


///拨码器

#define Dial_switch_ch1   PFin(14)	// 拨码开关1   打在NO上是0
#define Dial_switch_ch2   PFin(13)	// 拨码开关2
#define Dial_switch_ch3   PFin(11)	// 拨码开关3

///音乐
#define MP3_IO_0   PGout(8)	// IO 0    1不唱
#define MP3_IO_1   PGout(7)	// IO 1    1不唱
#define MP3_IO_2   PGout(6)	// IO 2    1不唱
#define MP3_IO_3   PGout(5)	// IO 3    1不唱
#define MP3_IO_4   PGout(4)	// IO 3    1不唱
#define MP3_IO_5   PGout(3)	// IO 3    1不唱
//#define SHACHEFLAG PDin(14)	// DS0

void LED_Init(void);//初始化
void replay_switch_Init(void);//继电器初始化

void replay_switch(u8 ch,u8 replayswitch);//继电器开关
u8 Touch_detection(u8 flag );  // 触碰检测函数 返回9 说明没有任何触碰
void wheel_angle_limit_set(u8 flag);  //  转角有限幅的时候需要设置为限制值	

void select_flag_car_mode(void); ///进行模式选择 车辆模型。遥控器方式，通过拨码器进行设置

void mp3_control(u8 flag); //音乐播放控制
#endif
