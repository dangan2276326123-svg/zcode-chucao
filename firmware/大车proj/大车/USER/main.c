#include "sys.h"
#include "delay.h"
#include "usart.h"
#include "led.h"
#include "pwm.h"
#include "telecontrol.h"
//#include "lcd.h"
#include "retrofit.h"
#include "path_plan.h"
#include "math.h"
#include "car_control.h"
//#include "can.h"
#include "adc.h"
#include "uart2.h"	
#include "uart5.h"	                
#include "uart4.h"	
#include "uart3.h"
#include "driver.h"
#include "iwdg.h"
#include "iic.h"
#include "exti.h"

// 角度传感器安装方向（上或下）
// 组别问题（左右一组，前后一组，必须按照顺序来，不再改变）

//车辆参数  轮轴 和轮距离
double B=1530.0; //车宽 mm
double L=2550.0;  //车长 mm
double B_Horizontal=2780.0; //车宽 mm
double L_Horizontal=1390.0;  //车长 mm


double veloc_limit_low =1.24;  //对应的满p波 尽量与实际相符  满p波与最高速的比例关系    这个是默认中速 还有高低速
double veloc_limit_middle =1.5;  //对应的满p波 尽量与实际相符  满p波与最高速的比例关系    这个是默认中速 还有高低速
double veloc_limit_high =1.74;  //对应的满p波 尽量与实际相符  满p波与最高速的比例关系    这个是默认中速 还有高低速

double veloc_actual=0.30;
double veloc_limit =1.24;  //对应的满p波 尽量与实际相符  满p波与最高速的比例关系    这个是最终值，不需要改变
double angle_limit=60.5/180.0*pi; ////控制角度限幅值，无需改变，自己运算  仅适用于双轮转向、斜行、相对转向模式  默认为（）


double angle_limit_single=65.5/180.0*pi; //单个车轮角度限幅值，可以更改


//传动比
double transmission_ratio_drive=5.5*2.0 ;// 行走电机传动比
double transmission_ratio_steer=50.0*8.0;//  伺服电机到车轮 50.0*5.5  快速车

double sensor_ratio=1.0;//  转向编码器以及电位计与转轴之间的传动比\

int ultrasonic_1=0,ultrasonic_2=0,ultrasonic_3=0,ultrasonic_4=0; //四路超声波的数值

//  转向限制标志位
u8 flag_steer_limit=0; // 是否有转向机械限位 0 没有 1有
double wheel_angle_limit=35.5/180.0*pi; //  如果有机械限位的话，限制是多少度
// 刹车电流检测对应的电压

// 角度传感器型号标志位
u8 flag_sensor=1; // 0是电位计 1是绝对值编码器
// 遥控器型号标志位
u8 flag_remote_control=1; // 0是航模遥控器 1是单手遥控器 2 是车模遥控器

// 转向方式标志位（绝对值转向还是增量式转向）
u8 flag_Steering_mode=1; // 0是绝对值式 1增量式

//增量式转向每次增的度数    
double angle_add=0.8*0.0175; //0.0175是1度，1.0中的 0不能省略   如果出现顿挫，加大这个数字

//转向电机默认转速设置
int steer_motor_speed=6000;

// 车辆模型。遥控器方式，通过拨码器进行设置
u8 flag_car_mode=0; // 0是四轮全能转向+航模 1是四轮有限位+航模 2是四轮有限位+车模 3是四轮有限位+单手遥控 4是双轮有限位+航模 5是双轮有限位+单手遥控 
 

// 是否进行避障号标志位  0不开启 1开启
u8 Obstacle_avoidance_flag=0,Obstacle_avoidance_flag_only=0; 
//电池电量低，报警清除标志位
u8 battery_voltage_flag_only=1;

//调整轴距标志位
u8 Adjusting_wheelbase=0; 

// 是否进行刹车保护标志位  0不开启 1开启
u8 Brake_protection_flag=0; 

float Brake_protection_value=2.3; //为单个刹车的电流

 
//所有的方向都是左正右负 角度为弧度单位  车速是米每秒  
int main(void)
{ 
	

  //double wheel_Angle_Init[4]={0,0,0,0};
  double wheel_Angle_Init[4]={3.1415926,3.1415926,3.1415926,3.1415926};	//左前3.99 右前2.50 左后 2.44 右后3.95;//四个轮子的初始值	，同步时两前轮相同两后轮相同  上位机要保存和修改的就是这个数
  double wheel_angle_limit=0.420;     //2.5度  定义车轮转向的机械极限角度 0.0175    25         
	
  extern u8 mp3_flag,mp3_flag_last,mp3_time,mp3_other;// 音乐播放类型、播放时间控制
	extern double Switch_direction;
  extern double control_flag[6];//0行驶还是停车，1前进还是后退，2转向方式，3角度值，4速度值，5作业机构是否起降  //*****************
	extern int sbus_channel[16];//解析后的通道数据            具体的各个位代表什么                           //**********************
	extern double veloc[4];	//每个车轮的转速                                                                   //*******************
	extern double angle[4];//每个车轮的转角                                                                      //***************
	extern u8 LOCK_FLAG; //遥控器锁	
	extern double battery_voltage,stop_voltage,base_voltage,control_voltage; //定义电池电压 刹车电压 基准电压  遥控器电压
	                     //************
	extern unsigned char regGroup[16]; //上位机接管数据
	extern u16 flag_sbus;
	int i=0,t,count,j,stop,stop_count,upload_count,only_start=0,stop_voltage_count=0;
	int shacheccr = 490;
	
	extern double AD_angle[4];//四个轮子的采集值  0左前，1右前，2左后，3右后                                         //**************
	double wheel_Angle_correct[4]={0,0,0,0};  // 0左前，1右前，2左后，3右后   车轮偏差的修正值

	double wheel_Angle_correct_run[4]={0,0,0,0};  // 0左前，1右前，2左后，3右后，运行中归正（回中间）
 	double Last_wheel_Angle_correct_run[4]={0,0,0,0};  // 0左前，1右前，2左后，3右后
	
	double  real_time_erro=0.0175*2;               //为1度    运行中大于这个角度，才修正
	extern int delay_usr;
   extern int  count_TIM4,Switch_direction_Horizontal_flag;
  
	extern int v0,v1,v2,v3;
//	double volt0,volt1,volt2,volt3;  ,
	
   extern	float tim3_low_time_ms; 
    extern float tim3_high_time_ms;
	
	int voltage_Progress_bar=0;
	int count_time=0;
	int flag_turn_break=0;
	int count_time_battery=0; //电池没电延时记录位
	
	NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);//设置系统中断优先级分组2
	delay_init(168);		//延时初始化 
	uart_init(115200);	//电脑串口初始化波特率为115200  调试串口 串口6
	uart2_init(9600);  //绝对值编码器
	USART1_SBUS_Init();  //遥控器
	uart5_init(115200);	//上位机（显示屏幕）                                      //*************上位机在这里
	uart4_init(19200);	//  转向伺服电机通信  （作业机构）
	
//	uart3_init(19200);
	TIM7_Init();
	


//  TIM1_PWM_Init(250,84-1);
	retrofit_init();		/* RETROFIT: weeding link/relays/stepper/wheel-capture *///84M/84=1Mhz 的计数频率计数到8400,频率为 1M/250=4Khz，行走电机	PWM输出  tim8pwm行走电机 
//			TIM_SetCompare1(TIM1,0);
//			TIM_SetCompare2(TIM1,0);
//			TIM_SetCompare3(TIM1,0);
//			TIM_SetCompare4(TIM1,0);
		
	
	LED_Init();		  		//初始化与LED连接的硬件接口
	replay_switch_Init();
	
	
	SW_3=1;  ///    总继电器打开，连电
	Position_light=1; //让示廓灯亮起来
	
//	PCout(3)=1;
//  PCout(4)=1; //上电默认为低速
	PFout(7)=0;
	PFout(6)=1;
	

	
	// 预留输出端口，无用
	PAout(11)=1;//上电默认推拉杆在中间
  PDout(3)=0;	
	
//	Encoder1_TIM4_init();
//	Encoder1_TIM1_init();

//	 TIM3_CH1_Cap_Init(0xEA60,8400-1);     //Tim3通道1通道2输入捕获（不只是通道1） 直流电机霍尔元器件高低电平时间与周期  间接测速	
		
	IIC_2_Init();                                                  //初始化车轮角度传感器（电位计）ADS115AD模块
	IIC_1_Init();			                                             //初始化刹车电流、电池电压检测ADS1115模块 
	
  EXTIX_Init();
	 
	TIM1_PWM_Init(250,84-1);//84M/84=1Mhz 的计数频率计数到8400,频率为 1M/250=4Khz，行走电机	PWM输出  tim8pwm行走电机 
		TIM_SetCompare1(TIM1,0);
		TIM_SetCompare2(TIM1,0);
		TIM_SetCompare3(TIM1,0);
		TIM_SetCompare4(TIM1,0);
	////////////////////////////////////上电初始化完成后开始一次AD采集////////////////////////////////////////////////////////////////////
    delay_ms(1000);                            //上电后等的那三秒   为了上电后电路更稳定 并且  方便后面的AD采集
		delay_ms(500); 
//			delay_ms(500); 
			for(j=0;j<2;j++)
		{
				if(flag_sensor==0)
				{
					ADC_angle_Check();//使用AD采集
				}
				if(flag_sensor==1)
				{
					get_angle_encode();;//使用编码器获取每个轮子当前AD值		
				}
		}

		wheel_Angle_correct[0]=(AD_angle[0]-wheel_Angle_Init[0])/sensor_ratio;  //初始车轮误差计算  0左前，1右前，2左后，3右后    //2.0的意义 2：1
		wheel_Angle_correct[1]=(AD_angle[1]-wheel_Angle_Init[1])/sensor_ratio;  //第一次上这个代码 先不让你修正车轮角度
		wheel_Angle_correct[2]=(AD_angle[2]-wheel_Angle_Init[2])/sensor_ratio;
		wheel_Angle_correct[3]=(AD_angle[3]-wheel_Angle_Init[3])/sensor_ratio;

//wheel_Angle_correct[0]=0; //加上传感器后记得去掉  //第二辆车还没加传感器 这个得赋0值
//wheel_Angle_correct[2]=0;
//wheel_Angle_correct[1]=0; //加上传感器后记得去掉
//wheel_Angle_correct[3]=0;


	////////////////////////////////////使能伺服电机///////////////////////////////////////////////////////////////////

		for(j=0;j<6;j++)
		{			
			mosbus_EN(j);  //每个电机mosbus使能
			delay_ms(10);	

	  }
		for(i=0;i<6;i++)
		{
			motor_EN(i);  //每个电机驱动器驱动使能
			delay_ms(10);
		}	
			for(j=0;j<6;j++)
		{			
					motor_speed(j,steer_motor_speed);  //每个电机设置旋转速度
				  delay_ms(10);	

	  }	
		
		
IWDG_Init(4,500); //与分频数prer为64,重载值rlr为500,溢出时间为1s	//时间计算(大概):Tout=((4*2^prer)*rlr)/32 (ms).		//初始化看门狗
		


		
		
///////////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////前面是启动时的初始化，成功初始化后开始while（1）/////////////////////////
///////////////////////////////////////////////////////////////////////////////////////////////////////////
///进行模式选择 车辆模型。遥控器方式，通过拨码器进行设置
if (PFin(3)==1)//说明刚开始就有遮挡，开启定时器
{
		TIM_Cmd(TIM7,ENABLE);
}
		
//	mp3_control(1);
//	delay_ms(5000);
//	
//  mp3_control(0);
//	delay_ms(5000);

//  mp3_control(2);
//	delay_ms(5000);
//		
//  mp3_control(0);
//	delay_ms(5000);
while(1)
{

	
	char tjcstr[30];	//定义一个字符串数组
	
			 count_time=count_time+1;
			
			if (count_time==10)   //每1s重新使能伺服电机，减少过载报警，过载后清掉
			{
				 count_time=0;
					
					for(i=1;i<5;i++)
				{
					motor_EN(i);  //每个电机驱动器驱动使能
					delay_ms(10);
				}	

			}
			
			
			
	
	if ( regGroup[0]==0 )//上位机未接管，正常遥控器控制
	{
	//	printf("上位机未接管");
	
							
							while(sbus_channel[4]<800 &&regGroup[0]==0 ) //说明遥控器居中或者断开(遥控器需要) ,大摇控器要读电压                   //入股遥控器没断  那就不会进入这个条件
							{
								path_plan();
								mp3_control(0);
							veloc[0]=0;
							veloc[1]=0;	
							veloc[2]=0;
							veloc[3]=0;
							angle[0]=0;
							angle[1]=0;
							angle[2]=0;
							angle[3]=0;	
							printf(" 遥控器未连接！\r\n");	
							sprintf(tjcstr, "t6.txt=\"遥控器未连接！\"\xff\xff\xff" ); 
							 HMISends(tjcstr);	
								delay_ms(50);
							mp3_other=10;
							
							}
							
							

						//	
						//	
						if (only_start==0)   //提示请将油门拨到最低处
						{
							 mp3_other=0;
							
												if (sbus_channel[4]<1100)
											{
												only_start=1;
											}		
											
											if (sbus_channel[4]>1100)
													{
														while(only_start==0 && regGroup[0]==0)
														{
															path_plan();
															IWDG_Feed();
															printf(" 请将遥控器油门扳到最下方！\r\n");	
															
															sprintf(tjcstr, "t6.txt=\"请将遥控器油门扳到最下方!\"\xff\xff\xff" ); 
															 HMISends(tjcstr);	
															//原延时50
																delay_ms(10);
															 mp3_other=11;
															
															if (sbus_channel[4]<1100)
															{
																only_start=1;
																 mp3_other=0;
															}
														}
																						

									}	
						}
							
							
							
							//select_flag_car_mode();
							IWDG_Feed();   //每次进行循环都先喂狗	

							path_plan();//sbus通讯传输遥控信息并解析计算,0左前，1右前，2左后，3右后                         //解析遥控器指令 并 执行 时必须做的

							/////////////////////////////////////////遥控器检测设置，如果上位机接管，这里要进行修改	

								if(sbus_channel[4]<1100) //说明遥控器在下方或者断开(遥控器需要) ,大摇控器要读电压                   //入股遥控器没断  那就不会进入这个条件
							{
							veloc[0]=0;
							veloc[1]=0;	
							veloc[2]=0;
							veloc[3]=0;

						//	printf(" 停车！%d \r\n",mp3_other);	
							//	SW_Stop=0;
								
							}
							else
							{
							SW_Stop=1;
							}
	
	}
	
	if(regGroup[0]==1)	//上位机接管
	
	{
	IWDG_Feed();   //每次进行循环都先喂狗	

	path_plan();//sbus通讯传输遥控信息并解析计算,0左前，1右前，2左后，3右后                         //解析遥控器指令 并 执行 时必须做的
	
	}
	
/////////////////////////////////////////转向触碰开关设置	                                        //如果没碰到触碰开关就不会进入这个条件
	if (Touch_detection(flag_steer_limit) <9 ) // 返回9 说明没有任何触碰
	{
	veloc[0]=0;
	veloc[1]=0;	
	veloc[2]=0;
	veloc[3]=0;
//	angle[0]=0;
//	angle[1]=0;
//	angle[2]=0;
//	angle[3]=0;	
		
		//转向要立刻刹车，重新修改
		
	
	printf(" 转弯角度过大，触碰到行程开关！\r\n");			
	}


/////////////////////////////////////////刹车检测设置	                                     //如果刹车线没断 就不会进入这个条件
	if (Brake_protection_flag==1) //开启刹车电流保护
	{
			if(stop_voltage<=Brake_protection_value)	 //串联电流刹车线断了，电机刹车进行抱死  有速度还抱死 说明出问题了  不接刹车 2.539V  一个2.67  两个2.84		
			{		
				
	
				
				if(stop_voltage<=Brake_protection_value)
				{
						veloc[0]=0;	
						veloc[1]=0;	
						veloc[2]=0;
						veloc[3]=0;
						printf(" 停车，刹车故障请检查！\r\n");		
				}
			}
				else
				{	
				stop_voltage_count=0;

				
				
				}
	}

	
	////////////////////////////////////////////////////////////////////////////////////////////刹车设置	    如果有速度就不会进入这个条件

//if((veloc[0])==0&&veloc[1]==0&&veloc[2]==0&&veloc[3]==0) //没有速度，刹车	
	flag_turn_break=(( fabs(AD_angle[0]-wheel_Angle_Init[0])>=fabs(angle[0]-0.0175*5))&&( fabs(AD_angle[0]-wheel_Angle_Init[0])<=fabs(angle[0]+0.0175*5.0)))&&(( fabs(AD_angle[1]-wheel_Angle_Init[1])>=fabs(angle[1]-0.0175*5))&&( fabs(AD_angle[1]-wheel_Angle_Init[1])<=fabs(angle[1]+0.0175*5.0)))&&(( fabs(AD_angle[2]-wheel_Angle_Init[2])>=fabs(angle[2]-0.0175*5))&&( fabs(AD_angle[2]-wheel_Angle_Init[2])<=fabs(angle[2]+0.0175*5.0)))&&(( fabs(AD_angle[3]-wheel_Angle_Init[3])>=fabs(angle[3]-0.0175*5))&&( fabs(AD_angle[3]-wheel_Angle_Init[3])<=fabs(angle[3]+0.0175*5.0)));

	if((veloc[0])==0&&veloc[1]==0&&veloc[2]==0&&veloc[3]==0&&flag_turn_break) //没有速度，刹车	
  {
			if (Adjusting_wheelbase==1) //调整轴距
			{
			
			   SW_Stop=1;
				 printf(" 轴距调整中！\r\n");	
			}
			if (Adjusting_wheelbase==0) //非调整轴距
			{				
					 if(stop_count++==20) //延时刹车  80ms一个控制周期，延时1s，需要16
								{
									SW_Stop=0;
									 printf(" 刹车！\r\n");	
										stop_count=0;  //允许再次延时刹车	
								}
	
				}



			  }
/////////////////////////////////////////////////////////////  C超声波避障模块设置
		if(Obstacle_avoidance_flag==1)
		{
			
		//	printf(" 物 %d \r\n",delay_usr);	
			 if (delay_usr>1000)
				{
					
					
						
						veloc[0]=0;	
						veloc[1]=0;	
						veloc[2]=0;
						veloc[3]=0;
					
							printf(" 刹车有障碍物 %d \r\n",delay_usr);	
							sprintf(tjcstr, "t8.txt=\"请注意有障碍物!\"\xff\xff\xff" ); 
								HMISends(tjcstr);	
							 mp3_other=8;	
					
					     if(Obstacle_avoidance_flag_only==0)
							{					
								 Obstacle_avoidance_flag_only=1;
							}

							
							
	
							
						
				}
				if (delay_usr<1000)
				{
					
					
				  	if(Obstacle_avoidance_flag_only==1)
							{
								mp3_other=0;
					      Obstacle_avoidance_flag_only=0;
							}
				
				}



		}			

//////////////////////////////////////////霍尔车速测量代码
		
	//		printf("%f %f %f \r\n",control_flag[4],tim3_low_time_ms,tim3_high_time_ms);
				

/////////////////////////////////////////运行代码     //运行代码赋相应的速度和转向角度时必须做的
				

		wheel_angle_limit_set(flag_steer_limit);  // 转角限幅后进行大小限制，如果没有限制，该代码没有作用
	
// 4左前，1右前，2左后，3右后
	  send_angle(4,-(angle[0]-wheel_Angle_correct[0]-Last_wheel_Angle_correct_run[1]-Switch_direction));   //角度控制  adress, angle    四个轮子 但是一个伺服电机控制两个  所以只控制两个就可以
	  delay_ms(12);
 
	  send_angle(1,(angle[1]+wheel_Angle_correct[1]-Last_wheel_Angle_correct_run[1]+Switch_direction));   //角度控制  adress, angle    四个轮子 但是一个伺服电机控制两个  所以只控制两个就可以
	  delay_ms(12);
	
	  send_angle(2,(angle[2]-wheel_Angle_correct[2]-Last_wheel_Angle_correct_run[1]+Switch_direction));   //角度控制  adress, angle    四个轮子 但是一个伺服电机控制两个  所以只控制两个就可以
	  delay_ms(12);
	
	  send_angle(3,-(angle[3]+wheel_Angle_correct[3]-Last_wheel_Angle_correct_run[1]-Switch_direction));   //角度控制  adress, angle    四个轮子 但是一个伺服电机控制两个  所以只控制两个就可以
	  delay_ms(12);
		
	//控制伺服电机
    
//左前
			pwm_veloc(0,veloc[0]);  //速度控制
			
//左后	
			pwm_veloc(2,veloc[2]);   //速度控制

//右前	
			pwm_veloc(1,veloc[1]);	//速度控制

////右后	
			pwm_veloc(3,veloc[3]);   //速度控制
	 


//printf(" ch0 %d ch1 %d ch2 %d  ch3 %d ch4 %d ch5 %d ch6 %d ch7 %d ch8 %d ch9 %d \r\n",regGroup[0],regGroup[1],regGroup[2],regGroup[3],regGroup[4],regGroup[5],regGroup[6],regGroup[7],regGroup[8],regGroup[9] );	
//printf("\n");
//printf("  ch0 %d ch1 %d ch2 %d  ch3 %d ch4 %d ch5 %d ch6 %d ch7 %d ch8 %d ch9 %d \r\n",sbus_channel[0],sbus_channel[1],sbus_channel[2],sbus_channel[3],sbus_channel[4],sbus_channel[5],sbus_channel[6],sbus_channel[7],sbus_channel[8],sbus_channel[9] );	
//printf("\n");
//printf(" 停车 %f  方向 %f 转向  %f 角度 %f  速度 %f   mp3_flag %d mp3_flag_last %d mp3_time %d Switch_direction %f \r\n",control_flag[0],control_flag[1],control_flag[2],control_flag[3],control_flag[4], mp3_flag,mp3_flag_last,mp3_time,Switch_direction );			
////regGroup																																												//0行驶还是停车，1前进还是后退，2转向方式，3角度值，4速度值，5作业机构是否起降		
//printf("\n");
//printf("角度: 左前%f  左后%f 右前%f 右后%f 速度：左前%f 左后%f  右前%f 右后%f 电池%f 刹车%f 基准%f 遥控器%f 转向 %f  %d\r\n",angle[0],angle[2],angle[1],angle[3],veloc[0],veloc[2],veloc[1],veloc[3],battery_voltage,stop_voltage,base_voltage,control_voltage,control_flag[2],flag_Steering_mode);
//printf("\n");
printf("总角度 %.3f  总速度 %.3f 角度: 左前%.3f  左后%.3f 右前%.3f 右后%.3f 速度：左前%.3f 左后%.3f  右前%.3f 右后%.3f 电池%.3f 刹车%.3f 转向 %.3f 前进%.3f 横向 %d\r\n",control_flag[3]/3.14*180.0,control_flag[4],angle[0]/3.14*180.0,angle[2]/3.14*180.0,angle[1]/3.14*180.0,angle[3]/3.14*180.0,veloc[0],veloc[2],veloc[1],veloc[3],battery_voltage,stop_voltage,control_flag[2],control_flag[1],Switch_direction_Horizontal_flag);


//					AD_all(2,100);//获取每个轮子当前AD值	
//get_angle_encode();;//使用编码器获取每个轮子当前AD值					
//printf("初始AD角度: 左前%f 左后%f  右前%f 右后% f \r\n",AD_angle[0],AD_angle[2],AD_angle[1],AD_angle[3]);//四个轮子的采集值






 		LED0=!LED0;
		LED1=!LED1;
		if (count++==20)
		{		
			count=0;
    //ADC_angle_Check();//使用AD采集		
   //  get_angle_encode();;//使用编码器获取每个轮子当前AD值					
		ADC_electric_Check();  // 每2秒检测一下电池电压、刹车电流等信息

//		Position_light=!Position_light;  ///    示廓灯
		
		if(battery_voltage<44  && count_time_battery++>60*10*30)//如果电压低于44断开，保护电池,且超过30分钟
		{
			SW_3=0;  ///    总继电器断开，断电
			//SW_3=1;
		
		}
		else
		{
		count_time_battery=0;
		
		}
			
		//向上位机传输信息
		//电压
		sprintf(tjcstr, "t1.txt=\"%d.%d V\"\xff\xff\xff", (int)battery_voltage,(int)((battery_voltage-(int)battery_voltage)*10)); 
    HMISends(tjcstr);	

    voltage_Progress_bar=(int)((battery_voltage-44.0)/(56.0-44.0)*100);
		if (voltage_Progress_bar>=20)
			{
			sprintf(tjcstr, "j1.pco=2024\xff\xff\xff" ); //绿色
			HMISends(tjcstr);	
			sprintf(tjcstr, "j1.val=%d\xff\xff\xff",voltage_Progress_bar );  
			HMISends(tjcstr);
			sprintf(tjcstr, "t8.txt=\"正常运行!\"\xff\xff\xff" ); 
			HMISends(tjcstr);			
			sprintf(tjcstr, "t6.txt=\"遥控器连接成功!\"\xff\xff\xff" );   
			HMISends(tjcstr);		
			if( battery_voltage_flag_only==1)
			{mp3_other=0;	 //让其一直响吧
			 battery_voltage_flag_only=0;
				
				
				
		   }
				
			}
		if (voltage_Progress_bar<10)   //没电了
			{
			sprintf(tjcstr, "j1.pco=63488\xff\xff\xff" ); //红色
			HMISends(tjcstr);		
			sprintf(tjcstr, "j1.val=%d\xff\xff\xff",voltage_Progress_bar ); 
			HMISends(tjcstr);			
			sprintf(tjcstr, "t8.txt=\"请充电!\"\xff\xff\xff" ); 
			HMISends(tjcstr);	
      //mp3_other=9;	 //让其一直响吧
				
				printf("没电了 %d \r\n",mp3_other);	
				
			if( battery_voltage_flag_only==0)
			{
			 battery_voltage_flag_only=1;
		   }
			}			
		//速度信息

		sprintf(tjcstr, "t7.txt=\"%d.%dm/s\"\xff\xff\xff", (int)control_flag[4],(int)((control_flag[4]-(int)control_flag[4])*10));  
		HMISends(tjcstr);	
		
		sprintf(tjcstr, "j0.val=%d\xff\xff\xff",(int)((control_flag[4]-0.0)/(veloc_limit-0.0)*100) );  
		HMISends(tjcstr);
		// 转向模式
			
			if(control_flag[2]==1)
			{
			sprintf(tjcstr, "t4.txt=\"两轮转向!\"\xff\xff\xff" ); 
			HMISends(tjcstr);	
			}
			if(control_flag[2]==2)
			{
			sprintf(tjcstr, "t4.txt=\"四轮转向!\"\xff\xff\xff" ); 
			HMISends(tjcstr);	
			}
			if(control_flag[2]==3)
			{
			sprintf(tjcstr, "t4.txt=\"斜行转向!\"\xff\xff\xff" ); 
			HMISends(tjcstr);	
			}
			if(control_flag[2]==4)
			{
			sprintf(tjcstr, "t4.txt=\"原地转向!\"\xff\xff\xff" ); 
			HMISends(tjcstr);	
			}

			
	
			
		}
		
		
}



}
