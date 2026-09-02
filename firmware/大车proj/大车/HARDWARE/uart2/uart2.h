#ifndef __UART2_H
#define __UART2_H
#include "stdio.h"	
#include "stm32f4xx_conf.h"
#include "sys.h" 

void uart2_init(u32 bound);
void RS485_Send_Data(u8 *buf,u8 len);
void set_adresss();
void set_median(u8 address);
void read_encoder(u8 address);
void get_angle_encode();
void read_ultrasonic_1(u8 address);  //¶ÁÈ¡³¬Éù²¨1
void read_ultrasonic_234(u8 address);  //¶ÁÈ¡³¬Éù²¨234
void read_ultrasonic_1234(u8 address) ; //¶ÁÈ¡³¬Éù²¨234
#endif


