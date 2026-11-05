#ifndef __TELECONTROL_H
#define __TELECONTROL_H
#include "sys.h"

//#include "usart.h"
//#include "sys.h"

//使用USART1时开启，不用可以注释
#define SBUS_DATA_LEN  35
extern u8 rec_sbus_data[SBUS_DATA_LEN];   // 接收数据
extern int sbus_channel[16];//解析后的通道数据
extern int sbus_filiter_channel[16];
extern void USART1_SBUS_Init(void);
extern void DMA2_S5_Reset(void);//DMA1_Stream6 接收重置	

void sbus_filter(u8 count_filiter);


extern u8 CHANGE_FLAG;
extern u8 LOCK_FLAG;
extern u8 HEIGHT_FIXED_FLAG;
extern u8 OPTICAL_FLOW_FLAG;

#endif

				    


