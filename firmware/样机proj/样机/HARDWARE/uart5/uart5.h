#ifndef __UART5_H
#define __UART5_H
#include "stdio.h"	
#include "stm32f4xx_conf.h"
#include "sys.h" 

void uart5_init(u32 bound);
void UART5_Put_Char(u16 DataToSend);
void send_Operation_parameters(double speed,double voltage,double electric_current,double mileage);  //上传作业参数
void Recieve_Operation_parameters(void);  //接收作业参数
//extern u8 Usartsendflag;

void HMISends(char *buf1)		  ;

#endif


