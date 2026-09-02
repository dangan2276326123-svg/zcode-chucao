#include "can.h"
#include "led.h"
#include "delay.h"
#include "usart.h"
#include "adc.h"
//CAN初始化
//tsjw:重新同步跳跃时间单元.范围:CAN_SJW_1tq~ CAN_SJW_4tq
//tbs2:时间段2的时间单元.   范围:CAN_BS2_1tq~CAN_BS2_8tq;
//tbs1:时间段1的时间单元.   范围:CAN_BS1_1tq ~CAN_BS1_16tq
//brp :波特率分频器.范围:1~1024; tq=(brp)*tpclk1
//波特率=Fpclk1/((tbs1+1+tbs2+1+1)*brp);
//mode:CAN_Mode_Normal,普通模式;CAN_Mode_LoopBack,回环模式;
//Fpclk1的时钟在初始化的时候设置为42M,如果设置CAN1_Mode_Init(CAN_SJW_1tq,CAN_BS2_6tq,CAN_BS1_7tq,6,CAN_Mode_LoopBack);
//则波特率为:42M/((6+7+1)*6)=500Kbps
//返回值:0,初始化OK;
//    其他,初始化失败; 


//u8 CAN1_Mode_Init(u8 tsjw,u8 tbs2,u8 tbs1,u16 brp,u8 mode)
//{

//  	GPIO_InitTypeDef GPIO_InitStructure; 
//	  CAN_InitTypeDef        CAN_InitStructure;
//  	CAN_FilterInitTypeDef  CAN_FilterInitStructure;
//#if CAN1_RX0_INT_ENABLE 
//   	NVIC_InitTypeDef  NVIC_InitStructure;
//#endif
//    //使能相关时钟
//	  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE);//使能PORTA时钟	                   											 

//  	RCC_APB1PeriphClockCmd(RCC_APB1Periph_CAN1, ENABLE);//使能CAN1时钟	
//	
//    //初始化GPIO
//	  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_11| GPIO_Pin_12;
//    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
//    GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;//推挽输出
//    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;//100MHz
//    GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;//上拉
//    GPIO_Init(GPIOA, &GPIO_InitStructure);//初始化PA11,PA12
//	
//	  //引脚复用映射配置
//	  GPIO_PinAFConfig(GPIOA,GPIO_PinSource11,GPIO_AF_CAN1); //GPIOA11复用为CAN1
//	  GPIO_PinAFConfig(GPIOA,GPIO_PinSource12,GPIO_AF_CAN1); //GPIOA12复用为CAN1
//	  
//  	//CAN单元设置
//   	CAN_InitStructure.CAN_TTCM=DISABLE;	//非时间触发通信模式   
//  	CAN_InitStructure.CAN_ABOM=DISABLE;	//软件自动离线管理	  
//  	CAN_InitStructure.CAN_AWUM=DISABLE;//睡眠模式通过软件唤醒(清除CAN->MCR的SLEEP位)
//  	CAN_InitStructure.CAN_NART=ENABLE;	//禁止报文自动传送 
//  	CAN_InitStructure.CAN_RFLM=DISABLE;	//报文不锁定,新的覆盖旧的  
//  	CAN_InitStructure.CAN_TXFP=DISABLE;	//优先级由报文标识符决定 
//  	CAN_InitStructure.CAN_Mode= mode;	 //模式设置 
//  	CAN_InitStructure.CAN_SJW=tsjw;	//重新同步跳跃宽度(Tsjw)为tsjw+1个时间单位 CAN_SJW_1tq~CAN_SJW_4tq
//  	CAN_InitStructure.CAN_BS1=tbs1; //Tbs1范围CAN_BS1_1tq ~CAN_BS1_16tq
//  	CAN_InitStructure.CAN_BS2=tbs2;//Tbs2范围CAN_BS2_1tq ~	CAN_BS2_8tq
//  	CAN_InitStructure.CAN_Prescaler=brp;  //分频系数(Fdiv)为brp+1	
//  	CAN_Init(CAN1, &CAN_InitStructure);   // 初始化CAN1 
//    
//		//配置过滤器并且过滤器不使用
// 	  CAN_FilterInitStructure.CAN_FilterNumber=0;	  //过滤器0
//  	CAN_FilterInitStructure.CAN_FilterMode=CAN_FilterMode_IdMask; 
//  	CAN_FilterInitStructure.CAN_FilterScale=CAN_FilterScale_32bit; //32位 
//  	CAN_FilterInitStructure.CAN_FilterIdHigh=0x0000;////32位ID
//  	CAN_FilterInitStructure.CAN_FilterIdLow=0x0000;
//  	CAN_FilterInitStructure.CAN_FilterMaskIdHigh=0x0000;//32位MASK//滤波不使用，只发送
//  	CAN_FilterInitStructure.CAN_FilterMaskIdLow=0x0000;
//   	CAN_FilterInitStructure.CAN_FilterFIFOAssignment=CAN_Filter_FIFO0;//过滤器0关联到FIFO0
//  	CAN_FilterInitStructure.CAN_FilterActivation=ENABLE; //激活过滤器0
//  	CAN_FilterInit(&CAN_FilterInitStructure);//滤波器初始化
//		
//#if CAN1_RX0_INT_ENABLE
//	
//	  CAN_ITConfig(CAN1,CAN_IT_FMP0,ENABLE);//FIFO0消息挂号中断允许.		    
//  
//  	NVIC_InitStructure.NVIC_IRQChannel = CAN1_RX0_IRQn;
//  	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 1;     // 主优先级为1
//  	NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;            // 次优先级为0
//  	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;
//  	NVIC_Init(&NVIC_InitStructure);
//#endif
//	return 0;
//}   
// 
//#if CAN1_RX0_INT_ENABLE	//使能RX0中断
////中断服务函数			    
//void CAN1_RX0_IRQHandler(void)
//{
//  	CanRxMsg RxMessage;
//	int i=0;
//    CAN_Receive(CAN1, 0, &RxMessage);
//	for(i=0;i<8;i++)
//	printf("rxbuf[%d]:%d\r\n",i,RxMessage.Data[i]);
//}
//#endif

////can发送一组数据(固定格式:ID为0X12,标准帧,数据帧)	
////len:数据长度(最大为8)				     
////msg:数据指针,最大为8个字节.
////返回值:0,成功;
////		 其他,失败;
////can总线上的节点接收和发送数据都是以帧为单位，即8个字节
////发送里面的id和筛选器里面的id不是同一个意思，
//u8 CAN1_Send_Msg(u8* msg,u8 len,u32 id)
//{	
//  u8 mbox;
//  u16 i=0;
//  CanTxMsg TxMessage;
//  TxMessage.StdId=id;	 // 标准标识ID为0到0x7FF 如果发送扩展帧不用管它 A左后 B右前  C左前  D右后
//  TxMessage.ExtId=0x12;	 // 设置扩展标示符ID（29位）0到0x1FFFFFFF 如果发送标准帧不用管它
//  TxMessage.IDE=0;		  // 使用标准标识符
//  TxMessage.RTR=0;		  // 消息类型为数据帧，一帧8位
//  TxMessage.DLC=len;							 // 发送两帧信息
//  for(i=0;i<len;i++)
//  TxMessage.Data[i]=msg[i];				 // 第一帧信息          
//  mbox=CAN_Transmit(CAN1, &TxMessage);   
//  i=0;
//  while((CAN_TransmitStatus(CAN1, mbox)==CAN_TxStatus_Failed)&&(i<0XFFF))i++;	//等待发送结束
//  if(i>=0XFFF)return 1;
//  return 0;		
//}

////can口接收数据查询
////buf:数据缓存区;	 
////返回值:0,无数据被收到;
////		 其他,接收的数据长度;
//u8 CAN1_Receive_Msg(u8 *buf)
//{		   		   
// 	u32 i;
//	CanRxMsg RxMessage;
//  if( CAN_MessagePending(CAN1,CAN_FIFO0)==0)return 0;		//没有接收到数据,直接退出 
//  CAN_Receive(CAN1, CAN_FIFO0, &RxMessage);//读取数据	
//  for(i=0;i<RxMessage.DLC;i++)
//	{
//		buf[i]=RxMessage.Data[i];  
////		printf("%d\r\n",RxMessage.Data[i]);
//	}  
//	return RxMessage.DLC;	
//}
//		
//u8 canbuf[8];
//u8 qlk[8];

////void Place_LF_init(void)
////{
////	int b=1000;//单位转
////	int speed=b*8192/3000;
////  //使用位置模式
////	canbuf[0]=0x00;
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00;
////	canbuf[3]=0x19;
////	canbuf[4]=0x00;
////	canbuf[5]=0x00;
////	canbuf[6]=0x00;	
////	canbuf[7]=0x3F;
////	CAN1_Send_Msg(canbuf,8,0X0C);
//// delay_ms(5);
//////设置电机的加减速参数
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x12; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x0A; 
////	canbuf[7]=0x0A;//	0x0A
////	CAN1_Send_Msg(canbuf,8,0X0C);
//// delay_ms(5);
//////设置电机允许运行的最高速度或者匀速速度
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x14; 
////	canbuf[4]=(speed >> 24) & 0XFF;
////  canbuf[5]=(speed >> 16) & 0XFF;
////	canbuf[6]=(speed >> 8) & 0XFF;
////	canbuf[7]=speed & 0XFF;
//////		canbuf[6]=0x01;
//////	canbuf[7]=0x11;	
////	CAN1_Send_Msg(canbuf,8,0X0C);
//// delay_ms(5);
//////设置位置模式控制字
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x17; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x4F;	
////	CAN1_Send_Msg(canbuf,8,0X0C);
//// delay_ms(5);
////	//设置电机启动使能
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x10; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x1F;	
////	CAN1_Send_Msg(canbuf,8,0X0C);
////	//报警复位
////	 delay_ms(5);
//// }
////void Place_LR_init(void)
////{
////	int b=1000;//单位转
////	int speed=b*8192/3000;
////  //使用位置模式
////	canbuf[0]=0x00;
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00;
////	canbuf[3]=0x19;
////	canbuf[4]=0x00;
////	canbuf[5]=0x00;
////	canbuf[6]=0x00;	
////	canbuf[7]=0x3F;
////	CAN1_Send_Msg(canbuf,8,0X0A);
//// delay_ms(5);
//////设置电机的加减速参数
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x12; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x0A; 
////	canbuf[7]=0x0A;//	0x0A
////	CAN1_Send_Msg(canbuf,8,0X0A);
//// delay_ms(5);
//////设置电机允许运行的最高速度或者匀速速度
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x14; 
////	canbuf[4]=(speed >> 24) & 0XFF;
////  canbuf[5]=(speed >> 16) & 0XFF;
////	canbuf[6]=(speed >> 8) & 0XFF;
////	canbuf[7]=speed & 0XFF;
//////		canbuf[6]=0x01;
//////	canbuf[7]=0x11;	
////	CAN1_Send_Msg(canbuf,8,0X0A);
//// delay_ms(5);
//////设置位置模式控制字
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x17; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x4F;	
////	CAN1_Send_Msg(canbuf,8,0X0A);
//// delay_ms(5);
////	//设置电机启动使能
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x10; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x1F;	
////	CAN1_Send_Msg(canbuf,8,0X0A);
////	//报警复位
////	 delay_ms(5);
//// }	
////void Place_RF_init(void)
////{
////	int b=1000;//单位转
////	int speed=b*8192/3000;
////  //使用位置模式
////	canbuf[0]=0x00;
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00;
////	canbuf[3]=0x19;
////	canbuf[4]=0x00;
////	canbuf[5]=0x00;
////	canbuf[6]=0x00;	
////	canbuf[7]=0x3F;
////	CAN1_Send_Msg(canbuf,8,0X0B);
//// delay_ms(5);
//////设置电机的加减速参数
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x12; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x0A; 
////	canbuf[7]=0x0A;//	0x0A
////	CAN1_Send_Msg(canbuf,8,0X0B);
//// delay_ms(5);
//////设置电机允许运行的最高速度或者匀速速度
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x14; 
////	canbuf[4]=(speed >> 24) & 0XFF;
////  canbuf[5]=(speed >> 16) & 0XFF;
////	canbuf[6]=(speed >> 8) & 0XFF;
////	canbuf[7]=speed & 0XFF;
////	CAN1_Send_Msg(canbuf,8,0X0B);
//// delay_ms(5);
//////设置位置模式控制字
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x17; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x4F;	
////	CAN1_Send_Msg(canbuf,8,0X0B);
//// delay_ms(5);
////	//设置电机启动使能
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x10; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x1F;	
////	CAN1_Send_Msg(canbuf,8,0X0B);
////	//报警复位
////	 delay_ms(5);
//// }		
////void Place_RR_init(void)
////{
////	int b=1000;//单位转
////	int speed=b*8192/3000;
////  //使用位置模式
////	canbuf[0]=0x00;
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00;
////	canbuf[3]=0x19;
////	canbuf[4]=0x00;
////	canbuf[5]=0x00;
////	canbuf[6]=0x00;	
////	canbuf[7]=0x3F;
////	CAN1_Send_Msg(canbuf,8,0X0D);
//// delay_ms(5);
//////设置电机的加减速参数
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x12; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x0A; 
////	canbuf[7]=0x0A;//	0x0A
////	CAN1_Send_Msg(canbuf,8,0X0D);
//// delay_ms(5);
//////设置电机允许运行的最高速度或者匀速速度
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x14; 
////	canbuf[4]=(speed >> 24) & 0XFF;
////  canbuf[5]=(speed >> 16) & 0XFF;
////	canbuf[6]=(speed >> 8) & 0XFF;
////	canbuf[7]=speed & 0XFF;
////	CAN1_Send_Msg(canbuf,8,0X0D);
//// delay_ms(5);
//////设置位置模式控制字
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x17; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x4F;	
////	CAN1_Send_Msg(canbuf,8,0X0D);
//// delay_ms(5);
////	//设置电机启动使能
////	canbuf[0]=0x00; 
////	canbuf[1]=0xDA; 
////	canbuf[2]=0x00; 
////	canbuf[3]=0x10; 
////	canbuf[4]=0x00;
////	canbuf[5]=0x00; 
////	canbuf[6]=0x00; 
////	canbuf[7]=0x1F;	
////	CAN1_Send_Msg(canbuf,8,0X0D);
////	//报警复位
////	 delay_ms(5);
//// }
////void Place_mode_init(void)
////{
////	Place_LF_init();
////	delay_ms(200);
////	Place_LR_init();
////	delay_ms(200);
////	Place_RF_init();
////	delay_ms(200);
////	Place_RR_init();
////	delay_ms(200);
////}
//	double c[4];
//	double adcx[4];
//void AD_Reset(void)
//{
//   u8 AD_Reset_Num[4]={1,2,3,4};
//		if(AD_Reset_Num[0]==1)//左前
//		{
//			adcx[0]=Get_Adc_Average(ADC_Channel_11,50);//获取通道5的转换值，20次取平均//PF4B右前通道14  PF5A左后通道15  PF3D右后通道9   PC1C左前通道11
//			if(adcx[0]>=1075&&adcx[0]<=1085);
//			else if(adcx[0]<1075)
//			{
//				adcx[0]=adcx[0]-1080; //adcx[0]=adcx[0]-1075;取中间值1080误差会更小//右后和左前adcx=adcx-1000;    右前和左后adcx=1100-adcx;
//				c[0]=345*adcx[0]/4096;
//			}
//			else
//			{
//				adcx[0]=adcx[0]-1080;//adcx[0]=adcx[0]-1085;取中间值1080误差会更小//右后和左前adcx=adcx-1000;   右前和左后adcx=1100-adcx;
//				c[0]=345*adcx[0]/4096;
//			}
//		}
//				if(AD_Reset_Num[1]==2)//右后
//		{
//			adcx[1]=Get_Adc_Average(ADC_Channel_9,50);//获取通道5的转换值，20次取平均//PF4B右前通道14  PF5A左后通道15  PF3D右后通道9   PC1C左前通道11
//			if(adcx[1]>=1065&&adcx[1]<=1075);
//			else if(adcx[1]<1065)
//			{
//				adcx[1]=adcx[1]-1070;//右后和左前adcx=adcx-1000;    右前和左后adcx=1100-adcx;
//				c[1]=345*adcx[1]/4096;
//			}
//			else
//			{
//				adcx[1]=adcx[1]-1070;//右后和左前adcx=adcx-1000;   右前和左后adcx=1100-adcx;
//				c[1]=345*adcx[1]/4096;
//			}
//		}
//		
//				if(AD_Reset_Num[2]==3)//右前
//		{
//			adcx[2]=Get_Adc_Average(ADC_Channel_14,50);//获取通道5的转换值，20次取平均//PF4B右前通道14  PF5A左后通道15  PF3D右后通道9   PC1C左前通道11
//			if(adcx[2]>=1055&&adcx[2]<=1065);
//			else if(adcx[2]<1055)
//			{
//				adcx[2]=1060-adcx[2];//右后和左前adcx=adcx-1000;    右前和左后adcx=1100-adcx;
//				c[2]=345*adcx[2]/4096;
//			}
//			else
//			{
//				adcx[2]=1060-adcx[2];//右后和左前adcx=adcx-1000;   右前和左后adcx=1100-adcx;
//				c[2]=345*adcx[2]/4096;
//			}
//		}
//		
//				if(AD_Reset_Num[3]==4)//左后
//		{
//			adcx[3]=Get_Adc_Average(ADC_Channel_15,50);//获取通道5的转换值，20次取平均//PF4B右前通道14  PF5A左后通道15  PF3D右后通道9   PC1C左前通道11
//			if(adcx[3]>=1065&&adcx[3]<=1075);
//			else if(adcx[3]<1065)
//			{
//				adcx[3]=1070-adcx[3];//右后和左前adcx=adcx-1000;    右前和左后adcx=1100-adcx;
//				c[3]=345*adcx[3]/4096;
//			}
//			else
//			{
//				adcx[3]=1070-adcx[3];//右后和左前adcx=adcx-1000;   右前和左后adcx=1100-adcx;
//				c[3]=345*adcx[3]/4096;
//			}
//		}	
////	delay_ms(500);	
//  send_place_AD(c[0],c[1],c[2],c[3]);	//左前，右后 右前 左后
//}

//void Send_Place(double h,double i,double j,double k)//左前，右后，
//{
//	
//	h=radian*h;i=radian*i;j=radian*j;k=radian*k;//弧度转化为角度
//	int Position;
//	if(h<-90)h=-90;if(i<-90)i=-90;if(j<-90)j=-90;if(k<-90)k=-90;
//	if(h>90)h=90;if(i>90)i=90;if(j>90)j=90;if(k>90)k=90;
//	if(h>=0)//左前
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;
//		h=h+c[0];//h=h+c[0]; c[0]-h
//		Position=coefficient*h/3;//4000转360°，减速比为50故200000转360°
//		canbuf[0]=0x00;
//	  canbuf[1]=0xDA; 
//	  canbuf[2]=0x00; 
//	  canbuf[3]=0x12; 
//	  canbuf[4]=0x00;
//	  canbuf[5]=0x00; 
//	  canbuf[6]=acceleration; 
//	  canbuf[7]=deceleration;
//	  CAN1_Send_Msg(canbuf,8,0X0C);//设置加减速时间
//		delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);//设置最高速度
//    delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);//设置目标位置
//		delay_ms(delaytime);

//	}
//	else//左前
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;
//		h=h+c[0];
//		h=-h;	
//		Position=coefficient*h/3;
//		Position=~Position;
//		Position=Position+1;
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;
//		CAN1_Send_Msg(canbuf,8,0X0C);//设置加减速时间
//		delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);//设置最高速度
//    delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);//设置目标位置
//    delay_ms(delaytime);

//	}
//		if(i>=0)//右后
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;	
//		i=c[1]+i;
//		Position=coefficient*i/3;//4000转360°，减速比为50故200000转360°，
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0D);//设置加减速时间
//		delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);//设置最高速度
//    delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);//设置目标位置
//    delay_ms(delaytime);
//	}
//	else//右后
//	{
//	  int b=turn;//单位转
//	  int speed=b*8192/3000;
//		i=c[1]+i;
//		i=-i;	
//		Position=coefficient*i/3;
//		Position=~Position;
//		Position=Position+1;
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0D);//设置加减速时间
//    delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);//设置最高速度
//		delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);//设置目标位置
//    delay_ms(delaytime);
//	}
//	
//		if(j>=0)//右前
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;
//		j=c[2]-j;
//		Position=coefficient*j/3;//4000转360°，减速比为50故200000转360°，
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0B);//设置加减速时间
//		delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);//设置最高速度
//    delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);//设置目标位置
//    delay_ms(delaytime);
//	}
//	else//右前
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;
//		j=c[2]-j;
//		j=-j;	
//		Position=coefficient*j/3;
//		Position=~Position;
//		Position=Position+1;
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0B);//设置加减速时间
//		delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);//设置最高速度
//    delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);//设置目标位置
//    delay_ms(delaytime);
//	}

//	if(k>=0)//左后
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;
//		k=c[3]-k;
//		Position=coefficient*k/3;//4000转360°，减速比为50故200000转360°，
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0A);//设置加减速时间
//    delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);//设置最高速度
//		delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);//设置目标位置
//		delay_ms(delaytime);
//	}
//	else
//	{
//		int b=turn;//单位转
//	  int speed=b*8192/3000;
//		k=c[3]-k;
//		k=-k;	
//		Position=coefficient*k/3;
//		Position=~Position;
//		Position=Position+1;
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=acceleration; 
//		canbuf[7]=deceleration;
//		CAN1_Send_Msg(canbuf,8,0X0A);//设置加减速时间
//		delay_ms(delaytime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);//设置最高速度
//		delay_ms(delaytime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(Position >> 24) & 0XFF;
//		canbuf[5]=(Position >> 16) & 0XFF;
//		canbuf[6]=(Position >> 8) & 0XFF;
//		canbuf[7]=Position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);//设置目标位置
//		delay_ms(delaytime);
//	}
//}




//void send_place_AD(double a,double b,double c,double d)
//{
//	int position;
//	if(a>=0)//左前
//	{
//		position=coefficient*a/3;//4000转360°，减速比为50故200000转360°，
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置位置模式控制字
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置电机启动使能
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//	}
//	else//左前
//	{
//		a=-a;	
//		position=coefficient*a/3;
//		position=~position;
//		position=position+1;
//    int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置位置模式控制字
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		//设置电机启动使能
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0C);
//		delay_ms(delayinittime);
//	}

//		if(b>=0)//右后
//	{
//		position=coefficient*b/3;//4000转360°，减速比为50故200000转360°，
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置位置模式控制字
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置电机启动使能
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//	}
//	else
//	{
//		b=-b;	
//		position=coefficient*b/3;
//		position=~position;
//		position=position+1;
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置位置模式控制字
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		//设置电机启动使能
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0D);
//		delay_ms(delayinittime);
//	}
//	
//		if(c>=0)//右前
//	{
//		position=coefficient*c/3;//4000转360°，减速比为50故200000转360°，
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置位置模式控制字
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置电机启动使能
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//	}
//	else
//	{
//		c=-c;	
//		position=coefficient*c/3;
//		position=~position;
//		position=position+1;
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置位置模式控制字
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		//设置电机启动使能
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0B);
//		delay_ms(delayinittime);
//	}



//	if(d>=0)//左后
//	{
//		position=coefficient*d/3;//4000转360°，减速比为50故200000转360°，
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//	}
//	else
//	{
//		d=-d;	
//		position=coefficient*d/3;
//		position=~position;
//		position=position+1;
//		int b=turn;//单位转
//		int speed=b*8192/3000;
//		//使用位置模式
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00;
//		canbuf[3]=0x19;
//		canbuf[4]=0x00;
//		canbuf[5]=0x00;
//		canbuf[6]=0x00;	
//		canbuf[7]=0x3F;
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		//设置电机的加减速参数
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x12; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x01; 
//		canbuf[7]=0x01;//	0x0A
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		//设置电机允许运行的最高速度或者匀速速度
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x14; 
//		canbuf[4]=(speed >> 24) & 0XFF;
//		canbuf[5]=(speed >> 16) & 0XFF;
//		canbuf[6]=(speed >> 8) & 0XFF;
//		canbuf[7]=speed & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x17; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x4F;	
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00; 
//		canbuf[1]=0xDA; 
//		canbuf[2]=0x00; 
//		canbuf[3]=0x10; 
//		canbuf[4]=0x00;
//		canbuf[5]=0x00; 
//		canbuf[6]=0x00; 
//		canbuf[7]=0x1F;	
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//		canbuf[0]=0x00;
//		canbuf[1]=0xDA;
//		canbuf[2]=0x00;
//		canbuf[3]=0x16;
//		canbuf[4]=(position >> 24) & 0XFF;
//		canbuf[5]=(position >> 16) & 0XFF;
//		canbuf[6]=(position >> 8) & 0XFF;
//		canbuf[7]=position & 0XFF;
//		CAN1_Send_Msg(canbuf,8,0X0A);
//		delay_ms(delayinittime);
//	}
//		delay_ms(500);
//		delay_ms(500);
//		delay_ms(500);
//		delay_ms(500);
//		PFout(15)=1;//喇叭	
//		delay_ms(500);
//		PFout(15)=0;//喇叭
//}


