#ifndef __PATH_PLAN_H
#define __PATH_PLAN_H
#include "sys.h"

#define  pi 3.1415926535
//
//#define velocity_limit_angle 1.0   /// 转角过大时 对速度进行限制
//double velocity_limit_angle =1.3;
// #define angle_limit 45.5/180.0*pi //单位弧度
//#define veloc_limit 	1.26	//单位m/s·1



void telecontrol_anazye_little(void);//解析遥控命令


void path_plan(void);		//flag为转向方式,direction为解析的方向角度的大小，velocity为解析的速度的大小

void work_equipment_control(void);//作业机构控制
void telecontrol(void);//遥控器遥控


//void path_four_wheel(double direction,double velocity);			//四轮相对转向方式
//void path_diagonal(double direction,double velocity);				//斜行转向方式
//void path_only_front(double direction,double velocity);			//只用前轮转向

//void path_only_front2(double direction,double velocity);			//只用前轮转向，带差速
//void path_only_front3(double direction,double velocity);			//只用前轮转向，带差速

//void path_only_rear(double direction,double velocity);			//只用后轮转向
//void path_crab_row(double direction,double velocity);				//蟹形横向移动



//void path_only_two_synchronization(double direction,double velocity);			////两轮并联时,只用前轮阿克曼转向,转角相同，但车速仍为差速
//void path_four_wheel_synchronization(double direction,double velocity);			////两轮并联时,四轮相对转向方式,转角相同，但车速仍为差速
//void new_path_crab_row( double direction,double velocity)	;		//新的打药横向转向

////////////////////
void limit_angle_veloc(void);// 用于限制每个车轮的转角和速度
void ackman_steering_front(double direction,double velocity);// 新的前轮转向
void ackman_steering_rear(double direction,double velocity);// 新的后轮转向
void four_Relative_front(double direction,double velocity);// 新的四轮相对转向
void four_Relative_rear(double direction,double velocity);// 新的四轮相对转向
void path_diagonal_front(double direction,double velocity);			//斜行转向方式,不是理论的高速斜行,只是为了斜行
void path_diagonal_rear(double direction,double velocity);			//斜行转向方式,不是理论的高速斜行,只是为了斜行
void path_circle_around(double direction,double velocity);	//原地转向

//PB8左转  PD0 右转
//PB5前进  PA15 后退
//#define left 				PBin(8)   	//PE4
//#define right 			PDin(0)		//PE3 
//#define forword 		PBin(5)		//P32
//#define back 				PAin(15)		//PA0


//#define  pi 3.1415926535
#endif
