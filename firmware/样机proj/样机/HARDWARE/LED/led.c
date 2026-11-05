#include "led.h" 
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

//初始化PF9和PF10为输出口.并使能这两个口的时钟		    
//LED IO初始化

extern double wheel_angle_limit;
extern double veloc[4];	//每个车轮的转速                                                                   //*******************
extern double angle[4];//每个车轮的转角  
extern u8 flag_car_mode ; // 0是四轮全能转向+航模 1是四轮有限位+航模 2是四轮有限位+车模 3是四轮有限位+单手遥控 4是双轮有限位+航模 5是双轮有限位+单手遥控 


void LED_Init(void)    //PF9  新板子中pf8 pf9用来刹车电流检测
{    	 
  GPIO_InitTypeDef  GPIO_InitStructure;
  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOF, ENABLE);//使能GPIOF时钟


  //GPIOF9,F10初始化设置
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化
	
	GPIO_ResetBits(GPIOF,GPIO_Pin_9);//GPIOF9,F10设置高，灯灭
}

void replay_switch_Init(void)
{
  GPIO_InitTypeDef  GPIO_InitStructure;
  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE);//使能GPIOA,GPIOE时钟
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB, ENABLE);//使能GPIOA,GPIOE时钟
  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOE, ENABLE);//使能GPIOF时钟
  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOD, ENABLE);//使能GPIOF时钟
  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOF, ENABLE);//使能GPIOA,GPIOE时钟
  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOG, ENABLE);//使能GPIOF时钟
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOC, ENABLE);//使能GPIOF时钟
	
	//方向调速等相关的io口初始化
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0|GPIO_Pin_1|GPIO_Pin_2|GPIO_Pin_3;
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
//  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
//  GPIO_Init(GPIOE, &GPIO_InitStructure);//初始化
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_8;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOE, &GPIO_InitStructure);//初始化
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_11|GPIO_Pin_12;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化

	
  // PC3 4 调速相关io的初始化
//  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3|GPIO_Pin_4;//LED0和LED1对应IO口
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
//  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//  GPIO_Init(GPIOC, &GPIO_InitStructure);//初始化GPIO
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6|GPIO_Pin_7;//LED0和LED1对应IO口
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化GPIO


	//喇叭
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_15;//LED0和LED1对应IO口
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
//  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化GPIO
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3|GPIO_Pin_4|GPIO_Pin_5|GPIO_Pin_6|GPIO_Pin_7|GPIO_Pin_8;//LED0和LED1对应IO口
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOG, &GPIO_InitStructure);//初始化GPIO
	

	
	// 继电器 
	
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0|GPIO_Pin_1;
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
//  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
//  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化

//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7;
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
//  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
//  GPIO_Init(GPIOE, &GPIO_InitStructure);//初始化
	
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5;
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
//  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
//  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10|GPIO_Pin_8;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化
	
	
	//指示灯
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0;//LED0和LED1对应IO口
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOC, &GPIO_InitStructure);//初始化GPIO

	// 预留输出
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3|GPIO_Pin_4|GPIO_Pin_5|GPIO_Pin_6|GPIO_Pin_7;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOD, &GPIO_InitStructure);//初始化
	
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_11;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化
	

	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_4|GPIO_Pin_5;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//普通输出模式
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;//下拉
  GPIO_Init(GPIOE, &GPIO_InitStructure);//初始化
	
	// 预留输入
	 
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9|GPIO_Pin_10|GPIO_Pin_11|GPIO_Pin_12|GPIO_Pin_13|GPIO_Pin_14|GPIO_Pin_15;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOD, &GPIO_InitStructure);//初始化

//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_3;
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化
	 // 拨码器
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_11|GPIO_Pin_13|GPIO_Pin_14;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化
	 



//限位开关的输出 正好8个
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5; //KEY0 KEY1 KEY2对应引脚
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化GPIOE2,3,4
//	
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0|GPIO_Pin_1|GPIO_Pin_2; //KEY0 KEY1 KEY2对应引脚
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化GPIOE2,3,4
//	
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10|GPIO_Pin_12|GPIO_Pin_13|GPIO_Pin_14; //KEY0 KEY1 KEY2对应引脚
//  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
//  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
//  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//  GPIO_Init(GPIOE, &GPIO_InitStructure);//初始化GPIOE2,3,4
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_4;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_1|GPIO_Pin_2|GPIO_Pin_3|GPIO_Pin_4|GPIO_Pin_5;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOC, &GPIO_InitStructure);//初始化
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_12|GPIO_Pin_15;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;//普通输入模式
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100M
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
  GPIO_Init(GPIOF, &GPIO_InitStructure);//初始化
}

void mp3_control(u8 flag)
{
	if (flag==0)  //不显示声音  全是1 不唱
		{     
		MP3_IO_0=1;
		MP3_IO_1=1;	
		MP3_IO_2=1;	
		MP3_IO_3=1;			
		MP3_IO_4=1;
		MP3_IO_5=1;
		}
		
			if (flag==1)  //显示声音 前进
		{
		MP3_IO_0=0;
		MP3_IO_1=1;	
		MP3_IO_2=1;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
    MP3_IO_5=1;
		}
			if (flag==2)  //显示声音 后退
		{
		MP3_IO_0=1;
		MP3_IO_1=0;	
		MP3_IO_2=1;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
		MP3_IO_5=1;
		}
				if (flag==3)  //显示声音 前轮转向
		{
		MP3_IO_0=0;
		MP3_IO_1=0;	
		MP3_IO_2=1;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
		MP3_IO_5=1;
		}
				if (flag==4)  //显示声音 四轮转向
		{
		MP3_IO_0=1;
		MP3_IO_1=1;	
		MP3_IO_2=0;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
				if (flag==5)  //显示声音 斜行转向
		{
		MP3_IO_0=0;
		MP3_IO_1=1;	
		MP3_IO_2=0;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
				if (flag==6)  //显示声音 原地转向
		{
		MP3_IO_0=1;
		MP3_IO_1=0;	
		MP3_IO_2=0;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
				if (flag==7)  //显示声音 切换为横向
		{
		MP3_IO_0=0;
		MP3_IO_1=0;	
		MP3_IO_2=0;	
		MP3_IO_3=1;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
				if (flag==8)  //显示声音 请注意有障碍物
		{
		MP3_IO_0=1;
		MP3_IO_1=1;	
		MP3_IO_2=1;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
				if (flag==9)  //显示声音 电池电量低，请充电
		{
		MP3_IO_0=0;
		MP3_IO_1=1;	
		MP3_IO_2=1;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
		
		   if (flag==10)  //显示声音 遥控器未连接
		{
		MP3_IO_0=1;
		MP3_IO_1=0;	
		MP3_IO_2=1;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
			   if (flag==11)  //显示声音 请先将油门拨杆掰到最低处启动
		{
		MP3_IO_0=0;
		MP3_IO_1=0;	
		MP3_IO_2=1;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}	
		
				if (flag==12)  //显示声音 刹车线故障请检查
		{
		MP3_IO_0=1;
		MP3_IO_1=1;	
		MP3_IO_2=0;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}	
				if (flag==13)  //显示声音 切换为正向
		{
		MP3_IO_0=0;
		MP3_IO_1=1;	
		MP3_IO_2=0;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}	
		  if (flag==14)  //显示声音 
		{
		MP3_IO_0=1;
		MP3_IO_1=0;	
		MP3_IO_2=0;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}	
			 if (flag==15)  //显示声音 
		{
		MP3_IO_0=0;
		MP3_IO_1=0;	
		MP3_IO_2=0;	
		MP3_IO_3=0;	
		MP3_IO_4=1;
		MP3_IO_5=1;		
		}
			 if (flag==16)  //显示声音 
		{
		MP3_IO_0=1;
		MP3_IO_1=1;	
		MP3_IO_2=1;	
		MP3_IO_3=1;	
		MP3_IO_4=0;
		MP3_IO_5=1;		
		}
		
}

void replay_switch(u8 ch,u8 replayswitch)//电机方向控制
{
			
	u8 switch_ch; 
	//PE0 PE1 PE2 PE3 对应电机方向 
  //改为PE8,PA11,PF9,PA12	
	if(ch==0)  
	{
		switch_ch=ch;
		PEout(8)=replayswitch;
	}
	if(ch==1)  
	{
		switch_ch=ch;
		PFout(9)=replayswitch;
	}
	if(ch==2)
	{
		switch_ch=ch;
		PAout(11)=replayswitch;
		
	}
	if(ch==3)  
	{
		switch_ch=ch;
		PAout(12)=replayswitch;
	}
			
//	if(ch<=3)  
//			{
//				switch_ch=ch;
//				PEout(switch_ch)=replayswitch;
//			}		
	
	//PC3 PC4 PC5 PG0 对应电机低速
	//PC3,PC4改为PF7,PF6
	//PC5未使用，PG0连接语音模块
	
	//后面的部分均未调用
	if(ch==4)  
	{
		switch_ch=ch;
		PFout(7)=replayswitch;
	}
	if(ch==5)  
	{
		switch_ch=ch;
		PFout(6)=replayswitch;
	}
	if(ch==6)  
	{
	}
	if(ch==7)
	{
	}

//	if(ch>=4&&ch<=6)		
//		{
//			switch_ch=ch-1;				
//			PCout(switch_ch)=replayswitch;
//		}
			
	//PG10-13未使用
//			if(ch>=8&&ch<=11)
//			{
//				switch_ch=ch+2;
//				PGout(switch_ch)=replayswitch;
//			}
}


u8 Touch_detection(u8 flag )  // 返回9 说明没有任何触碰
{

	if(flag==1)
	{
			if(PCin(4)==0) //左前 左转受限 
			{ 
				//angle[0]=wheel_angle_limit; 			
				printf("左前左转限位卡住:\r\n");
				return 0;
			}
			// 原代码引脚混乱，需测试
			if(PCin(5)==0) //左前 右转受限 
			{ 
				
				printf("左前右转限位卡住:\r\n");
				return 1;
			}
			if(PAin(4)==0) //右前 左转受限 
			{
				printf("右前左转限位卡住:\r\n");
				return 2;
			}	
			if(PCin(3)==0) //右前 右转受限 
			{	
				printf("右前右转限位卡住:\r\n");
				return 3;
			}
			if(PFin(12)==0) //左后 左转受限 
			{
				printf("左后左转限位卡住:\r\n");
				return 4;
			}
			if(PFin(15)==0) //左后 右转受限 
			{
				printf("左后右转限位卡住:\r\n");
				return 5;
			}
			if(PCin(1)==0) //右后 左转受限 
			{
				printf("右后左转限位卡住:\r\n");
				return 6;
			}
			if(PCin(2)==0) //右后 右转受限 
			{
				printf("右后右转限位卡住:\r\n");
				return 7;
			}
			
			return 9;   // 如果前面都没有进入，说明没有任何限位，则为9
	}
	if(flag==0)
	{
			return 9;
	}
	
	

}

void wheel_angle_limit_set(u8 flag)  //  转角有限幅的时候需要设置为限制值	
{
	if(flag==1)
		{
			if(angle[0]>=wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[0]=wheel_angle_limit;  //****************************************485通讯使伺服电机转向这一部分电机号等我还没想明白  记得理一下这里**********
			if(angle[0]<-wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[0]=-wheel_angle_limit;
			
			if(angle[1]>=wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[1]=wheel_angle_limit;  //****************************************485通讯使伺服电机转向这一部分电机号等我还没想明白  记得理一下这里**********
			if(angle[1]<-wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[1]=-wheel_angle_limit;
				
			if(angle[2]>=wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[2]=wheel_angle_limit;  //****************************************485通讯使伺服电机转向这一部分电机号等我还没想明白  记得理一下这里**********
			if(angle[2]<-wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[2]=-wheel_angle_limit;
			
			if(angle[3]>=wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[3]=wheel_angle_limit;  //****************************************485通讯使伺服电机转向这一部分电机号等我还没想明白  记得理一下这里**********
			if(angle[3]<-wheel_angle_limit) //前轮左转受阻限幅**************************************************************************************************
					angle[3]=-wheel_angle_limit;
		}

}
//  flag_car_mode ; // 0是四轮全能转向+航模 1是四轮有限位+航模 2是四轮有限位+车模 3是四轮有限位+单手遥控 4是双轮有限位+航模 5是双轮有限位+单手遥控 
void select_flag_car_mode(void)  ///进行模式选择 车辆模型。遥控器方式，通过拨码器进行设置
{
	// 注意，拨到NO是0 ////////////////////////////////////////////////////////
	if (Dial_switch_ch1==1&& Dial_switch_ch2==1&&Dial_switch_ch3==1)
	{
		flag_car_mode=0; //
	}
	if (Dial_switch_ch1==1&& Dial_switch_ch2==0&&Dial_switch_ch3==1)
	{
		flag_car_mode=1; //
	}
	if (Dial_switch_ch1==1&& Dial_switch_ch2==1&&Dial_switch_ch3==0)
	{
		flag_car_mode=2; //
	}
	if (Dial_switch_ch1==1&& Dial_switch_ch2==0&&Dial_switch_ch3==0)
	{
		flag_car_mode=3; //
	}
	if (Dial_switch_ch1==0&& Dial_switch_ch2==1&&Dial_switch_ch3==1)
	{
		flag_car_mode=4; //
	}
	if (Dial_switch_ch1==0&& Dial_switch_ch2==0&&Dial_switch_ch3==1)
	{
		flag_car_mode=5; //
	}
	

}
