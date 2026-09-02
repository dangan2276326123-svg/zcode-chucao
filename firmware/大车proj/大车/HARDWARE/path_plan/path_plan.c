#include "path_plan.h"
#include "telecontrol.h"
#include "sys.h"
#include "delay.h"
#include "usart.h"
#include "math.h"
#include "pwm.h"
#include "led.h" 
#include "uart5.h"	
#include "uart4.h"
#include "uart3.h"
#include "iwdg.h"
// 遥控器型号标志位
extern u8 flag_remote_control; // 0是单手遥控器 1是航模遥控器 2 是车模遥控器
extern double veloc_actual;
extern double veloc_limit ;  //对应的满p波 尽量与实际相符  满p波与最高速的比例关系
extern double veloc_limit_low;
extern double veloc_limit_middle;
extern double veloc_limit_high ;
extern double angle_limit ;  //控制角度限幅值，无需改变，自己运算
extern double angle_limit_single; //单个车轮角度限幅值，可以更改限制
extern u8 JiaQianFlag;
extern u8 JiannQianFlag;
extern int sbus_channel[16];//解析后的通道数据
extern double Upper_computer_date[4]; //0 表示行驶模式；1表示作业模式；2最大速度；3停车
extern double manual_contorl[12]; //0表示行驶模式；1表示停车；2 表示角度，3表示速度

double control_flag[6]={0,0,1,0,0,0};//0行驶还是停车，1前进还是后退，2转向方式，3角度值，4速度值，5作业机构是否起降

double Switch_direction=0;  ///用于切换水平方向
double angle[4]={0,0,0,0};//输出四轮角度，分别为0左前轮，1右前轮，2左后轮，3右后轮
double veloc[4]={0,0,0,0};//输出四轮速度，分别为左前轮，右前轮，左后轮，右后轮
int Switch_direction_Horizontal_flag=0;  //横向转向方式切换标志位
extern double B; //车宽
extern double L;  //车长
extern double B_Horizontal; //车宽
extern double L_Horizontal;  //车长

extern double angle_add; // 增量式每次增加的度数 
extern u8 flag_Steering_mode; // 0是绝对值式 1增量式
	extern unsigned char regGroup[16]; //上位机接管数据
u8 mp3_flag=0,mp3_flag_last=0,mp3_time=0,mp3_other=0;// 音乐播放类型、播放时间控制  mp3_other 为播放没有电、有障碍物的声音

////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////

	/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
	/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
	////////////////////////////////////path_plan 办两件事1.解析遥控器指令 2.解析完进行控制////////////////////////////////////////////////////////////////////
	/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
	/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
void path_plan(void)		//flag为转向方式,direction为解析的方向角度的大小，velocity为解析的速度的大小
{	
   telecontrol_anazye_little();
	//telecontrol_analyze();//遥控命令解析，返回 control_flag[6] 控制标志位（停车、方向、角度、车速） 
//至此 经过这一步 遥控器的信息已经转化成了 比较宏观的车辆信息：停车与否  什么方向？  怎么转向 质心速度  转向角度
		if(regGroup[0]==1)
		{
		//进行解算，仅支持前进后退，不运行横向，原地等
			Switch_direction_Horizontal_flag=0;//正常
			control_flag[0]=1;//正常行驶
			control_flag[1]=(double)(regGroup[1]);//方向	0是前进 ，1后退
			
			control_flag[2]=1;//运动方式
//			if ((double)(regGroup[1])==0.0)//前进
//			{
			control_flag[4]=((double)(regGroup[2])*255.0+(double)(regGroup[3]))/1000.0;
//			}
//			if ((double)(regGroup[1])==1.0)//后退
//			{
//				control_flag[4]=((double)(regGroup[2])*255.0+(double)(regGroup[3]))/1000.0;
//			}
			
			
			if ((double)(regGroup[4])==0.0)//左转
			{
				control_flag[3]=((double)(regGroup[5])*255.0+(double)(regGroup[6]))/1000.0;
			}
			if ((double)(regGroup[4])==1.0)//右转
			{
				control_flag[3]=-((double)(regGroup[5])*255.0+(double)(regGroup[6]))/1000.0;
			}
		
		}
   telecontrol();//控制         //这一步就是落实上面从遥控器处解析来的宏观车辆信息 到 具体怎么落实这个角度 ，事实上师兄已经写好了，我不用写从宏观到具体执行转向、车速的代码了。
	   		//我后面大多数情况只需要改前面宏观的数据



//油门最下方内八刹车
				if(sbus_channel[4]<1300)//油门打开/////////////////////右边油门摇杆
				 {	
					if ( Switch_direction_Horizontal_flag==0)
					{
					 
					 	if (control_flag[1]==0)//1前轮转向
						{
							angle[2]=-20.0/180.0*pi;
							angle[3]=20.0/180.0*pi;
							
							
						}
						if(control_flag[1]==1)//后轮转向
						{
							angle[0]=20.0/180.0*pi;
							angle[1]=-20.0/180.0*pi;
							
							
						 }
					 
					 
				 }

//       	if ( Switch_direction_Horizontal_flag==1)
//					{
//					 
//					 	if (control_flag[1]==0)//1前轮转向
//						{
//							angle[2]=-20.0/180.0*pi;
//							angle[3]=20.0/180.0*pi;
//							
//							
//						}
//						if(control_flag[1]==1)//后轮转向
//						{
//							angle[0]=20.0/180.0*pi;
//							angle[1]=-20.0/180.0*pi;
//							
//							
//						 }
					 
					 
				 }
}



////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////
void telecontrol_anazye_little(void) 
{
	u8 j=0;
	static  int Switch_direction_flag=0; //前进后退切换标志位
	static  int Switch_direction_flag_2=0; //前进后退切换标志位.用于切换后方向清零使用
	static  int Switch_way_flag=1;  //转向方式切换标志位
	static  int Switch_way_flag_work=0;  //工作模式切换标志位,默认0不工作
	static  int Switch_way_flag_work_allow=0;  //工作模式切换标志位,允许切换
	//static   u8 switch_way=0; //
	static  int Switch_way_flag_2=1; //转向方式切换标志位.用于切换后方向清零使用
	//static  int Switch_direction_Horizontal_flag_last=0;  //横向转向方式切换标志位

	
	control_flag[0]=1;//正常行驶   //取消急停，仅依赖油门控制
	
	//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
	//油门和方向解析
				
	   // 方向判断，需要车速为0时候切换
			if (sbus_channel[3]<1500&& Switch_direction_flag==0  && control_flag[4]==0 ) //前进///////////////////////////////////////////////////////////这可能是遥控器那个前进还是后退的档位选择
			{
				Switch_direction_flag=1;
				control_flag[1]=0;//方向	0是前进                                                            //////////第1个标志位  行走 方向 前进还是后退			
       mp3_flag=1;
				
			}
			if (sbus_channel[3]>1500&& Switch_direction_flag==1&& control_flag[4]==0)
				
			 {
				 Switch_direction_flag=0;
				 control_flag[1]=1;//后退
         mp3_flag=2;				 

			 }
			
			// 油门控制
			// 阈值是否需要修改（1100->1450）//////////////////////////////////////////////
			if(sbus_channel[4]>=1600)//油门打开/////////////////////右边油门摇杆
				 {		 
						 control_flag[4]=(sbus_channel[4]-1600.0)/(2000.0-1600)*veloc_actual;                        //第4个标志位 车质心的速度值
						 if(control_flag[4]>=veloc_actual)
						 {control_flag[4]=veloc_actual;}
						 if(control_flag[4]<=0)
						 {control_flag[4]=0;}				 
				 }
			else
				control_flag[4]=0; //停车
			
			
			
			
	//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////				
	
	// 运动方式解析		
			if (sbus_channel[2]<1500&& Switch_way_flag==0  && control_flag[4]==0 ) 
			{
				Switch_way_flag=1; // 
				control_flag[2]=control_flag[2]+1;
				if (control_flag[2]==5)//如果相加模式，这个数据对应加大目前是 两轮、四轮相对、四轮斜行、原地、
					control_flag[2]=1;
					mp3_flag=control_flag[2]+2; //播报内容
			}
			if (sbus_channel[2]>1500&& Switch_way_flag==1  && control_flag[4]==0 ) 
			{
				Switch_way_flag=0; // 
				control_flag[2]=control_flag[2]+1;
				if (control_flag[2]==5)
					control_flag[2]=1;
				mp3_flag=control_flag[2]+2; //播报内容
			}
	// 切换为横向
			if (sbus_channel[1]>1500 && Switch_direction_Horizontal_flag ==0  && control_flag[4]==0 )   //遥控器默认是900
			{
				control_flag[3]=0; //切换时候角度归0
				Switch_direction_Horizontal_flag=1;  //切换为横向
		
				
				Switch_direction=1.570796;//切换为水平方向,补偿角度
				mp3_flag=7; //播报内容
			}
			if (sbus_channel[1]<1500 && Switch_direction_Horizontal_flag ==1  && control_flag[4]==0 ) 
			{
				 control_flag[3]=0;//切换时候角度归0
				Switch_direction_Horizontal_flag=0;  //切换为正常
				
				
				
				
				
				Switch_direction=0;//
				mp3_flag=13; //播报内容
			
			}
			
			
			
			
			

			
	//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////	
	// 方向解析
	     //control_flag[3],转角解析,以垂直向前的方向为0度,                 左转为正，右转为负  flag_Steering_mode; // 0是绝对值式 1增量式
			//ch0 方向，ch0=1023 中间  ch0=1876最大，向右  ch0=214，向左				

			//根据转向方式进行控制量转向角限幅
			if(Switch_direction_Horizontal_flag==0)// 正常运行
			{
						if (control_flag[2]==1) //双轮转向
						{
									angle_limit=atan(2*L/B)-2.0*0.0175;					
						}
			//			
						if (control_flag[2]==2) //相对转向
						{			
									angle_limit=atan(L/B)-2.0*0.0175;			
						}
			//		
						if (control_flag[2]!=1 && control_flag[2]!=2)
						{
						angle_limit=80.0/180.0*3.1415926;	
							
						}
			}
			if(Switch_direction_Horizontal_flag==1)// 横向运行
			{
						if (control_flag[2]==1) //双轮转向
						{
									angle_limit=atan(2*B/L)-2.0*0.0175;				
						}
			//			
						if (control_flag[2]==2) //相对转向
						{			
									angle_limit=atan(B/L)-2.0*0.0175;		
						}
			//		
						if (control_flag[2]!=1 && control_flag[2]!=2)
						{
						angle_limit=80.0/180.0*3.1415926;	
							
						}
			}
			
			
			
				if (flag_Steering_mode==1)  //增量式转向
				{
								if(sbus_channel[5]<=1350)  //左转///////////////////////////////////////////////////  这里就是 控制方向的地方。 上位机调整的标志位判断可以放在这里
								{
										   control_flag[3]=control_flag[3]+angle_add;			                                  //第3个标志位 整个车体的角度值
										   if(control_flag[3]>angle_limit)
										  	control_flag[3]=angle_limit;
//									control_flag[3]=control_flag[3]-angle_add;			
//											if(control_flag[3]<-angle_limit)
//											control_flag[3]=-angle_limit;
								}			
								if(sbus_channel[5]>1700)      //右转
								{
											control_flag[3]=control_flag[3]-angle_add;			
											if(control_flag[3]<-angle_limit)
											control_flag[3]=-angle_limit;
//									 control_flag[3]=control_flag[3]+angle_add;			                                  //第3个标志位 整个车体的角度值
//										   if(control_flag[3]>angle_limit)
//										  	control_flag[3]=angle_limit;
								}						 
						//////////////////////////归正代码
//								if(sbus_channel[5]>=1450&&sbus_channel[5]<=1540)   //点击按钮后归正
//								{

//										if(sbus_channel[1]<=1200)  //归正代码
//										{
//											control_flag[3]=0;
//										}	
//								}
				}			
			
				if (flag_Steering_mode==0)  //绝对值式转向
				{

							 control_flag[3]=-(sbus_channel[5]-1500.0)/(2000.0-1500)*angle_limit;			        
							 if(control_flag[3]>angle_limit)
									control_flag[3]=angle_limit;
							 if(control_flag[3]<-angle_limit)
									control_flag[3]=-angle_limit;
				
						       //////////////////////////归正代码
								if(sbus_channel[5]>=1350&&sbus_channel[5]<=1640)   //点击按钮后归正
								{
											control_flag[3]=0;
								}
				}
				
				//切换方向以及切换转向方式时候清零
					if (control_flag[1]!=Switch_direction_flag_2) //如果切换前进后退方向时，强制归正，但速度已清零
						{
							control_flag[3]=0;
							control_flag[4]=0;
							Switch_direction_flag_2=control_flag[1];	
						}
						
						if (control_flag[2]!=Switch_way_flag_2) //如果切换转向方式时，强制归正，但速度为清零
						{
							control_flag[3]=0;
							control_flag[4]=0;
							Switch_way_flag_2=control_flag[2];
						}
	
//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////	
			/////////////////// 高低速选择
//				if (sbus_channel[8]<=1200)  // 低速
//				{
////				  veloc_limit=veloc_limit_low;
//						PCout(3)=0;
//					   PCout(4)=1;
//				}
//				if (sbus_channel[8]<1700&&sbus_channel[8]>=1200)
//				{
////				   veloc_limit=veloc_limit_middle;
//						PCout(3)=1;
//					   PCout(4)=1;
//				}
//				if (sbus_channel[8]>1700)
//				{
//				   veloc_limit=veloc_limit_high;
//					
//						PCout(3)=1;
//					   PCout(4)=1;
//					
//				}
				
		///作业设置
				if (sbus_channel[0]>=1500)  // 表面工作按钮切换了
				{
					
				 Switch_way_flag_work_allow=1; //此时允许切换
					
				}
				
				if (sbus_channel[0]<=1500 && Switch_way_flag_work_allow==1)  //说明工作按钮放下了，允许下次切换
					
				{
				 Switch_way_flag_work=!Switch_way_flag_work;
				
					 Switch_way_flag_work_allow=0; //等待下次切换
				}

        if(Switch_way_flag_work==0)
				{
				//写不工作的代码  PAout(11)=0;
					PDout(7)=0;
				//printf("关闭");
					
				}

        if(Switch_way_flag_work!=0)
				{
				  
				//写工作的代码 
					 PDout(7)=1;
				//  printf("打开");
					
				}
				
			///////// 推拉杆设置
//			if (Switch_direction_Horizontal_flag==0) // 只有在正常前进方向上才
//			{
//				   if (sbus_channel[7]<1268)  //缩回
//						{
//							PAout(11)=1;

//							PDout(3)=0;
//						}

//						if (sbus_channel[7]>1757)  //伸出
//						{

//							PAout(11)=0;

//							PDout(3)=1;

//						}

//						if (sbus_channel[7]<1757&&sbus_channel[7]>1268)  //伸出
//						{

//							PAout(11)=0;

//							PDout(3)=0;

//						}
//		}
//				
 ////////////////////////////////////////////////////////////声音控制
 //mp3_flag_last=0,mp3_time
 if (mp3_flag==mp3_flag_last &&mp3_time<40)
 {
		mp3_control(mp3_flag);
		mp3_time=mp3_time+1;
	 
 }
 
  if (mp3_flag!=mp3_flag_last)
	{
	   mp3_time=0;
	   mp3_flag_last=mp3_flag;
		 mp3_control(0);
	}
 
	 if(mp3_time>=40)
	 {
		 if(mp3_other==0)
		 {
		  mp3_control(0);
		 }
		 else  //播放的是各种故障信息
		 {
		 mp3_control(mp3_other);
		 
		 }

		 
		 
	 }


}

////////////////////////////////////////////////////////////////////////////////////////////////////
void telecontrol(void)//遥控器遥控  前进、后退，停车、行走，转向方式的选择。
{	float velocity;
	float direction;
	double temp;
	
			if(control_flag[0]==0||Upper_computer_date[3]==0)  //control_flag[0]，控制车正常，还是停车，1正常，0停车
			{
					//停车函数			 
					veloc[0]=0.0;
					veloc[1]=0.0;
					veloc[2]=0.0;
					veloc[3]=0.0;	
			}
			else
			{
								direction=control_flag[3];
								velocity=control_flag[4];                 //方向、速度赋值过来  作为  后面选的相应的行驶模式中函数的参数
										  
							   //控制车转向方式，1前轮转向，2是后轮转向，3是四轮相对转向，4是斜行方式，5是蟹行平行，6是原地转
								if(control_flag[2]==1)//两轮转向模式
								{										
										if (control_flag[1]==0)//1前轮转向
												ackman_steering_front(direction, velocity);
										if(control_flag[1]==1)//后轮转向
												ackman_steering_rear(direction, velocity);	
								}
								
							
								 if(control_flag[2]==2 )//3是相对转向
								{
  									if (control_flag[1]==0)//1前轮转向
												four_Relative_front(direction, velocity);
										if(control_flag[1]==1)//后轮转向
												four_Relative_rear(direction, velocity);	
	
								}
								 if(control_flag[2]==3 )//4是斜行转向
								{
								  	if (control_flag[1]==0)//1前轮转向
												path_diagonal_front(direction, velocity);
										if(control_flag[1]==1)//后轮转向
												path_diagonal_rear(direction, velocity);	
								}

								if(control_flag[2]==4 && Switch_direction_Horizontal_flag==0)//3是原地转向
								{							
										if (control_flag[1]==0)//1前轮转向
												path_circle_around(direction, velocity)	;
										if(control_flag[1]==1)//后轮转向
												path_circle_around(direction, velocity)	;
								}
								
								if(control_flag[2]==4)//新的方式
								{
								
								}
								
						}
						
			
							///切换为了水平方向时,将四个轮子进行切换
//										if(Switch_direction_Horizontal_flag==1)
//										{
//											
//										temp=veloc[2];
//										veloc[2]=veloc[0];
//										veloc[0]=-veloc[1];
//										veloc[1]=veloc[3];	
//										veloc[3]=-temp;
//										
//											
//										temp=angle[2];
//										angle[2]=angle[0];
//										angle[0]=angle[1];
//										angle[1]=angle[3];	
//										angle[3]=temp;
//																					
//										
//										}	
	if(Switch_direction_Horizontal_flag==1)   //核对一下交换顺序，注意不同车型，PCB接线中，谁和谁一组的问题
										{
											
										temp=veloc[2];
										veloc[2]=veloc[0];
										veloc[0]=-veloc[1];
										veloc[1]=veloc[3];	
										veloc[3]=-temp;
											
					
											
											
//										temp=veloc[1];
//					          veloc[1]=veloc[3];	
//										veloc[3]=temp;	
//             				temp=veloc[0];
//					          veloc[0]=veloc[2];	
//										veloc[2]=temp;
//											
										temp=angle[2];
										angle[2]=angle[0];
										angle[0]=angle[1];
										angle[1]=angle[3];	
										angle[3]=temp;
											
//										temp=angle[1];
//					          angle[1]=angle[0];	
//										angle[0]=temp;	
//             				temp=angle[3];
//					          angle[3]=angle[2];	
//										angle[2]=temp;	

//										temp=angle[1];
//					          angle[1]=angle[3];	
//										angle[3]=temp;	
//             				temp=angle[2];
//					          angle[2]=angle[0];	
//										angle[0]=temp;


										}	
			
			}



////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////////////////


 

void work_equipment_control(void)   ///////////////////////////////////////////////////////////////目前没有作业机构
{

}

////////////////////////////////////////////////////////////////////////////////// 
////////////////////////////////////////////////////////////////////////////////// 
////////////////////////////////////////////////////////////////////////////////// 
//float angle[4]={0,0,0,0};//输出四轮角度，分别为0前左轮，1前右轮，2后左轮，3后右轮
//float veloc[4]={0,0,0,0};//输出四轮速度，分别为前左轮，前右轮，后左轮，后右轮
//以转向内测为基本计算
void limit_angle_veloc(void)// 用于限制每个车轮的转角和速度
{
		if(angle[0]>=angle_limit_single)
			angle[0]=angle_limit_single;
		if(angle[0]<=-angle_limit_single)
			angle[0]=-angle_limit_single;	
		if(angle[1]>=angle_limit_single)
			angle[1]=angle_limit_single;
		if(angle[1]<=-angle_limit_single)
			angle[1]=-angle_limit_single;
		if(angle[2]>=angle_limit_single)
			angle[2]=angle_limit_single;
		if(angle[2]<=-angle_limit_single)
			angle[2]=-angle_limit_single;	
		if(angle[3]>=angle_limit_single)
			angle[3]=angle_limit_single;
		if(angle[3]<=-angle_limit_single)
			angle[3]=-angle_limit_single;
		
		if(veloc[0]>=veloc_limit)
			veloc[0]=veloc_limit;
		if(veloc[0]<=-veloc_limit)
			veloc[0]=-veloc_limit;	
		if(veloc[1]>=veloc_limit)
			veloc[1]=veloc_limit;
		if(veloc[1]<=-veloc_limit)
			veloc[1]=-veloc_limit;
		if(veloc[2]>=veloc_limit)
			veloc[2]=veloc_limit;
		if(veloc[2]<=-veloc_limit)
			veloc[2]=-veloc_limit;	
		if(veloc[3]>=veloc_limit)
			veloc[3]=veloc_limit;
		if(veloc[3]<=-veloc_limit)
			veloc[3]=-veloc_limit;

}


void ackman_steering_front(double direction,double velocity)
{	
	double R=0,W=0;
	if(direction==0)
	{
				angle[0]=0;		
				angle[1]=0;
				angle[2]=0;		
				angle[3]=0;
				veloc[0]=velocity;		
				veloc[1]=velocity;
				veloc[2]=velocity;		
				veloc[3]=velocity;	
	}
	else
	{
			if(Switch_direction_Horizontal_flag==0)// 正常运行
			{
				
				if (direction>(atan(2.0*L/B)-0.0175*2.0))
					direction=atan(2.0*L/B)-0.0175*2.0;
				if (direction<-(atan(2.0*L/B)+0.0175*2.0))
					direction=-atan(2.0*L/B)+0.0175*2.0;
				
				R=L/tan(direction);
				W=velocity/R;
		
				angle[0]=atan(2.0*L/(2*R-B));		
				angle[1]=atan(2.0*L/(2*R+B));
				angle[2]=0;		
				angle[3]=0;
				veloc[0]=velocity*(R-B/2.0)/R/cos(angle[0]);		
				veloc[1]=velocity*(R+B/2.0)/R/cos(angle[1]);
				veloc[2]=W*(R-B/2.0);		
				veloc[3]=W*(R+B/2.0);	
			//	veloc[0]=0;
							//	printf(" 请将R %.4f W %.4f %.4f %.4f\r\n",R,W,angle[0]/3.1415*180,angle[1]/3.1415*180);	
			}

				if(Switch_direction_Horizontal_flag==1)// 横向运行
			{
				
				if (direction>(atan(2.0*L_Horizontal/B_Horizontal)-0.0175*2.0))
					direction=atan(2.0*L_Horizontal/B_Horizontal)-0.0175*2.0;
				if (direction<-(atan(2.0*L_Horizontal/B_Horizontal)+0.0175*2.0))
					direction=-atan(2.0*L_Horizontal/B_Horizontal)+0.0175*2.0;
				
				R=L_Horizontal/tan(direction);
				W=velocity/R;
		
				angle[0]=atan(2.0*L_Horizontal/(2*R-B_Horizontal));		
				angle[1]=atan(2.0*L_Horizontal/(2*R+B_Horizontal));
				angle[2]=0;		
				angle[3]=0;
				veloc[0]=velocity*(R-B_Horizontal/2.0)/R/cos(angle[0]);		
				veloc[1]=velocity*(R+B_Horizontal/2.0)/R/cos(angle[1]);
				veloc[2]=W*(R-B_Horizontal/2.0);		
				veloc[3]=W*(R+B_Horizontal/2.0);	
			//		veloc[0]=0;

			}
//				
	}	
		// 进行限幅
	limit_angle_veloc();
		
}
void ackman_steering_rear(double direction,double velocity)
{	
	double R=0,W=0;
	if(direction==0)
	{
				angle[0]=0;		
				angle[1]=0;
				angle[2]=0;		
				angle[3]=0;
				veloc[0]=-velocity;		
				veloc[1]=-velocity;
				veloc[2]=-velocity;		
				veloc[3]=-velocity;	
	}
	else
	{
			if(Switch_direction_Horizontal_flag==0)// 正常运行
			{
								
				if (direction>(atan(2.0*L/B)-0.0175*2.0))
					direction=atan(2.0*L/B)-0.0175*2.0;
				if (direction<-(atan(2.0*L/B)+0.0175*2.0))
					direction=-atan(2.0*L/B)+0.0175*2.0;
				
				R=L/tan(direction);
				W=velocity/R;
		
				angle[3]=atan(2.0*L/(2.0*R-B));		
				angle[2]=atan(2.0*L/(2.0*R+B));
				angle[1]=0;		
				angle[0]=0;
				veloc[3]=-velocity*(R-B/2.0)/R/cos(angle[3]);		
				veloc[2]=-velocity*(R+B/2.0)/R/cos(angle[2]);
				veloc[1]=-W*(R-B/2.0);		
				veloc[0]=-W*(R+B/2.0);	
		  // 	veloc[0]=0;
			}

				if(Switch_direction_Horizontal_flag==1)// 横向运行
			{
				
				if (direction>(atan(2.0*L_Horizontal/B_Horizontal)-0.0175*2.0))
					direction=atan(2.0*L_Horizontal/B_Horizontal)-0.0175*2.0;
				if (direction<-(atan(2.0*L_Horizontal/B_Horizontal)+0.0175*2.0))
					direction=-atan(2.0*L_Horizontal/B_Horizontal)+0.0175*2.0;
				R=L_Horizontal/tan(direction);
				W=velocity/R;
		
				angle[3]=atan(2.0*L_Horizontal/(2.0*R-B_Horizontal));		
				angle[2]=atan(2.0*L_Horizontal/(2.0*R+B_Horizontal));
				angle[1]=0;		
				angle[0]=0;
				veloc[3]=-velocity*(R-B_Horizontal/2.0)/R/cos(angle[3]);		
				veloc[2]=-velocity*(R+B_Horizontal/2.0)/R/cos(angle[2]);
				veloc[1]=-W*(R-B_Horizontal/2.0);		
				veloc[0]=-W*(R+B_Horizontal/2.0);	
			//	veloc[1]=0;
			}
//		
		
				
	}	
		// 进行限幅
		limit_angle_veloc();
		
}

void four_Relative_front(double direction,double velocity)
{	
double R=0,W=0;
	if(direction==0)
	{
				angle[0]=0;		
				angle[1]=0;
				angle[2]=0;		
				angle[3]=0;
				veloc[0]=velocity;		
				veloc[1]=velocity;
				veloc[2]=velocity;		
				veloc[3]=velocity;	
	}
	else
	{
		
					if(Switch_direction_Horizontal_flag==0)// 正常运行
			{
				
								
				if (direction>(atan(L/B)-0.0175*2.0))
					direction=atan(L/B)-0.0175*2.0;
				if (direction<-(atan(L/B)+0.0175*2.0))
					direction=-atan(L/B)+0.0175*2.0;
				
			R=L/2.0/tan(direction);
						//W=velocity/R;
				
						angle[0]=atan(L/(2.0*R-B));		
						angle[1]=atan(L/(2.0*R+B));
						angle[2]=-angle[0];		
						angle[3]=-angle[1];
						veloc[0]=velocity*(R-B/2.0)/R/cos(angle[0]);		
						veloc[1]=velocity*(R+B/2.0)/R/cos(angle[1]);
						veloc[2]=veloc[0];	
						veloc[3]=veloc[1];
			}

				if(Switch_direction_Horizontal_flag==1)// 横向运行
			{
				
				if (direction>(atan(L_Horizontal/B_Horizontal)-0.0175*2.0))
					direction=atan(L_Horizontal/B_Horizontal)-0.0175*2.0;
				if (direction<-(atan(L_Horizontal/B_Horizontal)+0.0175*2.0))
					direction=-atan(L_Horizontal/B_Horizontal)+0.0175*2.0;
				
			R=L_Horizontal/2.0/tan(direction);
						//W=velocity/R;
				
						angle[0]=atan(L_Horizontal/(2.0*R-B_Horizontal));		
						angle[1]=atan(L_Horizontal/(2.0*R+B_Horizontal));
						angle[2]=-angle[0];		
						angle[3]=-angle[1];
						veloc[0]=velocity*(R-B_Horizontal/2.0)/R/cos(angle[0]);		
						veloc[1]=velocity*(R+B_Horizontal/2.0)/R/cos(angle[1]);
						veloc[2]=veloc[0];	
						veloc[3]=veloc[1];
			}
					
	}	
		// 进行限幅
		limit_angle_veloc();		
}
void four_Relative_rear(double direction,double velocity)
{	
	double R=0,W=0;
	if(direction==0)
	{
				angle[0]=0;		
				angle[1]=0;
				angle[2]=0;		
				angle[3]=0;
				veloc[0]=-velocity;		
				veloc[1]=-velocity;
				veloc[2]=-velocity;		
				veloc[3]=-velocity;	
	}
	else
	{
		//if (direction>atan2())
		
			if(Switch_direction_Horizontal_flag==0)// 正常运行
			{
				
												
				if (direction>(atan(L/B)-0.0175*2.0))
					direction=atan(L/B)-0.0175*2.0;
				if (direction<-(atan(L/B)+0.0175*2.0))
					direction=-atan(L/B)+0.0175*2.0;
				
						R=L/2.0/tan(direction);
				//W=velocity/R;
		
				angle[3]=atan(L/(2.0*R-B));		
				angle[2]=atan(L/(2.0*R+B));
				angle[1]=-angle[3];		
				angle[0]=-angle[2];
				veloc[3]=-velocity*(R-B/2.0)/R/cos(angle[3]);		
				veloc[2]=-velocity*(R+B/2.0)/R/cos(angle[2]);
				veloc[1]=veloc[3];	
				veloc[0]=veloc[2];
				
				
			}

				if(Switch_direction_Horizontal_flag==1)// 横向运行
			{
				
				if (direction>(atan(L_Horizontal/B_Horizontal)-0.0175*2.0))
					direction=atan(L_Horizontal/B_Horizontal)-0.0175*2.0;
				if (direction<-(atan(L_Horizontal/B_Horizontal)+0.0175*2.0))
					direction=-atan(L_Horizontal/B_Horizontal)+0.0175*2.0;
				
				R=L_Horizontal/2.0/tan(direction);
				//W=velocity/R;
		
				angle[3]=atan(L_Horizontal/(2.0*R-B_Horizontal));		
				angle[2]=atan(L_Horizontal/(2.0*R+B_Horizontal));
				angle[1]=-angle[3];		
				angle[0]=-angle[2];
				veloc[3]=-velocity*(R-B_Horizontal/2.0)/R/cos(angle[3]);		
				veloc[2]=-velocity*(R+B_Horizontal/2.0)/R/cos(angle[2]);
				veloc[1]=veloc[3];	
				veloc[0]=veloc[2];
			}


	}	
		// 进行限幅
		limit_angle_veloc();


}

void path_diagonal_front(double direction,double velocity)			//斜行转向方式,不是理论的高速斜行,只是为了斜行
{
///四轮转角完全相同,完全与遥控相同
	
			angle[0]=direction;
			angle[1]=direction;
			angle[2]=direction;
			angle[3]=direction;
		
///四轮转速度完全相同,完全与遥控相同
				veloc[0]=velocity;
				veloc[1]=velocity;
				veloc[2]=velocity;
				veloc[3]=velocity;
}

void path_diagonal_rear(double direction,double velocity)			//斜行转向方式,不是理论的高速斜行,只是为了斜行
{
///四轮转角完全相同,完全与遥控相同
	
			angle[3]=direction;
			angle[2]=direction;
			angle[1]=direction;
			angle[0]=direction;
		
///四轮转速度完全相同,完全与遥控相同
				veloc[3]=-velocity;
				veloc[2]=-velocity;
				veloc[1]=-velocity;
				veloc[0]=-velocity;
}


void path_circle_around(double direction,double velocity)	//原地转向,此时前进后退开关无效
{
	float temp;
	
	if(Switch_direction_Horizontal_flag==0)// 正常运行
	{
		temp = atan(L/B);
	}

		if(Switch_direction_Horizontal_flag==1)// 横向运行
	{
		temp = atan(L_Horizontal/B_Horizontal);
	}
		//if (velocity!=0)
		{

			angle[0]=-temp;     //车型不同 转向方向不同
		angle[1]=+temp;       
		angle[2]=+temp;
		angle[3]=-temp;     //车型不同 转向方向不同
			
		}
//			if(velocity<0)
//			{	velocity=-velocity;
//			
//			velocity=velocity*0.7;//原地旋转限速
//	
//				
//        veloc[0]=-velocity;
//				veloc[1]=-velocity;    //车型不同 转向方向不同 速度方向也不同
//				veloc[2]=velocity;
//				veloc[3]=velocity;    //车型不同 转向方向不同 速度方向也不同
//			}
			
	//		if(velocity>0)
			{	velocity=velocity;
			
			velocity=velocity*0.7;//原地旋转限速
	
				
        veloc[0]=velocity;    //车型不同 转向方向不同 速度方向也不同
				veloc[1]=-velocity;
				veloc[2]=velocity;    //车型不同 转向方向不同 速度方向也不同
				veloc[3]=-velocity;
			}	

}







