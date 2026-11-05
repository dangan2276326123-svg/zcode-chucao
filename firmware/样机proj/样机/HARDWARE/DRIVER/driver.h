#ifndef __DRIVER_H
#define __DRIVER_H
#include "sys.h"
#include "stdlib.h"	


/********** 驱动器 端口定义 **************
//DRIVER_DIR   PA8 
//DRIVER_OE    PA11 
//STEP_PULSE   PA1 (TIM2_CH2)
******************************************/
#define DRIVER_DIR2   PEin(10) // 旋转方向 ,左前
//#define DRIVER_OE2    PAout(11) // 使能脚 低电平有效

#define DRIVER_DIR3   PEin(11) // 旋转方向 
//#define DRIVER_OE3    PAout(5) // 使能脚 低电平有效

#define DRIVER_DIR4   PEin(12) // 旋转方向 
//#define DRIVER_OE4    PAout(11) // 使能脚 低电平有效

#define DRIVER_DIR5   PEin(15) // 旋转方向 
//#define DRIVER_OE5    PAout(5) // 使能脚 低电平有效

#define FSPR         200         //步进电机单圈最低步数

#define M1DIV               64   //定义电机1的细分数200的多少倍，如25600，则M1DIV=128, 如400，则M1DIV=2,
#define M2DIV               64   //定义电机2的细分数
#define M3DIV               64   //定义电机3的细分数
#define M4DIV               64   //定义电机4的细分数

#define M1_correct_erro               0.05  //定义电机1的角度纠正容忍误差，防止因传感器采集误差造成一直抖动，弧度0.0175为1度
#define M2_correct_erro               0.1   //定义电机2的角度纠正容忍误差，防止因传感器采集误差造成一直抖动
#define M3_correct_erro               0.1   //定义电机3的角度纠正容忍误差，防止因传感器采集误差造成一直抖动
#define M4_correct_erro               0.1   //定义电机4的角度纠正容忍误差，防止因传感器采集误差造成一直抖动

#define goal_hand_erro               0.02   //定义电机4的角度纠正容忍误差，防止因传感器采集误差造成一直抖动


#define M1_locate_erro               10844  //定义电机1的角度纠正容忍误差，防止因传感器采集误差造成一直抖动，1度
#define M2_locate_erro               0.1   //定义电机2的角度纠正容忍误差，防止因传感器采集误差造成一直抖动
#define M3_locate_erro               0.1   //定义电机3的角度纠正容忍误差，防止因传感器采集误差造成一直抖动
#define M4_locate_erro               0.1   //定义电机4的角度纠正容忍误差，防止因传感器采集误差造成一直抖动


#define Reduction_ratio    80  //定义电机减速比
#define Single_wheel_angle_limit               0.7      //44.69度  定义车轮转向的机械极限角度
#define speed_motor_max    400  //定义电机最大速度 r/min   转/分


/* S型加速参数 */
//注意目前细分均为12800 
#define ACCELERATED_SPEED_LENGTH 8200  //定义加速度的点数（其实也是3000个细分步的意思），调这个参数改变加速点,一般电机加速1.5圈，越大加速越慢
#define FRE_MIN 1280  //最低的运行频率，调这个参数调节最低运行速度最低速度0.1r/s,
#define FRE_MAX 85333 //最高的运行频率，调这个参数调节匀速时的最高速度35000 ，最高10r/s,即600r/min，128000  ，400r/min  85333


#define STOP                                  0 // 加减速曲线状态：停止
#define ACCEL                                 1 // 加减速曲线状态：加速阶段
#define DECEL                                 2 // 加减速曲线状态：减速阶段
#define RUN                                   3 // 加减速曲线状态：匀速阶段


typedef enum
{
	CW = 1,//高电平顺时针
	CCW = 0,//低电平逆时针
}DIR_Type;  //定义枚举类型为DIR_Type 可看作为u16这种，例如 DIR_Type dir,上面CW,CCW都是常量，
//不能对它们赋值，只能将它们的值赋给其他的变量。

extern long current_pos[4];//有符号方向

void Driver_Init(void);//驱动器初始化
void TIM2_Init(u16 arr,u16 psc);//TIM2_CH1 
void TIM3_Init(u16 arr,u16 psc);//TIM3_CH1 
void TIM4_Init(u16 arr,u16 psc);//TIM4_CH1 
void TIM5_Init(u16 arr,u16 psc);//TIM5_CH1 

void TIM2_Startup(u32 frequency);   //启动定时器2
void TIM3_Startup(u32 frequency);   //启动定时器3
void TIM4_Startup(u32 frequency);   //启动定时器4
void TIM5_Startup(u32 frequency);   //启动定时器5
void Locate_Rle2(long num,u32 frequency,DIR_Type dir); //相对定位函数2
void Locate_Rle3(long num,u32 frequency,DIR_Type dir); //相对定位函数3
void Locate_Rle4(long num,u32 frequency,DIR_Type dir); //相对定位函数2
void Locate_Rle5(long num,u32 frequency,DIR_Type dir); //相对定位函数3


void bujin_motor_PWM_Init(u16 arr,u16 psc);

void location_angle(u8 motor,double angle,u32 speed ); // 0左前，1右前，2左后，3右后
void Locate_Abs2(double angle,u32 speed);//绝对定位函数
void Locate_Abs3(double angle,u32 speed);//绝对定位函数
void Locate_Abs4(double angle,u32 speed);//绝对定位函数
void Locate_Abs5(double angle,u32 speed);//绝对定位函数


void Locate2(double angle,u32 speed);//绝对定位函数，左前


void CalculateSModelLine( float len, float fre_max, float fre_min, float flexible);
double angle_calculate(u8 adress,double goal_angle,double AD_angle);
#endif


