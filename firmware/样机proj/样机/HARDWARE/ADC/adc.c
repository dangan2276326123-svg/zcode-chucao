#include "adc.h"
#include "delay.h"
#include "path_plan.h"
//////////////////////////////////////////////////////////////////////////////////	 
//本程序只供学习使用，未经作者许可，不得用于其它任何用途
//ALIENTEK STM32F407开发板
//ADC 驱动代码	   
//正点原子@ALIENTEK
//技术论坛:www.openedv.com
//创建日期:2014/5/6
//版本：V1.0
//版权所有，盗版必究。
//Copyright(C) 广州市星翼电子科技有限公司 2014-2024
//All rights reserved									  
////////////////////////////////////////////////////////////////////////////////// 	
double AD_angle[4]={0,0,0,0};//四个轮子的采集值  0左前，1右前，2左后，3右后

////初始化ADC															   
//void  Adc_Init(void)
//{    
//  GPIO_InitTypeDef  GPIO_InitStructure;
//	GPIO_InitTypeDef  GPIO_InitStructuree;
//	ADC_CommonInitTypeDef ADC_CommonInitStructure;
//	ADC_InitTypeDef       ADC_InitStructure;
//	
//  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOF, ENABLE);//使能GPIOA时钟
//	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOC, ENABLE);
//  RCC_APB2PeriphClockCmd(RCC_APB2Periph_ADC3, ENABLE); //使能ADC3时钟

//  //先初始化ADC3通道5 IO口
//  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3|GPIO_Pin_4|GPIO_Pin_5|GPIO_Pin_7|GPIO_Pin_8;//PA5 通道5;//PA5 通道5
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AN;//模拟输入
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_NOPULL ;//不带上下拉
//  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化  
//	
//	  GPIO_InitStructuree.GPIO_Pin = GPIO_Pin_1;//PA5 通道5
//  GPIO_InitStructuree.GPIO_Mode = GPIO_Mode_AN;//模拟输入
//  GPIO_InitStructuree.GPIO_PuPd = GPIO_PuPd_NOPULL ;//不带上下拉
//  GPIO_Init(GPIOC, &GPIO_InitStructuree);//初始化 
// 
//	RCC_APB2PeriphResetCmd(RCC_APB2Periph_ADC3,ENABLE);	  //ADC3复位
//	RCC_APB2PeriphResetCmd(RCC_APB2Periph_ADC3,DISABLE);	//复位结束	 
// 
//	
//  ADC_CommonInitStructure.ADC_Mode = ADC_Mode_Independent;//独立模式
//  ADC_CommonInitStructure.ADC_TwoSamplingDelay = ADC_TwoSamplingDelay_5Cycles;//两个采样阶段之间的延迟5个时钟
//  ADC_CommonInitStructure.ADC_DMAAccessMode = ADC_DMAAccessMode_Disabled; //DMA失能
//  ADC_CommonInitStructure.ADC_Prescaler = ADC_Prescaler_Div4;//预分频4分频。ADCCLK=PCLK2/4=84/4=21Mhz,ADC时钟最好不要超过36Mhz 
//  ADC_CommonInit(&ADC_CommonInitStructure);//初始化
//	
//  ADC_InitStructure.ADC_Resolution = ADC_Resolution_12b;//12位模式
//  ADC_InitStructure.ADC_ScanConvMode = DISABLE;//非扫描模式	
//  ADC_InitStructure.ADC_ContinuousConvMode = DISABLE;//关闭连续转换
//  ADC_InitStructure.ADC_ExternalTrigConvEdge = ADC_ExternalTrigConvEdge_None;//禁止触发检测，使用软件触发
//  ADC_InitStructure.ADC_DataAlign = ADC_DataAlign_Right;//右对齐	
//  ADC_InitStructure.ADC_NbrOfConversion =4;//1个转换在规则序列中 也就是只转换规则序列1 
//  ADC_Init(ADC3, &ADC_InitStructure);//ADC初始化
//	
// 
//	ADC_Cmd(ADC3, ENABLE);//开启AD转换器	

//}				  
////获得ADC值
////ch: @ref ADC_channels 
////通道值 0~16取值范围为：ADC_Channel_0~ADC_Channel_16
////返回值:转换结果
//u16 Get_Adc(u8 ch)   
//{
//	  	//设置指定ADC的规则组通道，一个序列，采样时间
//	ADC_RegularChannelConfig(ADC3, ch, 1, ADC_SampleTime_480Cycles );	//ADC3,ADC通道,480个周期,提高采样时间可以提高精确度			    
//  
//	ADC_SoftwareStartConv(ADC3);		//使能指定的ADC3的软件转换启动功能	
//	 
//	while(!ADC_GetFlagStatus(ADC3, ADC_FLAG_EOC ));//等待转换结束

//	return ADC_GetConversionValue(ADC3);	//返回最近一次ADC3规则组的转换结果
//}
////获取通道ch的转换值，取times次,然后平均 
////ch:通道编号
////times:获取次数
////返回值:通道ch的times次转换结果平均值
//u16 Get_Adc_Average(u8 ch,u8 times)
//{
//	u32 temp_val=0;
//	u8 t;
//	for(t=0;t<times;t++)
//	{
//		temp_val+=Get_Adc(ch);
//		delay_ms(1);
//	}
//	
//	return temp_val/times;
//	
//}

//u16 Get_Adc_Average1(u8 ch,u8 times)//time必须要小于20
//{
//	u32 temp_val[10]={0};
//	int t,max,min,sum;
//	for(t=0;t<times;t++)
//	{
//		temp_val[t]=Get_Adc(ch);
//		delay_ms(5);
//	}
//	
//	sum=0;
//	max=temp_val[0];
//	min=temp_val[0];
//	for(t=0;t<times;t++)
//	{
//		if(max<temp_val[t])

//		max=temp_val[t];

//		if(min>temp_val[t])

//		min=temp_val[t];
//		sum=sum+temp_val[t];
//	}
//	return (sum-max-min)/(times-2);
//	
//}



//double Get_electric_current(void) //计算电流(0-150A)
//{
//		u16 temp;
//		double electric_current;
//		temp=Get_Adc_Average(6,3);
//	  electric_current=temp/4096.0*150.0;
//		return electric_current;

//}
//double Get_voltage(void)//计算电压(0-60v)
//{
//		u16 temp;
//		double voltage;
//		temp=Get_Adc_Average(5,3);
//	  voltage=temp/4096.0*60.0;
//		return voltage;

//}

//u16 AD_get(u8 adress)
//{
//	u16 adcx;
//if(adress==0)//左前
//{
//adcx=Get_Adc_Average(ADC_Channel_11,40);//获取通道5的转换值，20次取平均//PC1C左后通道11，PF5左前通道15 ,PF4右前通道14,PF3D右后通道9

//}
//if(adress==2)//左后
//{
//adcx=Get_Adc_Average(ADC_Channel_15,40);//获取通道5的转换值，20次取平均//PC1C左后通道11，PF5左前通道15 ,PF4右前通道14,PF3D右后通道9

//}
//if(adress==1)//右前
//{
//adcx=Get_Adc_Average(ADC_Channel_14,40);//获取通道5的转换值，20次取平均//PC1C左后通道11，PF5左前通道15 ,PF4右前通道14,PF3D右后通道9

//}
//if(adress==3)//右后
//{
//adcx=Get_Adc_Average(ADC_Channel_9,40);//获取通道5的转换值，20次取平均//PC1C左后通道11，PF5左前通道15 ,PF4右前通道14,PF3D右后通道9

//}
//return adcx;

//}


//void AD_all(u8 delay_time,u8 times) /////2.100
//{

// u32 temp_val[5]={0,0,0,0,0},ref;
// u8 t;
// for(t=0;t<times;t++)
// {
//  temp_val[0]+=Get_Adc(ADC_Channel_11); //左前
//  temp_val[2]+=Get_Adc(ADC_Channel_15); //左后
//  temp_val[1]+=Get_Adc(ADC_Channel_14); //右前
//  temp_val[3]+=Get_Adc(ADC_Channel_9); //右后
//  
//  temp_val[4]+=Get_Adc(ADC_Channel_5); //原来是采集电流，现在用来采集AD的供电电压
//  
//  delay_ms(delay_time);
// 
// 
// }
// 
//  AD_angle[0]=temp_val[0]/times/4096.0*2.0*pi;  //0左前，1右前，2左后，3右后
//  AD_angle[2]=temp_val[2]/times/4096.0*2.0*pi;
//  AD_angle[1]=temp_val[1]/times/4096.0*2.0*pi;
//  AD_angle[3]=temp_val[3]/times/4096.0*2.0*pi;
// 
// 
// 
////使用电流检测的IO检测AD电源的电压值，当作参考，而不是机械的使用3.3v
////  ref=temp_val[4]/times;
////   AD_angle[0]=temp_val[0]/times/ref*2.0*pi;  //0左前，1右前，2左后，3右后
////  AD_angle[2]=temp_val[2]/times/ref*2.0*pi;
////  AD_angle[1]=temp_val[1]/times/ref*2.0*pi;
////  AD_angle[3]=temp_val[3]/times/ref*2.0*pi;
// 
// 
//// return temp_val/times;


//}


