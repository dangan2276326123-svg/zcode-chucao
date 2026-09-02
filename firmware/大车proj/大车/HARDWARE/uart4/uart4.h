#ifndef __UART4_H
#define __UART4_H
#include "stdio.h"	
#include "stm32f4xx_conf.h"
#include "sys.h" 

void uart4_init(u32 bound);

//void send_Operation_parameters(double speed,double voltage,double electric_current,double mileage);  //上传作业参数
//void Recieve_Operation_parameters(void);  //接收作业参数

void UART4_Put_Char(unsigned char DataToSend);
//void TIM2_Init(void);

void mosbus_EN(u8 adress);
void motor_EN(u8 adress );
void send_angle(u8 adress,double angle);
void motor_speed(u8 adress,int speed );

void UartRxMonitor4(u8 ms); //串口接收监控
u8 Uart4Read(u8 *buf, u8 len) ;
void  work_send_control(u8 adress);
void  safei_work_send_control(void);
void  manua_control(u8 adress)   ;//手动 5，除草一 6，除草二 7，喷药 8 ，摇头一 9，摇头二 10 ，施肥 11
void TIM7_Init(void);
#endif


