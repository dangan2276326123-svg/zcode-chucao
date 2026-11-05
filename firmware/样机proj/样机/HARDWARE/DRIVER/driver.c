#include "driver.h"
#include "delay.h"
#include "usart.h"
#include "path_plan.h"
#include "adc.h"
#include "uart2.h"	
#include "sys.h"
#include "delay.h"
#include "usart.h"
#include "math.h"




u16  avr_frequency[4]={0,0,0,0};
long target_pos[4]={0,0,0,0};  //有符号方向
long current_pos[4]={0,0,0,0}; //有符号方向


DIR_Type motor_dir2=0;
DIR_Type motor_dir3=0;
DIR_Type motor_dir4=0;
DIR_Type motor_dir5=0;
u32 count[4]={0,0,0,0};



double Angle_Init[4]={3.988,2.22,2.30,3.90};	//左前3.99 左后2.50 右前2.44 右后3.95
double Angle_correct[4]={0,0,0,0};	


long location_count[4]={0,0,0,0};


/* S型加速参数 */
//int ACCELERATED_SPEED_LENGTH =(int)(1.5*FSPR*M1DIV); //定义加速度的点数（其实也是3000个细分步的意思），调这个参数改变加速点,
//u32 FRE_MIN=500;  //最低的运行频率，调这个参数调节最低运行速度
//u32 FRE_MAX=35000; //最高的运行频率，调这个参数调节匀速时的最高速度35000    
//uint32_t step_to_run= 6800+12800*10; //要匀速运行的步数       总共运行步数 = ACCELERATED_SPEED_LENGTH*2 + step_to_run                   
float fre[ACCELERATED_SPEED_LENGTH]; //数组存储加速过程中每一步的频率 
unsigned short period[ACCELERATED_SPEED_LENGTH]; //数组储存加速过程中每一步定时器的自动装载值,这是最终需要的   
uint32_t step_to_run= 0; //要匀速运行的步数       总共运行步数 = ACCELERATED_SPEED_LENGTH*2 + step_to_run 

//flexible代表S曲线区间（越大代表压缩的最厉害）加速度越大；越小越接近匀加速。理想的S曲线的取值为4-6）
//len  定义加速度的点数  fre_max 最高的运行频率  fre_min 35000
void CalculateSModelLine( float len, float fre_max, float fre_min, float flexible)//计算加减速过程中的频率
{
    int i=0;
    float deno ;
    float melo ;
    float delt = fre_max-fre_min;
    for(; i<len; i++)
    {
        melo = flexible* (i-len/2) / (len/2);
        deno = 1.0f / (1 + expf(-melo));  //expf is a library function of exponential(e)?
        fre[i] = delt * deno + fre_min;
        period[i] = (unsigned short)(14000000.0f / fre[i]); // 10000000 is the timer driver frequency
//    	printf("period[i]=%d  i=%d\r\n",period[i],i);//打印输出
			
		}
    return ;
}



/************** 驱动器控制信号线初始化 ****************/
/***********************************************
//TIM2_CH2(PA1) 单脉冲输出+重复计数功能初始化
//TIM2 时钟频率 72MHz
//arr：自动重装值
//psc：时钟预分频数
************************************************/
void bujin_motor_PWM_Init(u16 arr,u16 psc)
{
 TIM2_Init( arr, psc);//TIM2_CH1 
 TIM3_Init( arr, psc);//TIM3_CH1 
 TIM4_Init( arr, psc);//TIM4_CH1 
 TIM5_Init( arr, psc);//TIM5_CH1 
}


void TIM2_Init(u16 arr,u16 psc)
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
   GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_DOWN;        //下拉
   GPIO_Init(GPIOA,&GPIO_InitStructure);              //初始化PF9

		TIM_TimeBaseStructInit(&TIM_TimeBaseStructure);

		 //中断NVIC设置：允许中断，设置优先级
		
	
   TIM_TimeBaseStructure.TIM_Period = arr; //设置在下一个更新事件装入活动的自动重装载寄存器周期的值	 
	TIM_TimeBaseStructure.TIM_Prescaler =psc; //设置用来作为TIMx时钟频率除数的预分频值   
	TIM_TimeBaseStructure.TIM_ClockDivision = 0; //设置时钟分割:TDTS = Tck_tim
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up; //TIM向上计数模式

   TIM_TimeBaseInit(TIM2,&TIM_TimeBaseStructure);//初始化定时器14
	 TIM_ClearITPendingBit(TIM2,TIM_IT_Update);

   TIM_UpdateRequestConfig(TIM2,TIM_UpdateSource_Regular); /********* 设置只有计数溢出作为更新中断 ********/
	 TIM_SelectOnePulseMode(TIM2,TIM_OPMode_Single);/******* 单脉冲模式 **********/


   //初始化TIM14 Channel1 PWM模式	 
  TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2; //选择定时器模式:TIM脉冲宽度调制模式2
	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出2使能
	TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Disable; /****** 比较输出2N失能 *******/
	TIM_OCInitStructure.TIM_Pulse = arr>>1; //设置待装入捕获比较寄存器的脉冲值
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
   TIM_OC1Init(TIM2, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM2,ENABLE);//ARPE使能 

		TIM_ITConfig(TIM2, TIM_IT_Update ,ENABLE);  //TIM8   使能或者失能指定的TIM中断

    NVIC_InitStructure.NVIC_IRQChannel = TIM2_IRQn;     
		NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =2;   
		NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;          
		NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;     
		
		NVIC_Init(&NVIC_InitStructure);
		TIM_ClearITPendingBit(TIM2, TIM_IT_Update);  //清除TIMx的中断待处理位:TIM 中断源
	
   TIM_Cmd(TIM2, DISABLE);  //使能TIM2							  
}
/******* TIM2更新中断服务程序 *********/
void TIM2_IRQHandler(void)
{
	static uint32_t i=0;
	static uint8_t status = 1;
	static int num=0;
	if(TIM_GetITStatus(TIM2,TIM_FLAG_Update)!=RESET)//更新中断
	{
		TIM_ClearITPendingBit(TIM2,TIM_FLAG_Update);//清除更新中断标志位		
		//count[0]++; 
		TIM_GenerateEvent(TIM2,TIM_EventSource_Update);//产生一个更新事件 重新初始化计数器，
		//这里产生一个脉冲送到步进电机让电机运转一个脉冲数，即不细分的情况下，一般步进电机转1.8°
		//定时器初始化中，设置单脉冲模式是让计数器在下一个更新事件停止，即关闭，防止这次中断还没结束，
		//下一个计数器时间已经到了使中断紊乱，也就是进入中断后，定时器自动关闭。			
		TIM_Cmd(TIM2, ENABLE);  					   //使能TIM2,让定时器开始下一个脉冲计数后输出			
		   //   if(i%2==0) //每进入两次中断才是一个完整脉冲
      {		
				if(abs(location_count[0])<2*ACCELERATED_SPEED_LENGTH)//如果小于最大加速要求的脉冲
				{
				switch(status)
          {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM2,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM2,period[num]>>1);
                    count[0]++;
						       	num++;
                    if(count[0]>=abs(location_count[0]/2))
                    {
                        status=2;
                    }                        
                  break;
						 case 2://减速
									count[0]++;
									num--;
									TIM_SetAutoreload(TIM2,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM2,period[num]>>1);
									 
									if(count[0]==abs(location_count[0]))
									{	
									 if(motor_dir2==CCW) 						   //如果方向为逆时针   
											current_pos[0]+=count[0];
									 else          							   //否则方向为顺时针
										current_pos[0]-=count[0];			
										TIM_Cmd(TIM2, DISABLE);  				   //关闭TIM2			
								//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
										count[0]=0;
										status=1;
						   	 }
									break;
          }
				
				}
				else	
          {
						switch(status)
           {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM2,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM2,period[num]>>1);
                    count[0]++;
										num++;
                    if(count[0]>=ACCELERATED_SPEED_LENGTH)
                    {
                        status=3;
                    }                        
                  break;
              case 3://匀速status=3
                   
							     TIM_SetAutoreload(TIM2,avr_frequency[0]);//设定自动重装值;
							     TIM_SetCompare1(TIM2,avr_frequency[0]>>1);
							     count[0]++;
                     if(count[0]>=abs(location_count[0])-ACCELERATED_SPEED_LENGTH)
                       status=2;     
                   break;
              case 2://减速
                      count[0]++;
                      num--;
									TIM_SetAutoreload(TIM2,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM2,period[num]>>1);
                    if(count[0]==abs(location_count[0]))
										{  
										 if(motor_dir2==CCW) 						   //如果方向为逆时针   
												current_pos[0]+=count[0];
										 else          							   //否则方向为顺时针
											current_pos[0]-=count[0];			
											TIM_Cmd(TIM2, DISABLE);  				   //关闭TIM2			
									//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
											count[0]=0;
											status=1;
									  }
									break;
          
          }
				}
            
    }
				
	}
}

void TIM3_Init(u16 arr,u16 psc)
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

		TIM_TimeBaseStructInit(&TIM_TimeBaseStructure);

		 //中断NVIC设置：允许中断，设置优先级
		
	
   TIM_TimeBaseStructure.TIM_Period = arr; //设置在下一个更新事件装入活动的自动重装载寄存器周期的值	 
	TIM_TimeBaseStructure.TIM_Prescaler =psc; //设置用来作为TIMx时钟频率除数的预分频值   
	TIM_TimeBaseStructure.TIM_ClockDivision = 0; //设置时钟分割:TDTS = Tck_tim
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up; //TIM向上计数模式

   TIM_TimeBaseInit(TIM3,&TIM_TimeBaseStructure);//初始化定时器14
	 TIM_ClearITPendingBit(TIM3,TIM_IT_Update);

   TIM_UpdateRequestConfig(TIM3,TIM_UpdateSource_Regular); /********* 设置只有计数溢出作为更新中断 ********/
	 TIM_SelectOnePulseMode(TIM3,TIM_OPMode_Single);/******* 单脉冲模式 **********/


   //初始化TIM14 Channel1 PWM模式	 
  TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2; //选择定时器模式:TIM脉冲宽度调制模式2
	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出2使能
	TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Disable; /****** 比较输出2N失能 *******/
	TIM_OCInitStructure.TIM_Pulse = arr>>1; //设置待装入捕获比较寄存器的脉冲值
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
   TIM_OC1Init(TIM3, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM3, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM3,ENABLE);//ARPE使能 

		TIM_ITConfig(TIM3, TIM_IT_Update ,ENABLE);  //TIM8   使能或者失能指定的TIM中断

    NVIC_InitStructure.NVIC_IRQChannel = TIM3_IRQn;     
		NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =0;   
		NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;          
		NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;     
		
		NVIC_Init(&NVIC_InitStructure);
		TIM_ClearITPendingBit(TIM3, TIM_IT_Update);  //清除TIMx的中断待处理位:TIM 中断源
	
   TIM_Cmd(TIM3, DISABLE);  //使能TIM2	 							  
}

void TIM3_IRQHandler(void)
{
		static uint32_t i=0;
	static uint8_t status = 1;
	static int num=0;
	if(TIM_GetITStatus(TIM3,TIM_FLAG_Update)!=RESET)
	{
		TIM_ClearITPendingBit(TIM3,TIM_FLAG_Update);	
//		count[1]++; 
		TIM_GenerateEvent(TIM3,TIM_EventSource_Update);
		TIM_Cmd(TIM3, ENABLE);  		
		
		      {		
				if(abs(location_count[1])<2*ACCELERATED_SPEED_LENGTH)//如果小于最大加速要求的脉冲
				{
				switch(status)
          {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM3,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM3,period[num]>>1);
                    count[1]++;
						       	num++;
                    if(count[1]>=abs(location_count[1]/2))
                    {
                        status=2;
                    }                        
                  break;
						 case 2://减速
									count[1]++;
									num--;
									TIM_SetAutoreload(TIM3,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM3,period[num]>>1);
									 
									if(count[1]==abs(location_count[1]))
									{	
									 if(motor_dir3==CCW) 						   //如果方向为逆时针   
											current_pos[1]+=count[1];
									 else          							   //否则方向为顺时针
										current_pos[1]-=count[1];			
										TIM_Cmd(TIM3, DISABLE);  				   //关闭TIM2			
								//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
										count[1]=0;
										status=1;
						   	 }
									break;
          }
				
				}
				else	
          {
						switch(status)
           {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM3,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM3,period[num]>>1);
                    count[1]++;
										num++;
                    if(count[1]>=ACCELERATED_SPEED_LENGTH)
                    {
                        status=3;
                    }                        
                  break;
              case 3://匀速status=3
                   
							     TIM_SetAutoreload(TIM3,avr_frequency[1]);//设定自动重装值;
							     TIM_SetCompare1(TIM3,avr_frequency[1]>>1);
							     count[1]++;
                     if(count[1]>=abs(location_count[1])-ACCELERATED_SPEED_LENGTH)
                       status=2;     
                   break;
              case 2://减速
                      count[1]++;
                      num--;
									TIM_SetAutoreload(TIM3,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM3,period[num]>>1);
                    if(count[1]==abs(location_count[1]))
										{  
										 if(motor_dir3==CCW) 						   //如果方向为逆时针   
												current_pos[1]+=count[1];
										 else          							   //否则方向为顺时针
											current_pos[1]-=count[1];			
											TIM_Cmd(TIM3, DISABLE);  				   //关闭TIM2			
									//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
											count[1]=0;
											status=1;
									  }
									break;
          
          }
				}
            
    }
			
	
	}		
}

void TIM4_Init(u16 arr,u16 psc)
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


		TIM_TimeBaseStructInit(&TIM_TimeBaseStructure);

		 //中断NVIC设置：允许中断，设置优先级
		
	
   TIM_TimeBaseStructure.TIM_Period = arr; //设置在下一个更新事件装入活动的自动重装载寄存器周期的值	 
	TIM_TimeBaseStructure.TIM_Prescaler =psc; //设置用来作为TIMx时钟频率除数的预分频值   
	TIM_TimeBaseStructure.TIM_ClockDivision = 0; //设置时钟分割:TDTS = Tck_tim
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up; //TIM向上计数模式

   TIM_TimeBaseInit(TIM4,&TIM_TimeBaseStructure);//初始化定时器14
	 TIM_ClearITPendingBit(TIM4,TIM_IT_Update);

   TIM_UpdateRequestConfig(TIM4,TIM_UpdateSource_Regular); /********* 设置只有计数溢出作为更新中断 ********/
	 TIM_SelectOnePulseMode(TIM4,TIM_OPMode_Single);/******* 单脉冲模式 **********/


   //初始化TIM14 Channel1 PWM模式	 
  TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2; //选择定时器模式:TIM脉冲宽度调制模式2
	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出2使能
	TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Disable; /****** 比较输出2N失能 *******/
	TIM_OCInitStructure.TIM_Pulse = arr>>1; //设置待装入捕获比较寄存器的脉冲值
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
   TIM_OC1Init(TIM4, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM4, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM4,ENABLE);//ARPE使能 

		TIM_ITConfig(TIM4, TIM_IT_Update ,ENABLE);  //TIM8   使能或者失能指定的TIM中断

    NVIC_InitStructure.NVIC_IRQChannel = TIM4_IRQn;     
		NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =0;   
		NVIC_InitStructure.NVIC_IRQChannelSubPriority = 2;          
		NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;     
		
		NVIC_Init(&NVIC_InitStructure);
		TIM_ClearITPendingBit(TIM4, TIM_IT_Update);  //清除TIMx的中断待处理位:TIM 中断源
	
   TIM_Cmd(TIM4, DISABLE);  //使能TIM2	 							  
}

void TIM4_IRQHandler(void)
{	
	static uint32_t i=0;
	static uint8_t status = 1;
	static int num=0;
	if(TIM_GetITStatus(TIM4,TIM_FLAG_Update)!=RESET)
	{
		TIM_ClearITPendingBit(TIM4,TIM_FLAG_Update);	
		//count[2]++; 
		TIM_GenerateEvent(TIM4,TIM_EventSource_Update);
		TIM_Cmd(TIM4, ENABLE);  		
		
		      {		
				if(abs(location_count[2])<2*ACCELERATED_SPEED_LENGTH)//如果小于最大加速要求的脉冲
				{
				switch(status)
          {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM4,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM4,period[num]>>1);
                    count[2]++;
						       	num++;
                    if(count[2]>=abs(location_count[2]/2))
                    {
                        status=2;
                    }                        
                  break;
						 case 2://减速
									count[2]++;
									num--;
									TIM_SetAutoreload(TIM4,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM4,period[num]>>1);
									 
									if(count[2]==abs(location_count[2]))
									{	
									 if(motor_dir4==CCW) 						   //如果方向为逆时针   
											current_pos[2]+=count[2];
									 else          							   //否则方向为顺时针
										current_pos[2]-=count[2];			
										TIM_Cmd(TIM4, DISABLE);  				   //关闭TIM2			
								//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
										count[2]=0;
										status=1;
						   	 }
									break;
          }
				
				}
				else	
          {
						switch(status)
           {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM4,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM4,period[num]>>1);
                    count[2]++;
										num++;
                    if(count[2]>=ACCELERATED_SPEED_LENGTH)
                    {
                        status=3;
                    }                        
                  break;
              case 3://匀速status=3
                   
							     TIM_SetAutoreload(TIM4,avr_frequency[2]);//设定自动重装值;
							     TIM_SetCompare1(TIM4,avr_frequency[2]>>1);
							     count[2]++;
                     if(count[2]>=abs(location_count[2])-ACCELERATED_SPEED_LENGTH)
                       status=2;     
                   break;
              case 2://减速
                      count[2]++;
                      num--;
									TIM_SetAutoreload(TIM4,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM4,period[num]>>1);
                    if(count[2]==abs(location_count[2]))
										{  
										 if(motor_dir4==CCW) 						   //如果方向为逆时针   
												current_pos[2]+=count[2];
										 else          							   //否则方向为顺时针
											current_pos[2]-=count[2];			
											TIM_Cmd(TIM4, DISABLE);  				   //关闭TIM2			
									//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
											count[2]=0;
											status=1;
									  }
									break;
          }
				}          
    }	
	}
}

void TIM5_Init(u16 arr,u16 psc)
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
		TIM_TimeBaseStructInit(&TIM_TimeBaseStructure);

		 //中断NVIC设置：允许中断，设置优先级
		
	
   TIM_TimeBaseStructure.TIM_Period = arr; //设置在下一个更新事件装入活动的自动重装载寄存器周期的值	 
	TIM_TimeBaseStructure.TIM_Prescaler =psc; //设置用来作为TIMx时钟频率除数的预分频值   
	TIM_TimeBaseStructure.TIM_ClockDivision = 0; //设置时钟分割:TDTS = Tck_tim
	TIM_TimeBaseStructure.TIM_CounterMode = TIM_CounterMode_Up; //TIM向上计数模式

   TIM_TimeBaseInit(TIM5,&TIM_TimeBaseStructure);//初始化定时器14
	 TIM_ClearITPendingBit(TIM5,TIM_IT_Update);

   TIM_UpdateRequestConfig(TIM5,TIM_UpdateSource_Regular); /********* 设置只有计数溢出作为更新中断 ********/
	 TIM_SelectOnePulseMode(TIM5,TIM_OPMode_Single);/******* 单脉冲模式 **********/


   //初始化TIM14 Channel1 PWM模式	 
  TIM_OCInitStructure.TIM_OCMode = TIM_OCMode_PWM2; //选择定时器模式:TIM脉冲宽度调制模式2
	TIM_OCInitStructure.TIM_OutputState = TIM_OutputState_Enable; //比较输出2使能
	TIM_OCInitStructure.TIM_OutputNState = TIM_OutputNState_Disable; /****** 比较输出2N失能 *******/
	TIM_OCInitStructure.TIM_Pulse = arr>>1; //设置待装入捕获比较寄存器的脉冲值
	TIM_OCInitStructure.TIM_OCPolarity = TIM_OCPolarity_High; //输出极性:TIM输出比较极性高
   TIM_OC1Init(TIM5, &TIM_OCInitStructure);  //根据T指定的参数初始化外设TIM1 4OC1
   TIM_OC1PreloadConfig(TIM5, TIM_OCPreload_Enable);  //使能TIM14在CCR1上的预装载寄存器
  
   TIM_ARRPreloadConfig(TIM5,ENABLE);//ARPE使能 

		TIM_ITConfig(TIM5, TIM_IT_Update ,ENABLE);  //TIM8   使能或者失能指定的TIM中断

    NVIC_InitStructure.NVIC_IRQChannel = TIM5_IRQn;     
		NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority =0;   
		NVIC_InitStructure.NVIC_IRQChannelSubPriority = 1;          
		NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;     
		
		NVIC_Init(&NVIC_InitStructure);
		TIM_ClearITPendingBit(TIM5, TIM_IT_Update);  //清除TIMx的中断待处理位:TIM 中断源
	
   TIM_Cmd(TIM5, DISABLE);  //使能TIM2	 							  
}

void TIM5_IRQHandler(void)
{
		static uint32_t i=0;
	static uint8_t status = 1;
	static int num=0;
	if(TIM_GetITStatus(TIM5,TIM_FLAG_Update)!=RESET)
	{
		TIM_ClearITPendingBit(TIM5,TIM_FLAG_Update);	
		//count[3]++; 
		TIM_GenerateEvent(TIM5,TIM_EventSource_Update);
		TIM_Cmd(TIM5, ENABLE);  		
		      {		
				if(abs(location_count[3])<2*ACCELERATED_SPEED_LENGTH)//如果小于最大加速要求的脉冲
				{
				switch(status)
          {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM5,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM5,period[num]>>1);
                    count[3]++;
						       	num++;
                    if(count[3]>=abs(location_count[3]/2))
                    {
                        status=2;
                    }                        
                  break;
						 case 2://减速
									count[3]++;
									num--;
									TIM_SetAutoreload(TIM5,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM5,period[num]>>1);
									 
									if(count[3]==abs(location_count[3]))
									{	
									 if(motor_dir5==CCW) 						   //如果方向为逆时针   
											current_pos[3]+=count[3];
									 else          							   //否则方向为顺时针
										current_pos[3]-=count[3];			
										TIM_Cmd(TIM5, DISABLE);  				   //关闭TIM2			
								//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
										count[3]=0;
										status=1;
						   	 }
									break;
          }
				
				}
				else	
          {
						switch(status)
           {
              case 1://加速
                   //
								    TIM_SetAutoreload(TIM5,period[num]);//设定自动重装值	
							      TIM_SetCompare1(TIM5,period[num]>>1);
                    count[3]++;
										num++;
                    if(count[3]>=ACCELERATED_SPEED_LENGTH)
                    {
                        status=3;
                    }                        
                  break;
              case 3://匀速status=3
                   
							     TIM_SetAutoreload(TIM5,avr_frequency[3]);//设定自动重装值;
							     TIM_SetCompare1(TIM5,avr_frequency[3]>>1);
							     count[3]++;
                     if(count[3]>=abs(location_count[3])-ACCELERATED_SPEED_LENGTH)
                       status=2;     
                   break;
              case 2://减速
                      count[3]++;
                      num--;
									TIM_SetAutoreload(TIM5,period[num]);//设定自动重装值	
									TIM_SetCompare1(TIM5,period[num]>>1);
                    if(count[3]==abs(location_count[3]))
										{  
										 if(motor_dir5==CCW) 						   //如果方向为逆时针   
												current_pos[3]+=count[3];
										 else          							   //否则方向为顺时针
											current_pos[3]-=count[3];			
											TIM_Cmd(TIM5, DISABLE);  				   //关闭TIM2			
									//	printf("motor2当前位置=%ld\r\n",current_pos[0]);//打印输出
											count[3]=0;
											status=1;
									  }
									break;
          
          }
				}
            
    }
	}
}


/***************** 启动TIM8 *****************/
void TIM2_Startup(u32 frequency)   //启动定时器2
{
	 avr_frequency[0]=14000000/frequency-1; 
	
//	TIM_SetAutoreload(TIM2,temp_arr);//设定自动重装值	
	//TIM_SetCompare1(TIM2,temp_arr>>1); //匹配值2等于重装值一半，是以占空比为50%，这个是一半高电平，一半低电平，
	//定时器计数到最高或最低就是产生一个脉冲，脉冲从这里发送到PA1（TIM2_CH2	），占空比越大，输出的电压越大。
	TIM_SetCounter(TIM2,0);//计数器清零
	TIM_Cmd(TIM2, ENABLE);  //使能TIM2
}
void TIM3_Startup(u32 frequency)   
{
	avr_frequency[1]=14000000/frequency-1; 
//	TIM_SetAutoreload(TIM3,temp_arr);
//	TIM_SetCompare1(TIM3,temp_arr>>1); 
	TIM_SetCounter(TIM3,0);
	TIM_Cmd(TIM3, ENABLE);  
}

void TIM4_Startup(u32 frequency)   
{
	avr_frequency[2]=14000000/frequency-1; 
//	TIM_SetAutoreload(TIM4,temp_arr);
//	TIM_SetCompare1(TIM4,temp_arr>>1); 
	TIM_SetCounter(TIM4,0);
	TIM_Cmd(TIM4, ENABLE);  
}

void TIM5_Startup(u32 frequency)   
{
	avr_frequency[3]=14000000/frequency-1; 
//	TIM_SetAutoreload(TIM5,temp_arr);
//	TIM_SetCompare1(TIM5,temp_arr>>1); 
	TIM_SetCounter(TIM5,0);
	TIM_Cmd(TIM5, ENABLE);  
}


/********************************************
//相对定位函数 
//num 0～2147483647
//frequency: 20Hz~100KHz
//dir: CW(顺时针方向)  CCW(逆时针方向)
*********************************************/
void Locate_Rle2(long num,u32 frequency,DIR_Type dir) //相对定位函数
{
	location_count[0]=num;
	if(TIM2->CR1&0x01)//上一次脉冲还未发送完成  直接返回，TIM2->CR1=0x01是使能定时器，
		//上面中断2函数进入后，产生一个脉冲，然后定时器自动关闭，再程序中开启，即TIM2->CR1=0x01
	{
		printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
		return;
	}
	if((frequency<20)||(frequency>100000))//脉冲频率不在范围内 直接返回
	{
		printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	motor_dir2=dir;//将枚举类型为DIR_Type的dir的值赋值给另一个枚举类型motor_dir2，方便在中断中判断motor_dir2是否为正
	//然后在中断中的current_pos[0]进行总和计算出当前的位置
	//finish2=0;//计数未完成
	DRIVER_DIR2=motor_dir2;				 //将旋转方向赋值给DRIVER_DIR2所定义的接口
	TIM2_Startup(frequency);				 //开启TIM2
	
	
}



void Locate_Rle3(long num,u32 frequency,DIR_Type dir) //相对定位函数
{
	
	if(TIM3->CR1&0x01)
	{
		printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
		return;
	}
	if((frequency<20)||(frequency>100000))
	{
		printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	motor_dir3=dir;
	DRIVER_DIR3=motor_dir3;
	TIM3_Startup(frequency);
}



void Locate_Rle4(long num,u32 frequency,DIR_Type dir) //相对定位函数
{
	
	if(TIM4->CR1&0x01)
	{
		printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
		return;
	}
	if((frequency<20)||(frequency>100000))
	{
		printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	motor_dir4=dir;
	DRIVER_DIR4=motor_dir4;
	TIM4_Startup(frequency);
}

void Locate_Rle5(long num,u32 frequency,DIR_Type dir) //相对定位函数
{
	
	if(TIM5->CR1&0x01)
	{
		printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
		return;
	}
	if((frequency<20)||(frequency>100000))
	{
		printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	motor_dir5=dir;
	DRIVER_DIR5=motor_dir5;
	TIM5_Startup(frequency);
}








/********************************************
//绝对定位函数 
//num   -2147483648～2147483647
//frequency: 20Hz~100KHz
*********************************************/
void Locate_Abs2(double angle,u32 speed)//绝对定位函数，左前
{ 
	u32 frequency;
	double ang1;
	int mm;
	
	if(fabs(angle)>0.7*pi)
			return;	
	
	if(angle>=Single_wheel_angle_limit) //左前轮左转受阻
		angle=Single_wheel_angle_limit;
	
	frequency=speed/60*FSPR*M1DIV; //默认取整数
	
	mm=(int)(((angle))/2.0/pi*FSPR*M1DIV*Reduction_ratio);//计算转过的脉冲
	
	
	if(TIM2->CR1&0x01)//上一次脉冲还未发送完成 直接返回
	{
		//	printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
			return;
	}
	if((frequency<20)||(frequency>512000))//脉冲频率不在范围内 直接返回
	{
		//printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	
	target_pos[0]=mm;//设置目标位置
	
	if(target_pos[0]!=current_pos[0])//目标和当前位置不同
	{	
			if(target_pos[0]>current_pos[0])
						{	motor_dir2=CCW;//逆时针	
						}
				else
				{
						motor_dir2=CW;//顺时针
				}
				DRIVER_DIR2=motor_dir2;//设置方向
			
				location_count[0]=target_pos[0]-current_pos[0];
				
				TIM2_Startup(frequency);//开启TIM8
	}
	
	
//	if((target_pos[0]==current_pos[0]))//目标和当前位置相同	,同时处于原点位置时候//开启矫正||(fabs(angle)<0.1)
//	{	
//		
//		ang1=(AD_get(0)/4096.0*2.0*pi-Angle_Init[0]);
//		if(fabs(angle-ang1)>M1_correct_erro)//如果误差大于1度
//		{	
//			target_pos[0]=(int)(ang1/2.0/pi*200.0*M1DIV);
//		   current_pos[0]=target_pos[0];
//		}
//	}
	
}


void Locate_Abs3(double angle,u32 speed)//绝对定位函数  ，左后
{ 
	u32 frequency;
	double ang2;
	int mm;
	
	if(fabs(angle)>0.7*pi)
			return;	
	
	if(angle<=(-Single_wheel_angle_limit)) //左后轮右转受阻，此时angle为负值
	angle=-Single_wheel_angle_limit;
	
	frequency=speed/60*FSPR*M2DIV; //默认取整数
	
	mm=(int)(((angle))/2.0/pi*FSPR*M2DIV*Reduction_ratio);//计算转过的脉冲
	
	if(TIM3->CR1&0x01)//上一次脉冲还未发送完成 直接返回
	{
		//	printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
			return;
	}
	if((frequency<20)||(frequency>512000))//脉冲频率不在范围内 直接返回
	{
		//printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	
	target_pos[1]=mm;//设置目标位置
	
	if(target_pos[1]!=current_pos[1])//目标和当前位置不同
	{
				if(target_pos[1]>current_pos[1])
						{	motor_dir3=CCW;//逆时针	
						}
				else
				{
						motor_dir3=CW;//顺时针
				}
				DRIVER_DIR3=motor_dir3;//设置方向
			
				location_count[1]=target_pos[1]-current_pos[1];
				
				TIM3_Startup(frequency);//开启TIM8
	}
	
//	if(target_pos[1]==current_pos[1])//目标和当前位置相同	//开启矫正
//	{	
//		
//		ang2=(AD_get(2)/4096.0*2.0*pi-Angle_Init[1])/2.0/pi*200.0*M2DIV;
//		if(fabs(angle-ang2)>M2_correct_erro)//如果误差大于1度
//		{	
//			target_pos[1]=(int)(ang2);
//			current_pos[1]=target_pos[1];
//		}
//  }
	
}

void Locate_Abs4(double angle,u32 speed)//绝对定位函数，右前
{ 
	u32 frequency;
	double ang3;
	int mm;
	
	if(fabs(angle)>0.7*pi)
			return;	
	if(angle<=(-Single_wheel_angle_limit)) //右前轮右转受阻，此时angle为负值
	angle=-Single_wheel_angle_limit;
	
	frequency=speed/60*FSPR*M3DIV; //默认取整数
	
	mm=(int)(((angle))/2.0/pi*FSPR*M3DIV*Reduction_ratio);//计算转过的脉冲
	
	if(TIM4->CR1&0x01)//上一次脉冲还未发送完成 直接返回
	{
		//	printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
			return;
	}
	if((frequency<20)||(frequency>512000))//脉冲频率不在范围内 直接返回
	{
		//printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	
	target_pos[2]=mm;//设置目标位置
	
	if(target_pos[2]!=current_pos[2])//目标和当前位置不同
	{
				if(target_pos[2]>current_pos[2])
						{	motor_dir4=CCW;//逆时针	
						}
				else
				{
						motor_dir4=CW;//顺时针
				}
				DRIVER_DIR4=motor_dir4;//设置方向
			
				location_count[2]=target_pos[2]-current_pos[2];
				
				TIM4_Startup(frequency);//开启TIM8
	}
	
//	if(target_pos[2]==current_pos[2])//目标和当前位置相同	//开启矫正
//	{	
//		
//		ang3=(AD_get(1)/4096.0*2.0*pi-Angle_Init[2])/2.0/pi*200.0*M3DIV;
//		if(fabs(angle-ang3)>M3_correct_erro)//如果误差大于1度
//		{	
//			target_pos[2]=(int)(ang3);
//			current_pos[2]=target_pos[2];
//		}
//}
	
}

void Locate_Abs5(double angle,u32 speed)//绝对定位函数，右后
{ 
	u32 frequency;
	double ang4;
	int mm;
	
	if(fabs(angle)>0.7*pi)
			return;	
	
	if(angle>=Single_wheel_angle_limit) //右后轮左转受阻
		angle=Single_wheel_angle_limit;
	
	frequency=speed/60*FSPR*M4DIV; //默认取整数
	
	mm=(int)(((angle))/2.0/pi*FSPR*M4DIV*Reduction_ratio);//计算转过的脉冲
	
	if(TIM5->CR1&0x01)//上一次脉冲还未发送完成 直接返回
	{
		//	printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
			return;
	}
	if((frequency<20)||(frequency>512000))//脉冲频率不在范围内 直接返回
	{
		//printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
	
	target_pos[3]=mm;//设置目标位置
	
	if(target_pos[3]!=current_pos[3])//目标和当前位置不同
	{
				if(target_pos[3]>current_pos[3])
						{	motor_dir5=CCW;//逆时针	
						}
				else
				{
						motor_dir5=CW;//顺时针
				}
				DRIVER_DIR5=motor_dir5;//设置方向
			
				location_count[3]=target_pos[3]-current_pos[3];
				
				TIM5_Startup(frequency);//开启TIM8
	}
	
//	if(target_pos[3]==current_pos[3])//目标和当前位置相同	//开启矫正
//	{	
//		
//		ang4=(AD_get(3)/4096.0*2.0*pi-Angle_Init[3])/2.0/pi*200.0*M4DIV;
//		if(fabs(angle-ang4)>M4_correct_erro)//如果误差大于1度
//		{	
//			target_pos[3]=(int)(ang4);
//			current_pos[3]=target_pos[3];
//		}
//}
	
}



void location_angle(u8 motor,double angle,u32 speed ) // 0左前，1右前，2左后，3右后	
{
if(motor==0) 
	Locate2(angle,speed);
if(motor==1)
	Locate_Abs4(angle,speed);
if(motor==2)
	Locate_Abs3(angle,speed);
if(motor==3)
	Locate_Abs5(angle,speed);


}



void Locate2(double angle,u32 speed)//绝对定位函数，左前
{ static double angle_last;
	u32 frequency;
	double ang1;
	int mm;
	if(fabs(angle-angle_last)<0.08)
			return;	
	
	angle_last=angle;
	if(fabs(angle)>0.7*pi)
			return;	
	
	if(angle>=Single_wheel_angle_limit) //左前轮左转受阻
		angle=Single_wheel_angle_limit;
	
	frequency=speed/60*FSPR*M1DIV; //默认取整数
	
	
	if(TIM2->CR1&0x01)//上一次脉冲还未发送完成 直接返回
	{
		//	printf("\r\nThe last time pulses is not send finished,wait please!\r\n");
			return;
	}
	if((frequency<20)||(frequency>512000))//脉冲频率不在范围内 直接返回
	{
		//printf("\r\nThe frequency is out of range! please reset it!!(range:20Hz~100KHz)\r\n");
		return;
	}
////////////	

ang1=(AD_get(0)/4096.0*2.0*pi-Angle_Init[0]);//读取当前角度与初始角度的差值
mm=(int)(((angle-ang1))/2.0/pi*FSPR*M1DIV*Reduction_ratio);//计算转过的脉冲	

if(abs(mm)>M1_locate_erro)	
{
				if(mm>0)
				{	
					motor_dir2=CCW;//逆时针	
				}
				else
				{
					mm=-mm;
					motor_dir2=CW;//顺时针
				}
				DRIVER_DIR2=motor_dir2;//设置方向
			
				location_count[0]=mm;
				
				TIM2_Startup(frequency);//开启TIM8


}


	
}




double angle_calculate(u8 adress,double goal_angle,double AD_angle)
{
	static double angle_last;
	double angle_erro;
	if(adress==0)//左前
	{
//			if(fabs(goal_angle-angle_last)<goal_hand_erro) //人手抖以及计算产生的误差
//					return;	
			angle_last=goal_angle;
			if(fabs(goal_angle)>0.7*pi) //目标发送错误
					return 0.0;	
			
			if(goal_angle>=Single_wheel_angle_limit) //左前轮左转受阻
				goal_angle=Single_wheel_angle_limit;

			angle_erro=goal_angle-(AD_angle-Angle_Init[0]);//读取当前角度与初始角度的差值
      	
			if(fabs(angle_erro)<M1_correct_erro)
					return 0.0;
			return angle_erro;
			
			
	}

		if(adress==1)//右前
	{
	
	//			if(fabs(goal_angle-angle_last)<goal_hand_erro) //人手抖以及计算产生的误差
//					return;	
			angle_last=goal_angle;
			if(fabs(goal_angle)>0.7*pi) //目标发送错误
					return 0.0;	

				if(goal_angle<=(-Single_wheel_angle_limit)) //右前轮右转受阻，此时angle为负值
	     goal_angle=-Single_wheel_angle_limit;
			
			
			angle_erro=goal_angle-(AD_angle-Angle_Init[1]);//读取当前角度与初始角度的差值
      	
			if(fabs(angle_erro)<M1_correct_erro)
					return 0.0;
			return angle_erro;
		
		
		
		
	}
		if(adress==2)//左后
	{
	//			if(fabs(goal_angle-angle_last)<goal_hand_erro) //人手抖以及计算产生的误差
//					return;	
			angle_last=goal_angle;
			if(fabs(goal_angle)>0.7*pi) //目标发送错误
					return 0.0;	
			
				if(goal_angle<=(-Single_wheel_angle_limit)) //左后轮右转受阻，此时angle为负值
	    goal_angle=-Single_wheel_angle_limit;
	
			
			
			angle_erro=goal_angle-(AD_angle-Angle_Init[2]);//读取当前角度与初始角度的差值
      	
			if(fabs(angle_erro)<M1_correct_erro)
					return 0.0;
			return angle_erro;
	
	}
		if(adress==3)//右后
	{
	//			if(fabs(goal_angle-angle_last)<goal_hand_erro) //人手抖以及计算产生的误差
//					return;	
			angle_last=goal_angle;
			if(fabs(goal_angle)>0.7*pi) //目标发送错误
					return 0.0;	
	if(goal_angle>=Single_wheel_angle_limit) //右后轮左转受阻
		goal_angle=Single_wheel_angle_limit;
	
			angle_erro=goal_angle-(AD_angle-Angle_Init[3]);//读取当前角度与初始角度的差值
      	
			if(fabs(angle_erro)<M1_correct_erro)
					return 0.0;
			return angle_erro;
	
	}

}
	










