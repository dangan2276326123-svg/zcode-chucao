#ifndef __CAN_H
#define __CAN_H	 
#include "sys.h"	    
//////////////////////////////////////////////////////////////////////////////////	 
//本程序只供学习使用，未经作者许可，不得用于其它任何用途
//ALIENTEK STM32F407开发板
//CAN驱动 代码	   
//正点原子@ALIENTEK
//技术论坛:www.openedv.com
//创建日期:2014/5/7
//版本：V1.0 
//版权所有，盗版必究。
//Copyright(C) 广州市星翼电子科技有限公司 2014-2024
//All rights reserved									  
////////////////////////////////////////////////////////////////////////////////// 	 
#define CAN1_RX0_INT_ENABLE	0		//0,不使能;1,使能.	
#define radian 57.296        //57.296
#define coefficient 10000        //57.296

#define   acceleration 0x01 //设置加速时间单位100ms
#define   deceleration 0x01//设置减速时间单位100ms
#define   delaytime 5 //发送一次数据延时时间
#define   turn 3000 //转速

#define   delayinittime 5 //发送一次数据延时时间

void send_place(double a);
//CAN1接收RX0中断使能
	void get(void);						    
void Place_mode_init(void);			    
u8 CAN1_Mode_Init(u8 tsjw,u8 tbs2,u8 tbs1,u16 brp,u8 mode);//CAN初始化
void test(void);
//u8 CAN1_Send_Msg(u8* msg,u8 len);						//发送数据

u8 CAN1_Send_Msg(u8* msg,u8 len,u32 id);
//void Set_Z(void);
void AD_Reset(void);
void send_place_AD(double a,double b,double c,double d);
void Send_Place(double h,double i,double j,double k);

void Place_LF_init(void);
void Place_LR_init(void);
void Place_RF_init(void);
void Place_RR_init(void);

u8 CAN1_Receive_Msg(u8 *buf);							//接收数据
#endif


































