#ifndef __IIC_H
#define __IIC_H
#include "sys.h" 
//////////////////////////////////////////////////////////////////////////////////	 
//本程序只供学习使用，未经作者许可，不得用于其它任何用途
//ALIENTEK STM32F407开发板
//IIC 驱动代码	   
//正点原子@ALIENTEK
//技术论坛:www.openedv.com
//创建日期:2014/5/6
//版本：V1.0
//版权所有，盗版必究。
//Copyright(C) 广州市星翼电子科技有限公司 2014-2024
//All rights reserved									  
////////////////////////////////////////////////////////////////////////////////// 	
//IO方向设置
#define IIC_1_SDA_IN()  {GPIOB->MODER&=~(3<<(9*2));GPIOB->MODER|=0<<9*2;}        //
#define IIC_1_SDA_OUT() {GPIOB->MODER&=~(3<<(9*2));GPIOB->MODER|=1<<9*2;} //
//IO操作函数         
#define IIC_1_SCL    PBout(8) //SCL
#define IIC_1_SDA    PBout(9) //SDA         
#define IIC_1_READ_SDA   PBin(9)  //输入SDA

//IO方向设置
#define IIC_2_SDA_IN()  {GPIOB->MODER&=~(3<<(5*2));GPIOB->MODER|=0<<5*2;}        //
#define IIC_2_SDA_OUT() {GPIOB->MODER&=~(3<<(5*2));GPIOB->MODER|=1<<5*2;} //
//IO操作函数         
#define IIC_2_SCL    PBout(10) //SCL
#define IIC_2_SDA    PBout(11) //SDA         
#define IIC_2_READ_SDA   PBin(11)  //输入SDA

//IIC所有操作函数
void IIC_1_Init(void);                //初始化IIC的IO口                                 
void IIC_1_Start(void);                                //发送IIC开始信号
void IIC_1_Stop(void);                                  //发送IIC停止信号
void IIC_1_Send_Byte(u8 txd);                        //IIC发送一个字节
u8 IIC_1_Read_Byte(unsigned char ack);//IIC读取一个字节
u8 IIC_1_Wait_Ack(void);                                 //IIC等待ACK信号
void IIC_1_Ack(void);                                        //IIC发送ACK信号
void IIC_1_NAck(void);                                //IIC不发送ACK信号
void ADS_angle_Read(void);

///////////////////////////
void IIC_2_Init(void);                //初始化IIC的IO口                                 
void IIC_2_Start(void);                                //发送IIC开始信号
void IIC_2_Stop(void);                                  //发送IIC停止信号
void IIC_2_Send_Byte(u8 txd);                        //IIC发送一个字节
u8 IIC_2_Read_Byte(unsigned char ack);//IIC读取一个字节
u8 IIC_2_Wait_Ack(void);                                 //IIC等待ACK信号
void IIC_2_Ack(void);                                        //IIC发送ACK信号
void IIC_2_NAck(void);                                //IIC不发送ACK信号
void ADS_2_Read(void);

void ADC_angle_Check(void);
void ADC_electric_Check(void);
#endif

