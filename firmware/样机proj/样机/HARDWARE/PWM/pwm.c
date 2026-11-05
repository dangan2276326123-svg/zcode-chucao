#include "pwm.h"
#include "led.h"
#include "usart.h"

#include "path_plan.h"
extern double veloc[4];	
int count_TIM4=0;                     //记录左侧车轮转过的圈数

void TIM1_PWM_Init(u32 arr,u32 psc)  //四个行走电机用tim8的p波输出
{		 					 
	//此部分需手动修改IO口设置
	
	GPIO_InitTypeDef GPIO_InitStructure;
	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
	TIM_OCInitTypeDef  TIM_OCInitStructure;
	
	RCC_APB2PeriphClockCmd(RCC_APB2Periph_TIM1,ENABLE);  	//TIM8时钟使能    
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOE, ENABLE); 	//使能PORTF时钟	
	
	GPIO_PinAFConfig(GPIOE,GPIO_PinSource9,GPIO_AF_TIM1); //GPIOE9复用为定时器1
	GPIO_PinAFConfig(GPIOE,GPIO_PinSource13,GPIO_AF_TIM1);//GPIOE13复用为定时器1
	GPIO_PinAFConfig(GPIOE,GPIO_PinSource11,GPIO_AF_TIM1);//GPIOE11复用为定时器1
	GPIO_PinAFConfig(GPIOE,GPIO_PinSource14,GPIO_AF_TIM1);//GPIOE14复用为定时器1
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9|GPIO_Pin_11|GPIO_Pin_13|GPIO_Pin_14; 
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;        //复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;      //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;        //上拉
	GPIO_Init(GPIOE,&GPIO_InitStructure);              //初始化PE9|11|13|14
	
	
	
//	GPIO_SetBits(GPIOC,GPIO_Pin_6|GPIO_Pin_7|GPIO_Pin_8|GPIO_Pin_9);//GPIOF9,F10设置高，灯灭
	TIM_TimeBaseStructure.TIM_Prescaler=psc;  //定时器分频
	TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
	TIM_TimeBaseStructure.TIM_Period=arr;   //自动重装载值
	TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
	
	TIM_TimeBaseInit(TIM1,&TIM_TimeBaseStructure);//初始化定时器1
	
	//初始化TIM8 Channel1 PWM模式	 
	TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM1; //选择定时器模式:TIM脉冲宽度调制模式2
 	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出使能
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
	TIM_OC1Init(TIM1, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM8OC1
	TIM_OC2Init(TIM1, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM8OC2
  TIM_OC3Init(TIM1, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM8OC3
  TIM_OC4Init(TIM1, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM8OC4


	TIM_OC1PreloadConfig(TIM1, TIM_OCPreload_Enable);  //使能TIM8在CCR1上的预装载寄存器
  TIM_OC2PreloadConfig(TIM1, TIM_OCPreload_Enable);  //使能TIM8在CCR2上的预装载寄存器
	TIM_OC3PreloadConfig(TIM1, TIM_OCPreload_Enable);  //使能TIM8在CCR3上的预装载寄存器
	TIM_OC4PreloadConfig(TIM1, TIM_OCPreload_Enable);  //使能TIM8在CCR4上的预装载寄存器
 
  TIM_ARRPreloadConfig(TIM1,ENABLE);//ARPE使能 
	TIM_Cmd(TIM1, ENABLE);  //使能TIM8
	TIM_CtrlPWMOutputs(TIM1,ENABLE); 									  
}

extern double veloc_limit ;


//void pwm_veloc(u8 adress,double veloc)
//{
//	int speed;
//	speed =(int)(250.0/veloc_limit*veloc);//0-255对应0-3.3V(模块转换为0-5v)，对应着0-veloc_limit m/s；  计算占空比
//	
//	
///////////////////////////	
//	if(adress==0)//左前为0
//	{
//		if(speed<0)             //前面计算出的占空比如果是负的
//		{	

//			replay_switch(0,0);//PE0=0,反向
//			speed=-speed;  //反向不能考虑死区，因为一下子给大了不转
//			
//			if(speed<start_pwm)//保证计算安全，保证不出现负数
//			 speed=0;
////			if(speed>M1_dead_voltage_erro_max)//大于最大死区电压  防止一下子给大了 起不来
////			speed=M1_dead_voltage_erro_max;	  //最大死区电压
//			else
//			speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);	 //进行强制线性变换0-5v 转换为1v到4.2v  占空比
//				
//		}
//		else 
//		{	
//			replay_switch(0,1);//正向
//			
//		if(speed<start_pwm)//保证计算安全  对 相当于自己在软件上设置一个死区  
//			 speed=0;
//		else                                                                                             //下面这一行是在计算p波占空比
//		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);	 //进行强制线性变换0-5v 转换为1v到4.2v  占空比
//			                                                                                             
//		}		
//		
////				printf("speed %d \r\n",speed);
//		TIM_SetCompare1(TIM8,speed);                           //结果上是在赋p波  直接上是在设置占空比
//		
//	

//	}
////////////////////////	
//		if(adress==2)//左后为2
//	{
//		if(speed<0)
//		{	
//			speed=-speed;
//			if(speed<start_pwm)//保证计算安全
//			speed=0;
//			if(speed>M1_dead_voltage_erro_max)//大于最大死区电压
//				speed=M1_dead_voltage_erro_max;
//			
//			replay_switch(1,0);//PE1=0,反向
//		}
//		else 
//		{
//			replay_switch(1,1);//正向
////				printf(" L_F %d \r\n",speed );
//		
//		if(speed<start_pwm)//保证计算安全
//			speed=0;
//		else
//		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);
//		}
//		
//		TIM_SetCompare2(TIM8,speed);
//	}
///////////////////////////////
//		if(adress==1)//右前为1
//	{
//		if(speed<0)
//		{	
//			speed=-speed;
//			if(speed<start_pwm)//保证计算安全
//			speed=0;
//			if(speed>M1_dead_voltage_erro_max)//大于最大死区电压
//			speed=M1_dead_voltage_erro_max;
//			replay_switch(2,0);//PE2=0,反向

//		}
//		else 
//		{
//			replay_switch(2,1);//正向

//		if(speed<start_pwm)//保证计算安全
//			speed=0;
//		else
//		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);
//			
//		}
//					
//		TIM_SetCompare3(TIM8,speed);
//	

//	}
////////////////////////////
//		if(adress==3)//右后为3
//	{
//		if(speed<0)
//		{	
//			speed=-speed;
//			if(speed<start_pwm)//保证计算安全
//			speed=0;
//			if(speed>M1_dead_voltage_erro_max)//大于最大死区电压
//			speed=M1_dead_voltage_erro_max;
//			
//			replay_switch(3,0);//PE3=0,反向
//		}
//		else 
//		{
//			replay_switch(3,1);//正向
//		
//		if(speed<start_pwm)//保证计算安全
//			speed=0;
//		else
//		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);
//			
//		}
//		
//	
//		TIM_SetCompare4(TIM8,speed);
//	}
//}

void pwm_veloc(u8 adress,double veloc)
{
	int speed;
	speed =(int)(250.0/veloc_limit*veloc);//0-255对应0-3.3V(模块转换为0-5v)，对应着0-veloc_limit m/s；  计算占空比
	
	
/////////////////////////	
	if(adress==0)//左前为0
	{
		if(speed<0)             //前面计算出的占空比如果是负的
		{	
			replay_switch(0,0);//PE0=0,反向
			speed=-speed;  //反向不能考虑死区，因为一下子给大了不转
				
		}
		else 
		{	
			replay_switch(0,1);//正向			                                                                                             
		}		
		
		if(speed<start_pwm)//保证计算安全  对 相当于自己在软件上设置一个死区  
			 speed=0;
		else                                                                                             //下面这一行是在计算p波占空比
		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);	 //进行强制线性变换0-5v 转换为1v到4.2v  占空比
		TIM_SetCompare1(TIM1,speed);                           //结果上是在赋p波  直接上是在设置占空比
		
	

	}
//////////////////////	
		if(adress==2)//左后为2
	{
		if(speed<0)
		{	
			speed=-speed;
			replay_switch(2,0);//PE2=0,反向

		}
		else 
		{
			replay_switch(2,1);//正向			
		}
		if(speed<start_pwm)//保证计算安全
			speed=0;
		else
		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);			
		TIM_SetCompare3(TIM1,speed);
	
		
	}
/////////////////////////////
		if(adress==1)//右前为1
	{
		if(speed<0)
		{	
			speed=-speed;	
			replay_switch(1,0);//PE1=0,反向
		}
		else 
		{
			replay_switch(1,1);//正向	
		}
		if(speed<start_pwm)//保证计算安全
			speed=0;
		else
		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);
		TIM_SetCompare2(TIM1,speed);

	}
//////////////////////////
		if(adress==3)//右后为3
	{
		if(speed<0)
		{	
			speed=-speed;
			replay_switch(3,0);//PE3=0,反向
		}
		else 
		{
			replay_switch(3,1);//正向
		
		}
		
	  if(speed<start_pwm)//保证计算安全
			speed=0;
		else
		speed=(int)(speed*(M1_dead_voltage_erro_max-M1_dead_voltage_erro)/250.0+M1_dead_voltage_erro);
		TIM_SetCompare4(TIM1,speed);
	}
}


// 继电器
void BigRelayPWM_Init(u32 arr,u32 psc)
{		 					 
	//此部分需手动修改IO口设置
	
	GPIO_InitTypeDef GPIO_InitStructure;
	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
	TIM_OCInitTypeDef  TIM_OCInitStructure;
	
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2,ENABLE);  	//TIM14时钟使能    
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE); 	//使能PORTF时钟	
	
	GPIO_PinAFConfig(GPIOA,GPIO_PinSource5,GPIO_AF_TIM2); //GPIOF9复用为定时器14
	
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_5;           //GPIOF9
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;        //复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;      //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;        //上拉
	GPIO_Init(GPIOA,&GPIO_InitStructure);              //初始化PF9
	  
	TIM_TimeBaseStructure.TIM_Prescaler=psc;  //定时器分频
	TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
	TIM_TimeBaseStructure.TIM_Period=arr;   //自动重装载值
	TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
	
	TIM_TimeBaseInit(TIM2,&TIM_TimeBaseStructure);//初始化定时器14
	
	//初始化TIM2 Channel1 PWM模式	 
	TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM1; //选择定时器模式:TIM脉冲宽度调制模式2
 	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出使能
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_Low; //输出极性:TIM输出比较极性低
	TIM_OC1Init(TIM2, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1

	TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
 
  TIM_ARRPreloadConfig(TIM2,ENABLE);//ARPE使能
	// 设置占空比为50%
  TIM_SetCompare1(TIM2, arr / 2);
	
	TIM_Cmd(TIM2, ENABLE);  //使能TIM14									  
} 




// 后面未使用///////////////////////////////////////////////////////////////////////

//TIM_ICInitTypeDef  TIM4_ICInitStructure;

////定时器5通道1输入捕获配置
////arr：自动重装值(TIM2,TIM5是32位的!!)
////psc：时钟预分频数



//void Encoder1_TIM4_init(void)//实际的左侧车轮编码器
//{  
//    GPIO_InitTypeDef         GPIO_InitStructure; 
//    TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
//    TIM_ICInitTypeDef        TIM_ICInitStructure;
//    NVIC_InitTypeDef         NVIC_InitStructure;
//  
//    RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM4,ENABLE);//开启TIM4时钟
//    RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB,ENABLE);//开启GPIOB时钟
////    RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOD,ENABLE);//开启GPIOD时钟
//    GPIO_PinAFConfig(GPIOB,GPIO_PinSource6,GPIO_AF_TIM4);
//	  GPIO_PinAFConfig(GPIOB,GPIO_PinSource7,GPIO_AF_TIM4);
// //   GPIO_PinAFConfig(GPIOD,GPIO_PinSource13,GPIO_AF_TIM4);
// 
//    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6; //GPIOB6,GPIOB7
//    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_AF; 
//    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;
//    GPIO_InitStructure.GPIO_OType = GPIO_OType_OD;
//    GPIO_InitStructure.GPIO_PuPd  = GPIO_PuPd_UP ;
//    GPIO_Init(GPIOB,&GPIO_InitStructure); 

//    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_7; //GPIOB6,GPIOB7
//    GPIO_InitStructure.GPIO_Mode  = GPIO_Mode_AF; 
//    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;
//    GPIO_InitStructure.GPIO_OType = GPIO_OType_OD;
//    GPIO_InitStructure.GPIO_PuPd  = GPIO_PuPd_UP ;
//    GPIO_Init(GPIOB,&GPIO_InitStructure); 

//    TIM_TimeBaseStructure.TIM_Period = 8000; //设置下一个更新事件装入活动的自动重装载寄存器周期的值
//    TIM_TimeBaseStructure.TIM_Prescaler = 0; //设置用来作为TIMx时钟频率除数的预分频值  不分频
//    TIM_TimeBaseStructure.TIM_ClockDivision = 0; //设置时钟分割:TDTS = Tck_tim
//    TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up;  //TIM向上计数模式
//    TIM_TimeBaseInit(TIM4, &TIM_TimeBaseStructure); //PWM输出实验 中 初始化定时器 ARR PSC等等
//		
//		
//		NVIC_InitStructure.NVIC_IRQChannel = TIM4_IRQn; //TIM4中断
//		NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 2; //先占优先级2级
//		NVIC_InitStructure.NVIC_IRQChannelSubPriority = 2; //从优先级0级
//		NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;  //IRQ通道被使能
//		NVIC_Init(&NVIC_InitStructure); //初始化NVIC寄存器

//		
//   //<span style="color:#ff0000;">//设置定时器为编码器模式   IT1  IT2为上升沿和下降沿都计数四倍频</span>
//    TIM_EncoderInterfaceConfig(TIM4, TIM_EncoderMode_TI12,TIM_ICPolarity_Falling,TIM_ICPolarity_Rising);
//    TIM_ICStructInit(&TIM_ICInitStructure);
//    TIM_ICInitStructure.TIM_ICFilter =6;  //输入滤波器
//    TIM_ICInit(TIM4, &TIM_ICInitStructure);
//    TIM_ClearFlag(TIM4, TIM_FLAG_Update);  //清楚所有标志位
//		
//    TIM_ITConfig(TIM4, TIM_IT_Update, ENABLE); //允许中断更新
//		TIM_SetCounter(TIM4,0);
////    TIM4->CNT = 0;与上面一行作用一样 上一行是用的库函数 这一行直接操作寄存器
//    TIM_Cmd(TIM4, ENABLE);  //使能TIM4
//}

//void TIM4_IRQHandler(void)
//{

//    if(TIM_GetITStatus(TIM4,TIM_IT_Update)==SET)
//    { 	
//			if((TIM4->CR1>>4&0x01)==0)//正转动
//				{
////				Other=TIM4->CNT;
//				count_TIM4++;
//				}

//     	if((TIM4->CR1>>4&0x01)==1)//反向转动
//				{
////				Other=TIM4->CNT-10000;
//				count_TIM4--;
//				}
//    }
//    TIM_ClearITPendingBit(TIM4,TIM_IT_Update); 
//}

//void Encoder1_TIM1_init(void)//实际的右侧车轮编码器
//{

//	GPIO_InitTypeDef GPIO_InitStructure;
//	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;

//	
//	RCC_APB2PeriphClockCmd(RCC_APB2Periph_TIM1,ENABLE);  	//TIM1时钟使能    
//	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOE, ENABLE); 	//使能PORTE时钟
//	

//	/************定时器1引脚初始化******************/
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9|GPIO_Pin_11; //PTE9 PTE11
//	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;
//	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	
//	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; 
//	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_NOPULL; //浮空输入，其实默认就是浮空输入
//	
//	GPIO_Init(GPIOE,&GPIO_InitStructure); 
//	/***********************************************/
//	

//	/***********************************************/
//	
//	GPIO_PinAFConfig(GPIOE,GPIO_PinSource9,GPIO_AF_TIM1); //复用位定时器1
//	GPIO_PinAFConfig(GPIOE,GPIO_PinSource11,GPIO_AF_TIM1); //复用位定时器1
//	  
//	TIM_TimeBaseStructure.TIM_Prescaler=0;  //定时器分频
//	TIM_TimeBaseStructure.TIM_ClockDivision = TIM_CKD_DIV1;
//	TIM_TimeBaseStructure.TIM_Period=65535;   //自动重装载值
//	
//	TIM_TimeBaseInit(TIM1,&TIM_TimeBaseStructure);


//	
//	TIM_EncoderInterfaceConfig(TIM1,TIM_EncoderMode_TI12,TIM_ICPolarity_Rising,TIM_ICPolarity_Rising);
//	TIM_Cmd(TIM1, ENABLE); 	//使能定时器1



//}

////***************TIM1计数寄存器赋值**************
////void TIM1_Encoder_Write(int data)
////{
////    TIM1->CNT = data;
////}

////*************读计数TIM1个数**************
//int TIM1_Encoder_Read(void)
//{ 
//	s16 data;
//	data=(s16)(TIM_GetCounter(TIM1));
//	return (int)data;
//}


//TIM_ICInitTypeDef  TIM3_ICInitStructure;

//void TIM3_CH1_Cap_Init(u16 arr,u16 psc)//不只是通道1   还有  通道2也给配置了 6000 840
//{
//	GPIO_InitTypeDef GPIO_InitStructure;
//	TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
//	NVIC_InitTypeDef NVIC_InitStructure;

//	
//	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3,ENABLE);  	//TIM5时钟使能    
//	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA,ENABLE); 	//使能PORTA时钟	
//	
//	
//	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6; //GPIOA0
//	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
//	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
//	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽复用输出
//	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN; //下拉
//	GPIO_Init(GPIOA,&GPIO_InitStructure); //初始化PA0
//	


//	GPIO_PinAFConfig(GPIOA,GPIO_PinSource6,GPIO_AF_TIM3); //PA0复用位定时器5

//	
//	TIM_TimeBaseStructure.TIM_Prescaler=psc;  //定时器分频
//	TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
//	TIM_TimeBaseStructure.TIM_Period=arr;   //自动重装载值
//	TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
//	
//	TIM_TimeBaseInit(TIM3,&TIM_TimeBaseStructure);
//	

//	//初始化TIM5输入捕获参数
//	TIM3_ICInitStructure.TIM_Channel = TIM_Channel_1; //CC1S=01 	选择输入端 IC1映射到TI1上
//  TIM3_ICInitStructure.TIM_ICPolarity = TIM_ICPolarity_Falling;	//下降沿捕获
//  TIM3_ICInitStructure.TIM_ICSelection = TIM_ICSelection_DirectTI; //映射到TI1上
//  TIM3_ICInitStructure.TIM_ICPrescaler = TIM_ICPSC_DIV1;	 //配置输入分频,不分频 
//  TIM3_ICInitStructure.TIM_ICFilter = 0x0F;//IC1F=0000 配置输入滤波器 不滤波
//  TIM_ICInit(TIM3, &TIM3_ICInitStructure);

//	
//	TIM_ITConfig(TIM3,TIM_IT_Update,ENABLE);//允许更新中断 ,允许CC1IE捕获中断	
//	TIM_ITConfig(TIM3,TIM_IT_CC1,ENABLE);//允许更新中断 ,允许CC1IE捕获中断	



//			TIM_Cmd(TIM3,DISABLE); 	//关闭定时器4
//			TIM_SetCounter(TIM3,0);
//      TIM_Cmd(TIM3,ENABLE ); 	//使能定时器5


//  NVIC_InitStructure.NVIC_IRQChannel = TIM3_IRQn;
//	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=2;//抢占优先级3
//	NVIC_InitStructure.NVIC_IRQChannelSubPriority =0;		//子优先级3
//	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			//IRQ通道使能
//	NVIC_Init(&NVIC_InitStructure);	//根据指定的参数初始化VIC寄存器
//}



//u8  TIM3CH1_CAPTURE_STA=0;	//输入捕获状态		    				
//u32	TIM3CH1_CAPTURE_VAL;	//输入捕获值(TIM2/TIM5是32位)
//u32	TIM3CH1_CAPTURE_VAL_1;	//输入捕获值(TIM2/TIM5是32位)
//u32	TIM3CH1_CAPTURE_VAL_2;	//输入捕获值(TIM2/TIM5是32位)
//u32	TIM3CH1_CAPTURE_VAL_3;	//输入捕获值(TIM2/TIM5是32位)

//u8  TIM3CH2_CAPTURE_STA=0;	//输入捕获状态		    				
//u32	TIM3CH2_CAPTURE_VAL;	//输入捕获值(TIM2/TIM5是32位)
//u32	TIM3CH2_CAPTURE_VAL_1;	//输入捕获值(TIM2/TIM5是32位)
//u32	TIM3CH2_CAPTURE_VAL_2;	//输入捕获值(TIM2/TIM5是32位)
//u32	TIM3CH2_CAPTURE_VAL_3;	//输入捕获值(TIM2/TIM5是32位)

//u8 Tim3YiChuFlag = 0;


//int tim3_low_time_us=0;
//int tim3_high_time_us=0;
//float tim3_low_time_ms=0.0;
//float tim3_high_time_ms=0.0;
//float CycleTime = 0.0;

//int tim3_low_us=0;
//int tim3_high_us=0;
//float tim3_low_ms=0.0;
//float tim3_high_ms=0.0;

//static int Tim3CeSuStartFlag=1; //启动第一次捕获标志位
//static int Tim3CeSuStartFlag2=1; //启动第一次捕获标志位

//int Tim3count_i = 0;
//int Tim3YiChuCount = 0;


//void TIM3_IRQHandler(void)
//{
//	

// {
//if((TIM3CH1_CAPTURE_STA&0X80)==0)//还未成功捕获	,如果成功捕获了，那都不进如if后面的执行语句，表示正在处理，上一波数据还没有处理完毕
//	{
//	if(TIM_GetITStatus(TIM3, TIM_IT_Update) != RESET)//溢出  两种中断类型分开写的 这个是定时器到点的更新中断
//				{
//					Tim3YiChuFlag = 1;
//					TIM_OC1PolarityConfig(TIM3,TIM_ICPolarity_Falling); //CC1P=0 重新设置为下降沿捕获
//          tim3_low_time_ms = 0;
//          tim3_high_time_ms = 0;
//					CycleTime = 0;
//					Tim3CeSuStartFlag = 1;
//				}
//		else
//				{
//					Tim3YiChuFlag=0;
//				}
//if(TIM_GetITStatus(TIM3, TIM_IT_CC1) != RESET)//捕获1发生捕获事件
//		{
////			printf("11111111111111111111\r\n");
//			if(TIM3CH1_CAPTURE_STA==0X60)
//					{
//						TIM3CH1_CAPTURE_STA=0XE0;		 //标记成功捕获到高电平脉宽
//						TIM3CH1_CAPTURE_VAL_3=TIM_GetCapture1(TIM3);//再次获取当前的捕获值.
////						tim3_high_time_us=(TIM3CH1_CAPTURE_VAL_3-TIM3CH1_CAPTURE_VAL_2)*100;	  //得到总的高电平时间，因为是从0开始记，直接乘就行，算出微秒
//						tim3_high_time_ms=TIM3CH1_CAPTURE_VAL_3*100*0.001;//换算成毫秒
////						tim3_high_time_ms=tim3_high_time_us;
//					  CycleTime = tim3_low_time_ms + tim3_high_time_ms; //计算周期公式 （不涉及溢出次数）
////						CycleTime = 6000*Tim3YiChuCount+(TIM3CH1_CAPTURE_VAL_3 - TIM3CH1_CAPTURE_VAL_1)*0.001;   //换算成ms 总周期
//						TIM_Cmd(TIM3,DISABLE); 	     //关闭定时器4
//						TIM_SetCounter(TIM3,0);
//						TIM_OC1PolarityConfig(TIM3,TIM_ICPolarity_Falling);		//CC1P=1 设置为下降沿捕获
//						TIM_Cmd(TIM3,ENABLE); 	     //使能定时器4

//						Tim3CeSuStartFlag=1;			   //清空，高电平也捕获完成，准备重新开启下一次捕获
//					}
//			if(TIM3CH1_CAPTURE_STA==0x20)		//如果之前已经捕获到下降沿 ,那这次就是上升沿
//					{	
//						TIM3CH1_CAPTURE_VAL_2=TIM_GetCapture1(TIM3);//获取当前的捕获值.
////						tim3_low_time_us=(TIM3CH1_CAPTURE_VAL_2-TIM3CH1_CAPTURE_VAL_1)*100;	  //得到总的低电平时间，因为是从0开始记，直接乘就行，算出微秒
//						tim3_low_time_ms=TIM3CH1_CAPTURE_VAL_2*100*0.001;//换算成毫秒
////						tim3_low_time_ms=tim3_low_time_us;
//						TIM_Cmd(TIM3,DISABLE); 	//关闭定时器4
//						TIM_SetCounter(TIM3,0);
//						TIM_OC1PolarityConfig(TIM3,TIM_ICPolarity_Falling); //捕获完低电平后再设置下降沿捕获,开始捕获高电平
//						TIM_Cmd(TIM3,ENABLE); 	//使能定时器4
//						TIM3CH1_CAPTURE_STA=0X60;		//标记成功捕获到一次上升沿，已经捕获到低电平脉宽
//					}	
//				else if(Tim3CeSuStartFlag==1)
//					{
//						Tim3count_i++;
//						Tim3CeSuStartFlag=0;
////					    TIM3CH1_CAPTURE_VAL_1=0;
//						TIM3CH1_CAPTURE_STA=0X20;		//标记捕获到了第一个下降沿
//						TIM_Cmd(TIM3,DISABLE); 	//关闭定时器3
//						TIM_SetCounter(TIM3,0);
////					    TIM3CH1_CAPTURE_VAL_1 = TIM_GetCapture1(TIM3);
////						TIM3CH1_CAPTURE_VAL_1=TIM_GetCapture1(TIM3);
//						TIM_OC1PolarityConfig(TIM3,TIM_ICPolarity_Rising);		//CC1P=1 设置为上升沿捕获
//						TIM_Cmd(TIM3,ENABLE); 	//使能定时器4
//					}		
//		}			     	    					   
// 	}
//}


//		  TIM_ClearITPendingBit(TIM3, TIM_IT_CC1|TIM_IT_Update); //清除中断标志位
//}






