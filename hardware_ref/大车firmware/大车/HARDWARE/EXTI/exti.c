#include "exti.h"
#include "delay.h" 
#include "led.h" 
#include "key.h"
#include "beep.h"
#include "usart.h"
#include "uart4.h"
//////////////////////////////////////////////////////////////////////////////////	 
//本程序只供学习使用，未经作者许可，不得用于其它任何用途
//ALIENTEK STM32F407开发板
//外部中断 驱动代码	   
//正点原子@ALIENTEK
//技术论坛:www.openedv.com
//创建日期:2014/5/4
//版本：V1.0
//版权所有，盗版必究。
//Copyright(C) 广州市星翼电子科技有限公司 2014-2024
//All rights reserved									  
////////////////////////////////////////////////////////////////////////////////// 

//外部中断0服务程序
//void EXTI0_IRQHandler(void)
//{
//	delay_ms(10);	//消抖
//	if(WK_UP==1)	 
//	{
//		BEEP=!BEEP; //蜂鸣器翻转 
//	}		 
//	 EXTI_ClearITPendingBit(EXTI_Line0); //清除LINE0上的中断标志位 
//}	
////外部中断2服务程序
//void EXTI2_IRQHandler(void)
//{
//	delay_ms(10);	//消抖
//	if(KEY2==0)	  
//	{				 
//   LED0=!LED0; 
//	}		 
//	 EXTI_ClearITPendingBit(EXTI_Line2);//清除LINE2上的中断标志位 
//}
////外部中断3服务程序
extern int delay_usr;

void EXTI3_IRQHandler(void)
{  static u8 flag_exti=0;
	
	delay_ms(1);	//消抖
	if(PFin(3)==1)	  //开启计时
	{
		TIM_Cmd(TIM7,ENABLE);
   // printf(" 11111111111111！\r\n");	

	}
	
		if(PFin(3)==0 )	  //开启计时
	{
		TIM_Cmd(TIM7,DISABLE);
 //    printf(" 2222222222222 %d \r\n",delay_usr);	
		
		//开始减速，设置为0.1ms
		
		
		
		//
		
		
		delay_usr=1;
	}

	
	

//	if(PFin(3)==0)	  //关闭计时
//  { 
//		
//		TIM_Cmd(TIM7,DISABLE);
//		printf(" 障 %d \r\n",delay_usr);	
//		delay_usr=0;

//	}
	
	 EXTI_ClearITPendingBit(EXTI_Line3);  //清除LINE3上的中断标志位  
}
////外部中断4服务程序
//void EXTI4_IRQHandler(void)
//{
//	delay_ms(10);	//消抖
//	if(KEY0==0)	 
//	{				 
//		LED0=!LED0;	

//	}		 
//	 EXTI_ClearITPendingBit(EXTI_Line4);//清除LINE4上的中断标志位  
//}
//	   
////外部中断初始化程序
////初始化PE2~4,PA0为中断输入.
	
void EXTIX_Init(void)
{
	NVIC_InitTypeDef   NVIC_InitStructure;
	EXTI_InitTypeDef   EXTI_InitStructure;
	GPIO_InitTypeDef  GPIO_InitStructure;
	
	//KEY_Init(); //按键对应的IO口初始化
	  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOF, ENABLE);//使能GPIOA,GPIOE时钟
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化
 
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_SYSCFG, ENABLE);//使能SYSCFG时钟
	

	SYSCFG_EXTILineConfig(EXTI_PortSourceGPIOF, EXTI_PinSource3);//PE3 连接到中断线3

	

	
	/* 配置EXTI_Line2,3,4 */
	EXTI_InitStructure.EXTI_Line = EXTI_Line3 ;
  EXTI_InitStructure.EXTI_Mode = EXTI_Mode_Interrupt;//中断事件
  EXTI_InitStructure.EXTI_Trigger = EXTI_Trigger_Rising_Falling; //下降沿触发
  EXTI_InitStructure.EXTI_LineCmd = ENABLE;//中断线使能
  EXTI_Init(&EXTI_InitStructure);//配置
 

	
	
	NVIC_InitStructure.NVIC_IRQChannel = EXTI3_IRQn;//外部中断3
  NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0x02;//抢占优先级2
  NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0x02;//子优先级2
  NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;//使能外部中断通道
  NVIC_Init(&NVIC_InitStructure);//配置
	

	   
}