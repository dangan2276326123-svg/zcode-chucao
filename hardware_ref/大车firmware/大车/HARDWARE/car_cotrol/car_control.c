#include "car_control.h"
#include "pwm.h"
#include "usart.h"
#include "stdio.h"
#include "delay.h"
#include "path_plan.h"
extern double  freq_time[6];
extern double veloc[4];	
extern double control_flag[5];
struct{
    float set_speed;//设定速度 
    float actual_speed;//实际速度
    float error;//偏差  
    float error_next;//上一个偏差  
    float error_last;//上上一个偏差 
    float kp,ki,kd;   
   }pid;  
void pid_init(void)
{
    pid.set_speed = 0;
    pid.actual_speed = 0.0;
    pid.error = 0.0;
    pid.error_next = 0.0;
    pid.error_last = 0.0;
    pid.kp =1;//10
    pid.ki = 0.1;//0.2
    pid.kd = 0;
}
float pid_realise(float speed,double capture)  
{
//	static u8 kk=0;
		float increment_speed;//增量

	Ch_Cap();
	pid.set_speed = speed;//设置目标速度  
//	pid.error = pid.set_speed - pid.actual_speed;
	pid.error = pid.set_speed - capture;

	increment_speed = pid.kp*(pid.error-pid.error_next)+pid.ki*pid.error+pid.kd*(pid.error-2*pid.error_next+pid.error_last);  
	pid.actual_speed+= increment_speed;

	pid.error_last = pid.error_next; 
	pid.error_next = pid.error;
	if (pid.actual_speed > 10) pid.actual_speed = 10;                              
	if (pid.actual_speed < -10) pid.actual_speed= -10;
 
//		if(kk++==30)
//	{
//		printf("pid.error:%f r/min\r\n",pid.error);	
//	  printf("pid.actual_speed:%f r/min\r\n",pid.actual_speed);	
//		printf("zengliang:%f r/min\r\n",increment_speed);	
//		kk=0;
//	}
		return pid.actual_speed; 
}

void Test_Out_Pwm(void)
{		
	static u8 kk=0;
//	static double bb,cc;
	
  Ch_Cap();
	pid_init();
//  bb=;
//	cc=167*bb;
	TIM8->CCR2=167*(1.2+pid_realise(1.2,freq_time[3]));
//	if(TIM8->CCR2>0) PGout(2)=1;//方向;
//	else 
//		PGout(2)=0;
	if(kk++==30)
	{
  	printf("L_R:%lf m/s\r\n",freq_time[3]); //打印总的高电平时间
//		printf("pid.error:%lf m/s\r\n",pid.error);
		kk=0;
	}
}
void Out_Pwm(void)
{
	pid_init();
	if((veloc[0]>=0.0)&&(veloc[1]>=0.0)&&(veloc[2]>=0.0)&&(veloc[3]>=0.0))//左前 右前 左后 右后 正对着油箱往前行驶
//	if(control_flag[1]>=0.0)
	{
		Roll_LF_En=1;Roll_LR_En=1;Roll_RF_En=1;Roll_RR_En=1;
		Roll_LF_Dr=1;Roll_LR_Dr=1;Roll_RF_Dr=0;Roll_RR_Dr=0;
		Roll_LF_BK=1;Roll_LR_BK=1;Roll_RF_BK=1;Roll_RR_BK=1;
		
		TIM8->CCR1=167*(veloc[0]+pid_realise(veloc[0],freq_time[2]));//左前
		TIM8->CCR2=167*(veloc[2]+pid_realise(veloc[2],freq_time[3]));//左后
		TIM8->CCR3=167*(veloc[1]+pid_realise(veloc[1],freq_time[4]));//右前
		TIM8->CCR4=167*(veloc[3]+pid_realise(veloc[3],freq_time[5]));//右后
	}
	//else
	else if((veloc[0]<0.0)&&(veloc[1]<0.0)&&(veloc[2]<0.0)&&(veloc[3]<0.0))
	
	{
		Roll_LF_En=1;Roll_LR_En=1;Roll_RF_En=1;Roll_RR_En=1;
		Roll_LF_Dr=0;Roll_LR_Dr=0;Roll_RF_Dr=1;Roll_RR_Dr=1;
		Roll_LF_BK=1;Roll_LR_BK=1;Roll_RF_BK=1;Roll_RR_BK=1;
		
		veloc[0]=-veloc[0];veloc[1]=-veloc[1];veloc[2]=-veloc[2];veloc[3]=-veloc[3];
		TIM8->CCR1=167*(veloc[0]+pid_realise(veloc[0],freq_time[2]));//左前
		TIM8->CCR2=167*(veloc[2]+pid_realise(veloc[2],freq_time[3]));//左后
		TIM8->CCR3=167*(veloc[1]+pid_realise(veloc[1],freq_time[4]));//右前
		TIM8->CCR4=167*(veloc[3]+pid_realise(veloc[3],freq_time[5]));//右后	
	}
	else
	{
		if(veloc[0]>=0&&veloc[1]<0&&veloc[2]>=0&&veloc[3]<0)//左前 右前 左后 右后
		{
				Roll_LF_En=1;Roll_LR_En=1;Roll_RF_En=1;Roll_RR_En=1;
				Roll_LF_Dr=1;Roll_LR_Dr=1;Roll_RF_Dr=1;Roll_RR_Dr=1;
				veloc[0]=veloc[0];veloc[1]=-veloc[1];veloc[2]=veloc[2];veloc[3]=-veloc[3];
		}
		if(veloc[0]<0&&veloc[1]>=0&&veloc[2]<0&&veloc[3]>=0)//左前 右前 左后 右后
		{
				Roll_LF_En=1;Roll_LR_En=1;Roll_RF_En=1;Roll_RR_En=1;
				Roll_LF_Dr=0;Roll_LR_Dr=0;Roll_RF_Dr=0;Roll_RR_Dr=0;
				veloc[0]=-veloc[0];veloc[1]=veloc[1];veloc[2]=-veloc[2];veloc[3]=veloc[3];
		}	
			Roll_LF_BK=1;Roll_LR_BK=1;Roll_RF_BK=1;Roll_RR_BK=1;
		
			TIM8->CCR1=167*(veloc[0]+pid_realise(veloc[0],freq_time[2]));//左前
			TIM8->CCR2=167*(veloc[2]+pid_realise(veloc[2],freq_time[3]));//左后
			TIM8->CCR3=167*(veloc[1]+pid_realise(veloc[1],freq_time[4]));//右前
			TIM8->CCR4=167*(veloc[3]+pid_realise(veloc[3],freq_time[5]));//右后
	}
	
	
	
	
	
}


