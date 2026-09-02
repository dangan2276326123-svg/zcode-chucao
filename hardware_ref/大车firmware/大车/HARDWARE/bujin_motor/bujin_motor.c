#include "sys.h"
#include "delay.h"
#include "usart.h"
#include "math.h"
#include "stdint.h"
#include "bujin_motor.h" 


#define F2TIME_PARA				12000000   									//将频率值转换为定时器寄存器值得转换参数
#define STEP_PARA					10	   											//任意时刻转动步数修正因子
#define STEP_AA						31       										//加加速阶段，离散化点数
#define STEP_UA						31			  									//匀加速阶段，离散化点数
#define STEP_RA						31													//减加速阶段，离散化点数

#define STEP_SPTA					20													//SPTA最大速度等级
#define MAXSPEED_SPTA			80000												//SPTA最大速度
#define ACCSPEED_SPTA			150000											//SPTA加速度


//*正常S型曲线参数生成的表格*/
uint16_t Motor1TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = {0};
uint16_t Motor1StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor2TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor2StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor3TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor3StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};	

//*将参数降为2/3 S型曲线参数生成的表格*/
uint16_t Motor1_23TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor1_23StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor2_23TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor2_23StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor3_23TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor3_23StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};	
//*将参数降为1/3 S型曲线参数生成的表格*/
uint16_t Motor1_13TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor1_13StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor2_13TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor2_13StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor3_13TimeTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};
uint16_t Motor3_13StepTable[2*(STEP_AA+STEP_UA+STEP_RA)+1] = { 0};	


MOTOR_CONTROL_S motor1;	     	 
MOTOR_CONTROL_S motor2;	     	 
MOTOR_CONTROL_S motor3;	      
MOTOR_CONTROL_SPTA motor4;



//PWM输出初始化
//arr：自动重装值
//psc：时钟预分频数
void Initial_PWM_Motor1(void) //TIM2
{		 					 
   //此部分需手动修改IO口设置
   GPIO_InitTypeDef GPIO_InitStructure;
   TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
   TIM_OCInitTypeDef  TIM_OCInitStructure;
   NVIC_InitTypeDef NVIC_InitStructure;
	
	
   RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM2,ENABLE);  	//TIM14时钟使能    
   RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE); 	//使能PORTF时钟	

   GPIO_PinAFConfig(GPIOA,GPIO_PinSource15,GPIO_AF_TIM2); //GPIOF9复用为定时器14

   GPIO_InitStructure.GPIO_Pin = GPIO_Pin_15;           //GPIOF9
   GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;        //复用功能
   GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
   GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;      //推挽复用输出
   GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;        //上拉
   GPIO_Init(GPIOA,&GPIO_InitStructure);              //初始化PF9

	
		TIM_DeInit(TIM2);
		 //中断NVIC设置：允许中断，设置优先级
		NVIC_InitStructure.NVIC_IRQChannel = TIM2_IRQn;     
		NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =PWM1_PreemptionPriority;   
		NVIC_InitStructure.NVIC_IRQChannelSubPriority = PWM1_SubPriority;          
		NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;             
		NVIC_Init(&NVIC_InitStructure);
		
	
	
   TIM_TimeBaseStructure.TIM_Prescaler=5;  //定时器分频710000
   TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
   TIM_TimeBaseStructure.TIM_Period=1000;   //自动重装载值
   TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
   TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;

   TIM_TimeBaseInit(TIM2,&TIM_TimeBaseStructure);//初始化定时器14

   //初始化TIM14 Channel1 PWM模式	 
   TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2; //选择定时器模式:TIM脉冲宽度调制模式2
   TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出使能
	 TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Enable; //互补信号输出到对应的输出引脚
   TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_Low; //输出极性:TIM输出比较极性低
   TIM_OCInitStructure.TIM_OCNPolarity = TIM_OCNPolarity_High;
   TIM_OCInitStructure.TIM_OCIdleState = TIM_OCIdleState_Reset;
   TIM_OCInitStructure.TIM_OCNIdleState = TIM_OCIdleState_Reset;
   TIM_OCInitStructure.TIM_Pulse = 50; 
   TIM_OC1Init(TIM2, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM2,ENABLE);//ARPE使能 


	//清中断，以免一启用中断后立即产生中断
	TIM_ClearFlag(TIM2, TIM_FLAG_Update);
	//使能TIM1中断源
	TIM_ITConfig(TIM2, TIM_IT_Update, ENABLE);

   TIM_Cmd(TIM2, DISABLE);  //使能TIM2
	 
	// 	TIM_CtrlPWMOutputs(TIM2,ENABLE); //使能PWM输出
	 
} 
//TIM3 PWM部分初始化 
//PWM输出初始化
//arr：自动重装值
//psc：时钟预分频数
void Initial_PWM_Motor2(void)//TIM3
{		 					 
   //此部分需手动修改IO口设置
   GPIO_InitTypeDef GPIO_InitStructure;
   TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
   TIM_OCInitTypeDef  TIM_OCInitStructure;
   NVIC_InitTypeDef NVIC_InitStructure;
	
   RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM3,ENABLE);  	//TIM14时钟使能    
   RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB, ENABLE); 	//使能PORTF时钟	

   GPIO_PinAFConfig(GPIOB,GPIO_PinSource4,GPIO_AF_TIM3); //GPIOF9复用为定时器14

   GPIO_InitStructure.GPIO_Pin = GPIO_Pin_4;           //GPIOF9
   GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;        //复用功能
   GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
   GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;      //推挽复用输出
   GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;        //上拉
   GPIO_Init(GPIOB,&GPIO_InitStructure);              //初始化PF9

	
	TIM_DeInit(TIM3);
     //中断NVIC设置：允许中断，设置优先级
	NVIC_InitStructure.NVIC_IRQChannel = TIM3_IRQn;    //更新事件 	TIM2_IRQHandler
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =PWM2_PreemptionPriority;   //抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = PWM2_SubPriority;          //响应优先级1
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;             //允许中断
	NVIC_Init(&NVIC_InitStructure);
	
	
   TIM_TimeBaseStructure.TIM_Prescaler=5;  //定时器分频
   TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
   TIM_TimeBaseStructure.TIM_Period=1000;   //自动重装载值
   TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
   TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;

   TIM_TimeBaseInit(TIM3,&TIM_TimeBaseStructure);//初始化定时器14

   //初始化TIM14 Channel1 PWM模式	 
   	TIM_OCInitStructure.TIM_OCMode       = TIM_OCMode_PWM2;       //PWM2模式 
    TIM_OCInitStructure.TIM_OutputState  = TIM_OutputState_Enable;  //信号输出到对应的输出引脚 
    TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Enable; //互补信号输出到对应的输出引脚                  
    TIM_OCInitStructure.TIM_Pulse =50;   //脉冲宽度 
    TIM_OCInitStructure.TIM_OCPolarity   = TIM_OCPolarity_Low;   //互补输出高电平有效 
    TIM_OCInitStructure.TIM_OCNPolarity  = TIM_OCNPolarity_High;    //互补输出高电平有效      
    TIM_OCInitStructure.TIM_OCIdleState  = TIM_OCIdleState_Reset;  //输出空闲状态为1 
    TIM_OCInitStructure.TIM_OCNIdleState = TIM_OCIdleState_Reset;   //互补输出空闲状态为0 
   TIM_OC1Init(TIM3, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM3, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM3,ENABLE);//ARPE使能 
	 
	 	//清中断，以免一启用中断后立即产生中断
    TIM_ClearFlag(TIM3, TIM_FLAG_Update);
    //使能TIM1中断源
    TIM_ITConfig(TIM3, TIM_IT_Update, ENABLE); 

   TIM_Cmd(TIM3, DISABLE);  //使能TIM14
} 
//TIM4 PWM部分初始化 
//PWM输出初始化
//arr：自动重装值
//psc：时钟预分频数
void Initial_PWM_Motor3(void)//TIM4
{		 					 
   //此部分需手动修改IO口设置
   GPIO_InitTypeDef GPIO_InitStructure;
   TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
   TIM_OCInitTypeDef  TIM_OCInitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	
   RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM4,ENABLE);  	//TIM14时钟使能    
   RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB, ENABLE); 	//使能PORTF时钟	

   GPIO_PinAFConfig(GPIOB,GPIO_PinSource6,GPIO_AF_TIM4); //GPIOF9复用为定时器14

   GPIO_InitStructure.GPIO_Pin = GPIO_Pin_6;           //GPIOF9
   GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;        //复用功能
   GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
   GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;      //推挽复用输出
   GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;        //上拉
   GPIO_Init(GPIOB,&GPIO_InitStructure);              //初始化PF9

	TIM_DeInit(TIM4);
     //中断NVIC设置：允许中断，设置优先级
	NVIC_InitStructure.NVIC_IRQChannel = TIM4_IRQn;    //更新事件 	TIM3_IRQHandler
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =PWM3_PreemptionPriority;   //抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority = PWM3_SubPriority;          //响应优先级1
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;             //允许中断
	NVIC_Init(&NVIC_InitStructure);
	
   TIM_TimeBaseStructure.TIM_Prescaler=5;  //定时器分频
   TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
   TIM_TimeBaseStructure.TIM_Period=1000;   //自动重装载值
   TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
   TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;

   TIM_TimeBaseInit(TIM4,&TIM_TimeBaseStructure);//初始化定时器14

   //初始化TIM14 Channel1 PWM模式	 
  TIM_OCInitStructure.TIM_OCMode       = TIM_OCMode_PWM2;       //PWM2模式 
	TIM_OCInitStructure.TIM_OutputState  = TIM_OutputState_Enable;  //信号输出到对应的输出引脚 
	TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Enable; //互补信号输出到对应的输出引脚                  
	TIM_OCInitStructure.TIM_Pulse =50;   //脉冲宽度 
	TIM_OCInitStructure.TIM_OCPolarity   = TIM_OCPolarity_Low;   //互补输出高电平有效 
	TIM_OCInitStructure.TIM_OCNPolarity  = TIM_OCNPolarity_High;    //互补输出高电平有效      
	TIM_OCInitStructure.TIM_OCIdleState  = TIM_OCIdleState_Reset;  //输出空闲状态为1 
	TIM_OCInitStructure.TIM_OCNIdleState = TIM_OCIdleState_Reset;   //互补输出空闲状态为0   
   TIM_OC1Init(TIM4, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM4, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM4,ENABLE);//ARPE使能 
	//清中断，以免一启用中断后立即产生中断
	TIM_ClearFlag(TIM4, TIM_FLAG_Update);
	//使能TIM1中断源
	TIM_ITConfig(TIM4, TIM_IT_Update, ENABLE); 
   TIM_Cmd(TIM4, DISABLE);  //使能TIM14
}  
//TIM5 PWM部分初始化 
//PWM输出初始化
//arr：自动重装值
//psc：时钟预分频数
void Initial_PWM_Motor4(void)
{		 					 
   //此部分需手动修改IO口设置
   GPIO_InitTypeDef GPIO_InitStructure;
   TIM_TimeBaseInitTypeDef  TIM_TimeBaseStructure;
   TIM_OCInitTypeDef  TIM_OCInitStructure;
    NVIC_InitTypeDef NVIC_InitStructure;
	
   RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM5,ENABLE);  	//TIM14时钟使能    
   RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE); 	//使能PORTF时钟	

   GPIO_PinAFConfig(GPIOA,GPIO_PinSource0,GPIO_AF_TIM5); //GPIOF9复用为定时器14

   GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0;           //GPIOF9
   GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;        //复用功能
   GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
   GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;      //推挽复用输出
   GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;        //上拉
   GPIO_Init(GPIOA,&GPIO_InitStructure);              //初始化PF9

		NVIC_InitStructure.NVIC_IRQChannel = TIM5_IRQn;                 //更新事件
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =PWM4_PreemptionPriority;        //抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority =PWM4_SubPriority;              //响应优先级1
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;                 //允许中断
	NVIC_Init(&NVIC_InitStructure);
	
	
   TIM_TimeBaseStructure.TIM_Prescaler=5;  //定时器分频
   TIM_TimeBaseStructure.TIM_CounterMode=TIM_CounterMode_Up; //向上计数模式
   TIM_TimeBaseStructure.TIM_Period=1000;   //自动重装载值
   TIM_TimeBaseStructure.TIM_ClockDivision=TIM_CKD_DIV1; 
   TIM_TimeBaseStructure.TIM_RepetitionCounter = 0;

   TIM_TimeBaseInit(TIM5,&TIM_TimeBaseStructure);//初始化定时器14

   //初始化TIM14 Channel1 PWM模式	 
   TIM_OCInitStructure.TIM_OCMode       = TIM_OCMode_PWM2;       //PWM2模式 
	TIM_OCInitStructure.TIM_OutputState  = TIM_OutputState_Enable;  //信号输出到对应的输出引脚 
	TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Enable; //互补信号输出到对应的输出引脚                  
	TIM_OCInitStructure.TIM_Pulse =50;   //脉冲宽度 
	TIM_OCInitStructure.TIM_OCPolarity   = TIM_OCPolarity_Low;   //互补输出高电平有效 
	TIM_OCInitStructure.TIM_OCNPolarity  = TIM_OCNPolarity_High;    //互补输出高电平有效      
	TIM_OCInitStructure.TIM_OCIdleState  = TIM_OCIdleState_Reset;  //输出空闲状态为1 
	TIM_OCInitStructure.TIM_OCNIdleState = TIM_OCIdleState_Reset;   //互补输出空闲状态为0   
   TIM_OC1Init(TIM5, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM5, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM5,ENABLE);//ARPE使能 
	//清中断，以免一启用中断后立即产生中断
	TIM_ClearFlag(TIM5, TIM_FLAG_Update);
	//使能TIM1中断源
	TIM_ITConfig(TIM5, TIM_IT_Update, ENABLE); 
   TIM_Cmd(TIM5, DISABLE);  //使能TIM14
}  



void bujin_motor_PWM_Init(void)
{
	Initial_PWM_Motor1();				//初始化电机1的PWM 
	Initial_PWM_Motor2();				//初始化电机2的PWM
	Initial_PWM_Motor3();				//初始化电机3的PWM
	Initial_PWM_Motor4();				//初始化电机4的PWM
	
	/*初始化电机运行参数，主要是根据S型曲线参数生成表格*/
	MotorRunParaInitial();
}


/*根据S型曲线参数获取某个时刻的频率*/
float GetFreAtTime(float fstart,float faa,float taa,float tua,float tra,float t)
{
		//根据公式计算从开始到最高速过冲中，t时刻的转动频率
	  if(t>=0&&t<=taa){
			//加加速阶段
			return fstart+0.5*faa*t*t;
		}else if(taa<t&&t<=(taa+tua)){
			//匀加速阶段
			return fstart+0.5*faa*taa*taa+(t-taa)*faa*taa;
		}else if((taa+tua)<t&&t<=(taa+tua+tra)){
			//减加速阶段
			return fstart+0.5*faa*taa*taa+(tua)*faa*taa+0.5*faa*taa*tra-0.5*faa*taa*(taa+tua+tra-t)*(taa+tua+tra-t)/(tra);
		}		
		return 0;
}

 /*计算S型曲线算法的每一步定时器周期及步进数*/
void CalcMotorPeriStep_CPF(float fstart,float faa,float taa,float tua,float tra,uint16_t MotorTimeTable[],uint16_t MotorStepTable[])
{
  int  i;
	float fi;
	
	for(i=0;i<STEP_AA;i++)
	{
		fi=GetFreAtTime(fstart,faa,taa,tua,tra,taa/STEP_AA*i);
		MotorTimeTable[i]=F2TIME_PARA/fi;
		MotorStepTable[i]=fi*(taa/STEP_AA)/STEP_PARA;
	}
	for(i=STEP_AA;i<STEP_AA+STEP_UA;i++)
	{
		fi=GetFreAtTime(fstart,faa,taa,tua,tra,taa+(tua/STEP_UA)*(i-STEP_AA));
		MotorTimeTable[i]=F2TIME_PARA/fi;
		MotorStepTable[i]=fi*(tua/STEP_UA)/STEP_PARA;
	}
	for(i=STEP_AA+STEP_UA;i<STEP_AA+STEP_UA+STEP_RA;i++)
	{
		fi=GetFreAtTime(fstart,faa,taa,tua,tra,taa+tua+tra/STEP_RA*(i-STEP_AA-STEP_UA));
		MotorTimeTable[i]=F2TIME_PARA/fi;
		MotorStepTable[i]=fi*(tra/STEP_RA)/STEP_PARA;
	}
	fi=GetFreAtTime(fstart,faa,taa,tua,tra,taa+tua+tra);
	MotorTimeTable[STEP_AA+STEP_UA+STEP_RA]=F2TIME_PARA/fi;
	MotorStepTable[STEP_AA+STEP_UA+STEP_RA]=fi*(tra/STEP_RA)/STEP_PARA;
	
	
	for(i=STEP_AA+STEP_UA+STEP_RA+1;i<2*(STEP_AA+STEP_UA+STEP_RA)+1;i++)
	{ 
		MotorTimeTable[i]=MotorTimeTable[2*(STEP_AA+STEP_UA+STEP_RA)-i];
		MotorStepTable[i]=MotorStepTable[2*(STEP_AA+STEP_UA+STEP_RA)-i];
	}
}



//电机运行参数初始化*/
void MotorRunParaInitial(void)
{ 
	/*FIXME:用户可以改变该参数实现S型曲线的升降特性*/ 
	CalcMotorPeriStep_CPF(M_FRE_START,M_FRE_AA,M_T_AA,M_T_UA,M_T_RA,Motor1TimeTable,Motor1StepTable); 
  CalcMotorPeriStep_CPF(M_FRE_START,M_FRE_AA,M_T_AA,M_T_UA,M_T_RA,Motor2TimeTable,Motor2StepTable); 	
	CalcMotorPeriStep_CPF(M_FRE_START,M_FRE_AA,M_T_AA,M_T_UA,M_T_RA,Motor3TimeTable,Motor3StepTable);

	/*更改参数降为2/3生成的表格*/
	CalcMotorPeriStep_CPF(M_FRE_START*2.0/3,M_FRE_AA*2.0/3,M_T_AA*2.0/3,M_T_UA*2.0/3,M_T_RA*2.0/3,Motor1_23TimeTable,Motor1_23StepTable); 
	CalcMotorPeriStep_CPF(M_FRE_START*2.0/3,M_FRE_AA*2.0/3,M_T_AA*2.0/3,M_T_UA*2.0/3,M_T_RA*2.0/3,Motor2_23TimeTable,Motor2_23StepTable); 	
	CalcMotorPeriStep_CPF(M_FRE_START*2.0/3,M_FRE_AA*2.0/3,M_T_AA*2.0/3,M_T_UA*2.0/3,M_T_RA*2.0/3,Motor3_23TimeTable,Motor3_23StepTable); 

	/*更改参数降为1/3生成的表格*/
	CalcMotorPeriStep_CPF(M_FRE_START*1.0/3,M_FRE_AA*1.0/3,M_T_AA*1.0/3,M_T_UA*1.0/3,M_T_RA*1.0/3,Motor1_13TimeTable,Motor1_13StepTable); 
	CalcMotorPeriStep_CPF(M_FRE_START*1.0/3,M_FRE_AA*1.0/3,M_T_AA*1.0/3,M_T_UA*1.0/3,M_T_RA*1.0/3,Motor2_13TimeTable,Motor2_13StepTable); 	
	CalcMotorPeriStep_CPF(M_FRE_START*1.0/3,M_FRE_AA*1.0/3,M_T_AA*1.0/3,M_T_UA*1.0/3,M_T_RA*1.0/3,Motor3_13TimeTable,Motor3_13StepTable);  	
}

/**************************************************************************************
 初始化电机的参数，主要是细分选择，使用的定时器，顺时针方向值，电机ID等
 **************************************************************************************/
void Initial_Motor(unsigned char MotorID, unsigned char StepDive,unsigned int maxposition)
{
  unsigned int i=0;
	MOTOR_CONTROL_S *pmotor=NULL; 
	MOTOR_CONTROL_SPTA *pmotor_spta=NULL; 
	uint16_t *MotorTimeTable;
	uint16_t *MotorStepTable;
	switch(StepDive)
	{
	 case 1:i=0x00;break;
	 case 2:i=0x01;break;
	 case 4:i=0x02;break;
	 case 8:i=0x03;break;
	 case 16:i=0x04;break;
	 case 32:i=0x05;break;
	 case 64:i=0x06;break;
	 case 128:i=0x07;break;
	 default:i=0x00;break;
	}
	
  switch(MotorID)
  {
//	  case 1:			 
//			if(i&0x01)
//			{
//			 GPIO_SetBits(GPIOA,GPIO_Pin_11);
//			}
//			if(i&0x02)
//			{
//			 GPIO_SetBits(GPIOA,GPIO_Pin_12);
//			}

//			if(i&0x04)
//			{
//				GPIO_SetBits(GPIOE,GPIO_Pin_7);
//			}
		//	GPIO_SetBits(GPIOE,GPIO_Pin_8); //使能
			
			pmotor=&motor1;
			motor1.id=1;
			motor1.clockwise=M1_CLOCKWISE;
			motor1.TIMx=TIM2;
			MotorTimeTable=Motor1TimeTable;
			MotorStepTable=Motor1StepTable;			
			break;
		case 2:			 
//			if(i&0x01)
//			{
//			 GPIO_SetBits(GPIOC,GPIO_Pin_0);
//			}
//			if(i&0x02)
//			{
//			 GPIO_SetBits(GPIOC,GPIO_Pin_1);
//			}

//			if(i&0x04)
//			{
//				GPIO_SetBits(GPIOC,GPIO_Pin_2);
//			} 			
//			GPIO_SetBits(GPIOC,GPIO_Pin_3);
			pmotor=&motor2;
			motor2.id=2;
			motor2.clockwise=M2_CLOCKWISE;
			motor2.TIMx=TIM3;
			MotorTimeTable=Motor2TimeTable;
			MotorStepTable=Motor2StepTable;
			 break;
		case 3:
//			if(i&0x01)
//			{
//			 GPIO_SetBits(GPIOA,GPIO_Pin_3);
//			}
//			if(i&0x02)
//			{
//			 GPIO_SetBits(GPIOA,GPIO_Pin_4);
//			}

//			if(i&0x04)
//			{
//				GPIO_SetBits(GPIOA,GPIO_Pin_5);
//			}
//			GPIO_SetBits(GPIOC,GPIO_Pin_4);
			pmotor=&motor3;
			motor3.id=3;
			motor3.clockwise=M3_CLOCKWISE;
			motor3.TIMx=TIM4;
			MotorTimeTable=Motor3TimeTable;
			MotorStepTable=Motor3StepTable;
			break;
		case 4:			
//			if(i&0x01)
//			 {
//			   GPIO_SetBits(GPIOD,GPIO_Pin_7);
//			 }
//			 if(i&0x02)
//			 {
//			   GPIO_SetBits(GPIOB,GPIO_Pin_5);
//			 }

//			 if(i&0x04)
//			 {
//			    GPIO_SetBits(GPIOB,GPIO_Pin_7);
//			 }
//			 GPIO_SetBits(GPIOB,GPIO_Pin_8);
			 motor4.id=4;
			 motor4.clockwise=M4_CLOCKWISE;
			 motor4.TIMx=TIM5;
			 motor4.divnum=StepDive;
			 motor4.GPIOBASE=GPIOB;
			 motor4.PWMGPIO=GPIO_Pin_6;
			 pmotor_spta=&motor4;
			 break;		
	  default:break;
  }
	if(MotorID<=3&&MotorID>=1)
	{
		pmotor->divnum=StepDive;
		pmotor->MaxPosition=maxposition;
		pmotor->MaxPosition_Pulse=maxposition*StepDive;

		pmotor->CurrentPosition=0;
		pmotor->CurrentPosition_Pulse=0;
		pmotor->StartTableLength=STEP_AA+STEP_UA+STEP_RA+1;
		pmotor->StopTableLength=STEP_AA+STEP_UA+STEP_RA; 
		pmotor->Counter_Table=MotorTimeTable;
		pmotor->Step_Table=MotorStepTable;

		pmotor->CurrentIndex=0;
		pmotor->speedenbale=0;
		pmotor->StartSteps=0;                  //必须清零，后面是累加，否则会把前一次的加上
		pmotor->StopSteps=0;                   //同上
		for(i=0;i<pmotor->StartTableLength;i++)
		 pmotor->StartSteps+=pmotor->Step_Table[i];
		for(i=0;i<pmotor->StopTableLength;i++)
		 pmotor->StopSteps+=pmotor->Step_Table[i+pmotor->StartTableLength];

		pmotor->TIMx->ARR =pmotor->Counter_Table[0]; //设置周期
		pmotor->TIMx->CCR1 =pmotor->Counter_Table[0]>>1;       //设置占空比
	}
	if(MotorID==4)
	{
		pmotor_spta->divnum=StepDive;
		pmotor_spta->MaxPosition=maxposition;
		pmotor_spta->MaxPosition_Pulse=maxposition*StepDive;		
	}
}

/**************************************************************************************
启动电机按照S型曲线参数运行*/
void Start_Motor_S(unsigned char MotorID,unsigned char dir,unsigned int Degree)
{
  unsigned int PulsesGiven=0;
	MOTOR_CONTROL_S *pmotor=NULL; 
	if(Degree==0)
	{ 		  	 
		return;
	}
	switch(MotorID)
	{
		case 1:
			pmotor=&motor1; 
			if(0==dir)
		  {
		    GPIO_SetBits(GPIOE,GPIO_Pin_10);
		  }
		  else
		  {
		    GPIO_ResetBits(GPIOE,GPIO_Pin_10);
		  } 			
			break;
		case 2:
			pmotor=&motor2; 
		  if(1==dir)
		  {
		    GPIO_SetBits(GPIOE,GPIO_Pin_11);
		  }
		  else
		  {
		    GPIO_ResetBits(GPIOE,GPIO_Pin_11);  
		  }	
			break;
		case 3:
			pmotor=&motor3; 
		  if(0==dir)
		  {
		    GPIO_SetBits(GPIOE,GPIO_Pin_12);
		  }
		  else
		  {
		    GPIO_ResetBits(GPIOE,GPIO_Pin_12);
		  }	
			break;
		default:
			return;
	}
	pmotor->en=1;
	pmotor->dir=dir;
	pmotor->running=1;
	pmotor->PulsesHaven=0;
	PulsesGiven=Degree;
	pmotor->Time_Cost_Act=0;
	pmotor->PulsesGiven=PulsesGiven*pmotor->divnum;
	Motor_Reinitial(MotorID);		
	pmotor->CurrentIndex=0;
	pmotor->speedenbale=0;
	pmotor->TIMx->ARR =pmotor->Counter_Table[0]; //设置周期
	pmotor->TIMx->CCR1 =pmotor->Counter_Table[0]>>1;       //设置占空比
	TIM_Cmd(pmotor->TIMx, ENABLE);		  //DISABLE
}



/*重新初始化电机运行时相关参数*/
void Motor_Reinitial(unsigned char MotorID)
{
	int i=0; 
	MOTOR_CONTROL_S *pmotor=NULL;  
	uint16_t *MotorTimeTable;
	uint16_t *MotorStepTable;
	uint16_t *MotorTime23Table;
	uint16_t *MotorStep23Table;
	uint16_t *MotorTime13Table;
	uint16_t *MotorStep13Table;
	
	switch(MotorID)
	{
		case 1:
			pmotor=&motor1;  
		  MotorTimeTable=Motor1TimeTable;
			MotorStepTable=Motor1StepTable;
			MotorTime23Table=Motor1_23TimeTable;
			MotorStep23Table=Motor1_23StepTable;
			MotorTime13Table=Motor1_13TimeTable;
			MotorStep13Table=Motor1_13StepTable;
			break;
		case 2:
			pmotor=&motor2;  
		  MotorTimeTable=Motor2TimeTable;
			MotorStepTable=Motor2StepTable;
			MotorTime23Table=Motor2_23TimeTable;
			MotorStep23Table=Motor2_23StepTable;
			MotorTime13Table=Motor2_13TimeTable;
			MotorStep13Table=Motor2_13StepTable;
			break;
		case 3:
			pmotor=&motor3; 
		  MotorTimeTable=Motor3TimeTable;
			MotorStepTable=Motor3StepTable;
			MotorTime23Table=Motor3_23TimeTable;
			MotorStep23Table=Motor3_23StepTable;
			MotorTime13Table=Motor3_13TimeTable;
			MotorStep13Table=Motor3_13StepTable;
			break;
		default:
			return ;
	}					 
	pmotor->pulsecount=0;
	pmotor->CurrentIndex=0;
	pmotor->speedenbale=0;
	
	pmotor->Counter_Table=MotorTimeTable;  		//指向启动时，时间基数计数表
  pmotor->Step_Table=MotorStepTable;  			//指向启动时，每个频率脉冲个数表
	pmotor->StartSteps=0;                  //必须清零，后面是累加，否则会把前一次的加上
	pmotor->StopSteps=0;                   //同上
	for(i=0;i<pmotor->StartTableLength;i++)
	 pmotor->StartSteps+=pmotor->Step_Table[i];
	for(i=0;i<pmotor->StopTableLength;i++)
	 pmotor->StopSteps+=pmotor->Step_Table[i+pmotor->StartTableLength];
	if(pmotor->PulsesGiven<pmotor->StartSteps+pmotor->StopSteps){
		//如果给定的运行步数小余最大S型曲线，则尝试选择2/3S型曲线
		pmotor->Counter_Table=MotorTime23Table;  		
		pmotor->Step_Table=MotorStep23Table;  			
		pmotor->StartSteps=0;                  
		pmotor->StopSteps=0;                   
		for(i=0;i<pmotor->StartTableLength;i++)
		 pmotor->StartSteps+=pmotor->Step_Table[i];
		for(i=0;i<pmotor->StopTableLength;i++)
		 pmotor->StopSteps+=pmotor->Step_Table[i+pmotor->StartTableLength];
		if(pmotor->PulsesGiven<pmotor->StartSteps+pmotor->StopSteps){
			//如果给定的运行步数小余最大S型曲线，则尝试选择1/3S型曲线
			pmotor->Counter_Table=MotorTime23Table;  		
			pmotor->Step_Table=MotorStep23Table;  			
			pmotor->StartSteps=0;                  
			pmotor->StopSteps=0;                   
			for(i=0;i<pmotor->StartTableLength;i++)
			 pmotor->StartSteps+=pmotor->Step_Table[i];
			for(i=0;i<pmotor->StopTableLength;i++)
			 pmotor->StopSteps+=pmotor->Step_Table[i+pmotor->StartTableLength];
		}
	}
	
	pmotor->TIMx->ARR =pmotor->Counter_Table[0]; //设置周期
	pmotor->TIMx->CCR1 =pmotor->Counter_Table[0]>>1;       //设置占空比
	pmotor->Time_Cost_Act=pmotor->TIMx->ARR;
	Get_TimeCost_ReverDot_S(MotorID);		 
		
}


/*多轴协同使用了算法原理进行时间预估，所以修改该算法时记得
 这两处保持同步*/
/*计算S型曲线反转点，S型曲线在运行时，加减速过程是完全对称的*/
unsigned long long Get_TimeCost_ReverDot_S(unsigned char MotorID)
{
	unsigned long long time_cost=0;
	unsigned long long time_cost2=0;
	unsigned int pulsecnt=0;
	int i=0,j;
	MOTOR_CONTROL_S *pmotor=NULL; 
	switch(MotorID)
	{
		case 1:
			pmotor=&motor1;  
			break;
		case 2:
			pmotor=&motor2;  
			break;
		case 3:
			pmotor=&motor3;  
			break;
		default:
			return 0;
	}
	
	if(pmotor->PulsesGiven>=pmotor->StartSteps+pmotor->StopSteps)
	{
		for(i=0;i<pmotor->StartTableLength;i++)
			time_cost+=(pmotor->Step_Table[i]*pmotor->Counter_Table[i]);
		for(i=0;i<pmotor->StopTableLength;i++)
			time_cost+=(pmotor->Step_Table[i+pmotor->StartTableLength]*pmotor->Counter_Table[i+pmotor->StartTableLength]);		
		time_cost+=(pmotor->PulsesGiven-pmotor->StartSteps-pmotor->StopSteps)*pmotor->Counter_Table[pmotor->StartTableLength-1];
		
		pmotor->RevetDot=pmotor->PulsesGiven-pmotor->StopSteps;
	}
	else
	{
		//考虑这种情况，第一频率142 步，第二频率148步，要是运动200步该怎么运行
		//所以这里要改变第二频率的步数
		while((pulsecnt+pmotor->Step_Table[i])<=(pmotor->PulsesGiven>>1))
		{					
			time_cost+=(pmotor->Step_Table[i]*pmotor->Counter_Table[i]);
			time_cost2+=(pmotor->Step_Table[i]*pmotor->Counter_Table[i]);
			pulsecnt+=pmotor->Step_Table[i];
			i++;
		}
		time_cost+=time_cost2;
		if(pmotor->Step_Table[i]<pmotor->PulsesGiven-2*pulsecnt)
		{
			pmotor->Step_Table[i]=pmotor->PulsesGiven-2*pulsecnt;
			pmotor->StartSteps=0;                  //必须清零，后面是累加，否则会把前一次的加上
			pmotor->StopSteps=0;                   //同上
			for(j=0;j<pmotor->StartTableLength;j++)
			 pmotor->StartSteps+=pmotor->Step_Table[j];
			for(j=0;j<pmotor->StopTableLength;j++)
			 pmotor->StopSteps+=pmotor->Step_Table[j+pmotor->StartTableLength];
		}
		time_cost+=(pmotor->Counter_Table[i]*(pmotor->PulsesGiven-2*pulsecnt));
		pmotor->RevetDot=pmotor->PulsesGiven-pulsecnt;
	}
	pmotor->Time_Cost_Cal=time_cost;
	return time_cost;
}




