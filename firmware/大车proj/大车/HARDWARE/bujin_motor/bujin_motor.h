#ifndef __BUJIMOTOR_H
#define __BUJIMOTOR_H
#include "sys.h"


#define MIN(a,b) (a<b) ? (a) : (b)
#define MAX(a,b) (a>b) ? (a) : (b)
#define rt_int8_t	   int8_t
#define rt_int16_t	   int16_t
#define rt_int32_t	   int32_t

#define rt_uint8_t	   uint8_t
#define rt_uint16_t	   uint16_t
#define rt_uint32_t	   uint32_t

#define IDLE						0
#define ACCELERATING		1
#define AT_MAX					2
#define DECELERATING		3

typedef __packed struct 
{
 unsigned char en;	          //使能
 unsigned char dir;			  		//方向
 unsigned char running;		  		//转动完成标志 
 unsigned char rstflg;		  	//复位标志
 unsigned char divnum;		  	//分频数
 unsigned char speedenbale;		//是否使能速度控制	
 unsigned char clockwise;			//顺时针方向对应的值
 unsigned char id;					//电机id
 
 uint32_t pulsecount;
 uint16_t *Counter_Table;  		//指向启动时，时间基数计数表
 uint16_t *Step_Table;  			//指向启动时，每个频率脉冲个数表
 uint16_t CurrentIndex;    	//当前表的位置
 uint16_t TargetIndex;    	//目标速度在表中位置
 uint16_t StartTableLength;   //启动数据表
 uint16_t StopTableLength;    //启动数据表
 uint32_t StartSteps;					//电机启动步数
 uint32_t StopSteps;					//电机停止步数
 uint32_t RevetDot;			  		//电机运动的减速点
 uint32_t PulsesGiven;			  //电机运动的总步数
 uint32_t PulsesHaven;				//电机已经运行的步数
 uint32_t CurrentPosition;		//当前位置
 uint32_t MaxPosition;				//最大位置，超过该位置置0
 uint32_t CurrentPosition_Pulse;		//当前位置
 uint32_t MaxPosition_Pulse;		//当前位置
 unsigned long long Time_Cost_Act;	//实际运转花费的时间
 unsigned long long Time_Cost_Cal;	//计算预估运转花费的时间
 TIM_TypeDef* TIMx;	
} MOTOR_CONTROL_S ;

typedef __packed struct 
{
	unsigned char en;	          		//使能
	unsigned char dir;			  			//方向
	unsigned char running;		  		//转动完成标志
	unsigned char rstflg;		  			//复位标志，为1时，限位开关强停。
	unsigned char divnum;		  			//分频数	 
	unsigned char speedenbale;		//是否使能速度控制	
  unsigned char clockwise;			//顺时针方向对应的值
  unsigned char id;							//电机id	

	uint32_t PulsesGiven;			  		//电机运动的总步数
	uint32_t PulsesHaven;						//电机已经运行的步数
	uint32_t step_move     ;				//total move requested
	uint32_t step_spmax    ;				//maximum speed
	uint32_t step_accel    ;				//accel/decel rate, 8.8 bit format
	uint32_t step_acced    ;				//steps in acceled stage

	uint32_t step_middle   ;				//mid-point of move, = (step_move - 1) >> 1
	uint32_t step_count    ;				//step counter
	uint32_t step_frac     ;				//step counter fraction
	uint32_t step_speed    ;				//current speed, 16.8 bit format (HI byte always 0)
	uint32_t speed_frac    ;				//speed counter fraction
	uint8_t step_state    ;					//move profile state
	uint8_t step_dur      ;					//counter for duration of step pulse HI

	uint32_t CurrentPosition;					//当前位置
	uint32_t MaxPosition;							//最大位置，超过该位置置0
	uint32_t CurrentPosition_Pulse;		//当前位置
	uint32_t MaxPosition_Pulse;				//当前位置
 
	TIM_TypeDef* TIMx;	
	GPIO_TypeDef * GPIOBASE;
	int32_t PWMGPIO;
} MOTOR_CONTROL_SPTA ;

#define M1_CLOCKWISE					0
#define M1_UNCLOCKWISE				1
#define M2_CLOCKWISE					0
#define M2_UNCLOCKWISE				1
#define M3_CLOCKWISE					0
#define M3_UNCLOCKWISE				1
#define M4_CLOCKWISE					0
#define M4_UNCLOCKWISE				1


//定义的中断优先级
#define PWM1_PreemptionPriority 1             //阶级
#define PWM1_SubPriority 0					//阶层
#define PWM2_PreemptionPriority 1             //阶级
#define PWM2_SubPriority 1					//阶层
#define PWM3_PreemptionPriority 2             //阶级
#define PWM3_SubPriority 0					//阶层
#define PWM4_PreemptionPriority 2             //阶级
#define PWM4_SubPriority 1					//阶层
/***********************END********************************************/

#define M1DIV               128   //定义电机1的细分数
#define M2DIV               32   //定义电机2的细分数
#define M3DIV               32   //定义电机3的细分数
#define M4DIV               32   //定义电机4的细分数

#define M_FRE_START					10000 //电机的启动频率
#define M_FRE_AA						6000	//电机频率的加加速度
#define M_T_AA							2			//电机频率的加加速时间
#define M_T_UA							6     //电机频率的匀加速时间
#define M_T_RA							2		  //电机频率的减加速时间 




//电机
//extern MOTOR_CONTROL_S motor1;
//extern MOTOR_CONTROL_S motor2;
//extern MOTOR_CONTROL_S motor3;
//extern MOTOR_CONTROL_SPTA motor4; 






/*重新初始化电机运行时相关参数*/
void Motor_Reinitial(unsigned char MotorID);

void Initial_MotorIO(void);
void Initial_Motor(unsigned char MotorID, unsigned char StepDive,unsigned int maxposition);
void MotorRunParaInitial(void);
void Start_Motor12(unsigned char dir1,unsigned int Degree1,unsigned char dir2,unsigned int Degree2);
void Start_Motor_S(unsigned char MotorID,unsigned char dir,unsigned int Degree);
void Start_Motor_SPTA(unsigned char MotorID,unsigned char dir,unsigned int Degree);
void SetSpeed(unsigned char MotorID, signed char speedindex);
void Do_Reset(unsigned char MotorID);
void Deal_Cmd(void);
void Initial_PWM_Motor1(void);//motor1 PA15
void Initial_PWM_Motor2(void);//motor1 PB4
void Initial_PWM_Motor3(void);//motor1 PB6
void Initial_PWM_Motor4(void);//motor1 PA0
void EXTI_Configuration(void);

void bujin_motor_PWM_Init(void);


//电机运行参数初始化*/
void MotorRunParaInitial(void);

 /*计算S型曲线算法的每一步定时器周期及步进数*/
void CalcMotorPeriStep_CPF(float fstart,float faa,float taa,float tua,float tra,uint16_t MotorTimeTable[],uint16_t MotorStepTable[]);

/*计算S型曲线反转点，S型曲线在运行时，加减速过程是完全对称的*/
unsigned long long Get_TimeCost_ReverDot_S(unsigned char MotorID);



//		TIM_SetCompare1(TIM2,speed);
//		TIM_SetCompare1(TIM3,speed);
//		TIM_SetCompare1(TIM4,speed);
//		TIM_SetCompare1(TIM5,speed);

//			replay_switch(10,1);//正向
//			replay_switch(11,1);//正向
//			replay_switch(12,1);//正向
//			replay_switch(15,1);//正向
//			
//			replay_switch(10,0);//PE0=0,反向
//			replay_switch(11,0);//PE0=0,反向
//			replay_switch(12,0);//PE0=0,反向
//			replay_switch(15,0);//PE0=0,反向

#endif




