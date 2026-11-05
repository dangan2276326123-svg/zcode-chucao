#include "sys.h"
#include "uart2.h"	
#include "delay.h"
#include "CRC2.h"
#include "path_plan.h"
#include "uart5.h"
#include "uart4.h"
#include "path_plan.h"

u8 USART_RX_BUF4[100];     //接收缓冲,最大USART_REC_LEN个字节.
extern double control_flag[6];

extern double transmission_ratio_steer;//  伺服电机到车轮
double manual_contorl[12]={0}; //0表示行驶模式；1表示停车；2 表示角度，3表示速度
u8 UART4_RX_BUF[64];                   //接收缓冲，最大64字节
u8 UART4_RX_CNT=0;                       //接收字节计数器
u8 flagFrame4=0;                         //帧接收完成标志，即接收到一帧新数据

void uart4_init(u32 bound)
	{
   //GPIO端口设置
  GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOC,ENABLE); //使能GPIOA时钟
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_UART4,ENABLE);//使能USART2时钟

	//串口5对应引脚复用映射

	GPIO_PinAFConfig(GPIOC,GPIO_PinSource10,GPIO_AF_UART4); //GPIOA2复用为USART2
	GPIO_PinAFConfig(GPIOC,GPIO_PinSource11,GPIO_AF_UART4); //GPIOA3复用为USART2

	//USART5端口配置
  GPIO_InitStructure.GPIO_Pin =GPIO_Pin_11|GPIO_Pin_10; //GPIOA9与GPIOA10
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;	//速度50MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP; //上拉
	GPIO_Init(GPIOC,&GPIO_InitStructure); //初始化PA9，PA10


	
	

   //USART5 初始化设置
	USART_InitStructure.USART_BaudRate = bound;//波特率设置
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;//字长为8位数据格式
	USART_InitStructure.USART_StopBits = USART_StopBits_1;//一个停止位
	USART_InitStructure.USART_Parity = USART_Parity_No;//无奇偶校验位
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//无硬件数据流控制
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;	//收发模式

  USART_Init(UART4, &USART_InitStructure); //初始化串口5


  USART_Cmd(UART4, ENABLE);  //使能串口5

	USART_ITConfig(UART4, USART_IT_RXNE, ENABLE);//开启相关中断


	NVIC_InitStructure.NVIC_IRQChannel = UART4_IRQn;//串口5中断通道
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=0;//抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority =1;		//子优先级3
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			//IRQ通道使能
	NVIC_Init(&NVIC_InitStructure);	//根据指定的参数初始化VIC寄存器、
}



u8 state4=0;//接收状态
u8 uart_byte_count4=0;        //接收到的数据长度

u8 recive_flag4=0;



void UART4_IRQHandler(void)                	//串口5中断服务程序
{
			u8 res;	                                    //定义数据缓存变量
	if(USART_GetITStatus(UART4, USART_IT_RXNE) != RESET)//接收到数据
	{	 	
		res =USART_ReceiveData(UART4);//;读取接收到的数据USART2->DR
		if(UART4_RX_CNT<sizeof(UART4_RX_BUF))    //一次只能接收64个字节，人为设定，可以更大，但浪费时间
		{
			UART4_RX_BUF[UART4_RX_CNT]=res;  //记录接收到的值
			UART4_RX_CNT++;        //使收数据增加1 
		}
	}
//	u8 Res;
//	//printf("X %d\r\n",568);
//	
//	if(USART_GetITStatus(UART4, USART_IT_RXNE) != RESET)  //接收中断(接收到的数据必须是0x0d 0x0a结尾)
//	{
//		Res =USART_ReceiveData(UART4);//(USART1->DR);	//读取接收到的数据
//	//	printf("123\r\n");
//		if(state4==0&&Res==0xFD)//开启接收
//			{
//					state4=1;
//					uart_byte_count4=0x00; 
//			
//			}
//		if(state4==2)//接收完成
//			{
//					state4=0;
//					//解析代码
//	//  	printf(" %d %d %d %d %d\r\n",USART_RX_BUF2[1],USART_RX_BUF2[2],USART_RX_BUF2[3],USART_RX_BUF2[4],USART_RX_BUF2[5]);

//				
//			if (recive_flag4==0)	
//			{
//				manual_contorl[0]=USART_RX_BUF4[1];///0表示行驶模式；1表示停车；2 表示角度，3表示速度
//				manual_contorl[1]=USART_RX_BUF4[2];//停车	
//				
//				if(USART_RX_BUF4[5]==1)				
//				manual_contorl[2]=USART_RX_BUF4[6]+USART_RX_BUF4[7]/100.0; //作业角度		
//				if(USART_RX_BUF4[5]==0)				
//				manual_contorl[2]=-(USART_RX_BUF4[6]+USART_RX_BUF4[7]/100.0); //作业角度		

//				
//				if(USART_RX_BUF4[8]==1)				
//				manual_contorl[3]=USART_RX_BUF4[9]+USART_RX_BUF4[10]/100.0; //作业角度		
//				if(USART_RX_BUF4[8]==0)				
//				manual_contorl[3]=-(USART_RX_BUF4[9]+USART_RX_BUF4[10]/100.0); //作业角度		

//			
//	//	printf("行走%f 停车%f 角度%f 速度%f\r\n",manual_contorl[0],manual_contorl[1],manual_contorl[2],manual_contorl[3]);

//			}		
//					
//	
//				
//			}
//		if(state4==1)//一位位接收数据并装入缓存
//			{
//					USART_RX_BUF4[uart_byte_count4]=Res;
//					uart_byte_count4++;
//					if(Res==0xFC)//停止字符
//						state4=2;
//			}
//		 		 
//  } 

}

void UART4_Put_Char(unsigned char DataToSend)
{
  while(USART_GetFlagStatus(UART4,USART_FLAG_TC)==RESET);//循环发送,直到发送完毕   
			USART_SendData(UART4,DataToSend); 
}


void mosbus_EN(u8 adress )
{
	  char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;
	
	
		temp_send=adress;  //1号电机
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x060000;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0001;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		
		for(i=0;i<8;i++)
		{
		UART4_Put_Char(ByteSend2[i]);
		}		
	
}

void motor_EN(u8 adress )
{
	  char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;
	
	
		temp_send=adress;  //1号电机
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x060001;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0001;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		
		for(i=0;i<8;i++)
		{
		UART4_Put_Char(ByteSend2[i]);
		}		
	
}

void motor_speed(u8 adress,int speed )
{
	  char ByteSend2[8]={0};//绝对位置设置的字节 01 06 00 02 05 DC 2A C3
		int i=0;
		uint32_t  temp_send;
	
	
		temp_send=adress;  //1号电机
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x060002;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=speed;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		
		for(i=0;i<8;i++)
		{
		UART4_Put_Char(ByteSend2[i]);
		}		
	
}
void send_angle(u8 adress,double angle)
{
char ByteSend2[13]={0};//用来设置伺服电机绝对位置的字节数组  后面要用485通讯发送给伺服电机
		int i=0;
		uint32_t  temp_send;
		
		int angle2;
            
		angle2 =transmission_ratio_steer*angle*32768.0/2/pi;//angle*150/5*5=时车轮要偏转的圈数  angle是要转动的弧度值     800
    //angle*R（150mm）是对应的弧长 此处约等于丝杆滑块要移动的距离  /5是因为丝杆转一圈移动5mm  /5能算出丝杆要走的圈数 之间还有一个减速器 所以*5得到伺服电机应该转动的圈数
      //目前伺服电机转一圈是32768个脉冲 所以 *32768就是这次转动所需要的总的脉冲数   原来是(32768.0*1005.0/2/pi)*angle 现在我给改成了150.0*angle*32768.0; 其实差不多的 1005/2/3.14约等于 160 而我是150
     // 转动的快慢关键是要修改伺服电机转动一圈的脉冲数 它少点 那就转的快点
     //或者说想要转的更快 就让他那个angle_add多一点呗

		
//		if(angle2>4000000)  //最多只运行转半圈
//			angle2=2000000;                        //这个二驱小车 左转200万 25°左右  右转极限-235万  25度左右
//		if(angle2<-2350000)
//			angle2=-2350000;
		if(angle==0)
			angle2=1;  ////////////////伺服电机就是这样规定的  发1就是
		//angle2 = 2000000;
//		printf("                                                                         脉冲 %d \r\n",angle2);
		temp_send=adress;
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x100016;			
		
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x000204;		
		ByteSend2[4] = (temp_send>>16) & 0xFF;	
		ByteSend2[5] = (temp_send>>8) & 0xFF;
		ByteSend2[6] = temp_send & 0xFF;	
		
		temp_send=angle2;	
		ByteSend2[9] = (temp_send>>24) & 0xFF;//低位在前，高位在后
		ByteSend2[10] = (temp_send>>16) & 0xFF;	
		ByteSend2[7] = (temp_send>>8) & 0xFF;
		ByteSend2[8] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],11);

		ByteSend2[11] = (temp_send>>8) & 0xFF;
		ByteSend2[12] = temp_send & 0xFF;		
			
		
		for(i=0;i<13;i++)
		{
		UART4_Put_Char(ByteSend2[i]);
		}		


}








void UartRxMonitor4(u8 ms)//串口接收监控
{
	static u8 USART4_RX_BKP=0;  //定义USART2_RC_BKP暂时存储诗句长度与实际长度比较
	static u8 idletmr4=0;        //定义监控时间
	if(UART4_RX_CNT>0)//接收计数器大于零时，监控总线空闲时间
	{
		if(USART4_RX_BKP!=UART4_RX_CNT) //接收计数器改变，即刚接收到数据时，清零空闲计时
		{
			USART4_RX_BKP=UART4_RX_CNT;  //赋值操作，将实际长度给USART2_RX_BKP
			idletmr4=0;                    //将监控时间清零
		}
		else                              ////接收计数器未改变，即总线空闲时，累计空闲时间
		{
			//如果在一帧数据完成之前有超过3.5个字节时间的停顿，接收设备将刷新当前的消息并假定下一个字节是一个新的数据帧的开始
			if(idletmr4<5)                  //空闲时间小于1ms时，持续累加
			{
				idletmr4 +=ms;
				if(idletmr4>=5&&UART4_RX_CNT>6)             //空闲时间达到1ms时，即判定为1帧接收完毕
				{
					flagFrame4=1;//设置命令到达标志，帧接收完毕标志
				}
			}
		}
	}
	else
	{
		USART4_RX_BKP=0;
	}
}	

u8 Uart4Read(u8 *buf, u8 len)  
{
	 u8 i;
	if(len>UART4_RX_CNT)  //指定读取长度大于实际接收到的数据长度时
	{
		len=UART4_RX_CNT; //读取长度设置为实际接收到的数据长度
	}
	for(i=0;i<len;i++)  //拷贝接收到的数据到接收指针中
	{
		*buf=UART4_RX_BUF[i];  //将数据复制到buf中
		UART4_RX_BUF[i]=0;
		buf++;
	}
	UART4_RX_CNT=0;              //接收计数器清零
	return len;                   //返回实际读取长度
}

void  manua_control(u8 adress)   //手动 5，除草一 6，除草二 7，喷药 8 ，摇头一 9，摇头二 10 ，施肥 11
{
	//发送指令
// 0行走方式 1 停车 2作业机构，3号待定 4 角度符号 5角度整数 6角度小数 7速度符号 8速度整数 9速度小数
	char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;

//	unsigned charcnt;
	unsigned int crc;
	unsigned char crch,crcl;
	 u8 len;
	static u8 buf[60];
	

	
	if(adress==5) //手动控制，只需要读即可
	{
			 temp_send=0x050300;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
				
				temp_send=0x00000A;	
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}
			delay_ms(150);	
				
//			while(flagFrame==0)            //帧接收完成标志，即接收到一帧新数据
//				{
//				}	
				if(flagFrame4==1)
					
				{
					flagFrame4=0;           //帧接收完成标志清零
					len = Uart4Read(buf,sizeof(buf));   //将接收到的命令读到缓冲区中
					//printf("ch5 %d %d %d %d %d %d %d %d %d\r\n",buf[0],buf[1],buf[2],buf[3],buf[4],buf[5],buf[6],buf[7],buf[8],buf[9],buf[10],buf[11]);
					if(buf[0]==0x05)                   //判断地址是不是0x00
					{
						
						crc=Crc16withTable(buf,len-2);       //计算CRC校验值，出去CRC校验值
						crch=crc>>8;    				//crc高位
						crcl=crc&0xFF;					//crc低位
				//		printf("ch0 crch = %d %d crcl = %d %d\r\n",buf[7],crch,buf[8],crcl);
						if((buf[len-2]==crch)&&(buf[len-1]==crcl))  //判断CRC校验是否正确
						{
					//		adcx[0]=buf[4]*256+buf[6];
					
							manual_contorl[0]=buf[4];///0表示行驶模式；1表示停车；2 表示角度，3表示速度	
							manual_contorl[1]=buf[6];//停车			
							if(buf[12]==1)				
									manual_contorl[2]=buf[14]+buf[16]/100.0; //作业角度		
							if(buf[12]==0)				
									manual_contorl[2]=-(buf[14]+buf[16]/100.0); //作业角度
							
							if(buf[18]==1)				
							manual_contorl[3]=buf[20]+buf[22]/100.0; //作业速度		
							if(buf[18]==0)				
							manual_contorl[3]=-(buf[20]+buf[22]/100.0); //作业速度	
								
			
						//printf("行走%f 停车%f 角度%f 速度%f\r\n",manual_contorl[0],manual_contorl[1],manual_contorl[2],manual_contorl[3]);	
							
							
						}
						
					}
					
				}
	
			}		
}

extern double control_flag[6];//0行驶还是停车，1前进还是后退，2转向方式，3角度值，4速度值，5作业机构是否起降
extern int sbus_channel[16];//解析后的通道数据
void  work_send_control(u8 adress)   //，除草一 6，除草二 7，喷药 8 ，摇头一 9，摇头二 10 ，施肥 11
{
	//发送指令
//  0作业状态	1速度整数	2速度小数  3 X整数高位	4X整数低位	5X小数高位	 6X小数低位	7Y整数高位	 8Y整数低位	9Y小数高位 	10Y小数低位 11预留	12预留	13预留	14预留	15预留
	char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;


///////////////////////////////////////////////////////////////////////////////////	
	if(adress==6) //除草一，只需要写即可
			{
			 temp_send=0x060600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) //如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
			delay_ms(10);	
			}
				
	 if(adress==7) //除草二，只需要写即可
			{
			 temp_send=0x070600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) //如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
			delay_ms(10);	
			}
///////////////////////////////////////////////////////////////////////////////////	
		 if(adress==8) //除草二，只需要写即可
			{
			 temp_send=0x080600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) //如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
			delay_ms(10);	
			}
	if(adress==9) //除草二，只需要写即可
			{
			 temp_send=0x090600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400))//如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
			delay_ms(10);	
			}
			
if(adress==11) //撒肥
			{
			 temp_send=0x0B0600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) 
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}
			delay_ms(30);
				/////////////////车速	     			
			temp_send=0x0B060001;	
			    ByteSend2[0] = (temp_send>>24) & 0xFF;
				ByteSend2[1] = (temp_send>>16) & 0xFF;
				ByteSend2[2] = (temp_send>>8) & 0xFF;
				ByteSend2[3] = temp_send & 0xFF;		
			
				temp_send=(int) ((control_flag[4]+0.1)*100);
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;
			//delay_ms(20);
			for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
				
			delay_ms(10);
				
			}
			
			
if(adress==12) //撒肥
			{
			 temp_send=0x0C0600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) //如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}

				delay_ms(30);
				/////////////////车速	     			
			temp_send=0x0C060001;	
			    ByteSend2[0] = (temp_send>>24) & 0xFF;
				ByteSend2[1] = (temp_send>>16) & 0xFF;
				ByteSend2[2] = (temp_send>>8) & 0xFF;
				ByteSend2[3] = temp_send & 0xFF;		
			
				temp_send=(int) ((control_flag[4]+0.1)*100);
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;
			//delay_ms(20);
			for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}				
				
			delay_ms(10);	
			}			
						
	if(adress==13) //撒肥
			{
			 temp_send=0x0D0600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) //如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}
				delay_ms(30);
				/////////////////车速	     			
			temp_send=0x0D060001;	
			    ByteSend2[0] = (temp_send>>24) & 0xFF;
				ByteSend2[1] = (temp_send>>16) & 0xFF;
				ByteSend2[2] = (temp_send>>8) & 0xFF;
				ByteSend2[3] = temp_send & 0xFF;		
			
				temp_send=(int) ((control_flag[4]+0.1)*100);
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;
			//delay_ms(20);
			for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	

				
			delay_ms(10);	
			}			
					
if(adress==14) //撒肥
			{
			 temp_send=0x0E0600;
				ByteSend2[0] = (temp_send>>16) & 0xFF;
				ByteSend2[1] = (temp_send>>8) & 0xFF;
				ByteSend2[2] = temp_send & 0xFF;	
	
		if((sbus_channel[6]<1400)) //如果停车或者推拉杆升起，均停止工作
		{
		temp_send=0x000000;	
		}
		else
			temp_send=0x000001;	//正常运行   0x 0E 06 00 00 00 01 11 11
				
				ByteSend2[3] = (temp_send>>16) & 0xFF;
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;	
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;		
				
				for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
			delay_ms(30);
				/////////////////车速	        0x 0E 06 00 01 88 88 11 11			
			temp_send=0x0E060001;	
			    ByteSend2[0] = (temp_send>>24) & 0xFF;
				ByteSend2[1] = (temp_send>>16) & 0xFF;
				ByteSend2[2] = (temp_send>>8) & 0xFF;
				ByteSend2[3] = temp_send & 0xFF;		
			
				temp_send=(int) ((control_flag[4]+0.1)*100);
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;
			//delay_ms(20);
			for(i=0;i<8;i++)
				{
				UART4_Put_Char(ByteSend2[i]);
				}	
			//	delay_ms(10);

//				
//			delay_ms(10);
				
			}	


			if(adress==20||(sbus_channel[6]<1400)) //撒肥杨家威
			{
				temp_send=0x14060001;	
				ByteSend2[0] = (temp_send>>24) & 0xFF;
				ByteSend2[1] = (temp_send>>16) & 0xFF;
				ByteSend2[2] = (temp_send>>8) & 0xFF;
				ByteSend2[3] = temp_send & 0xFF;		
			
				temp_send=(int) ((control_flag[4])*100);
				ByteSend2[4] = (temp_send>>8) & 0xFF;
				ByteSend2[5] = temp_send & 0xFF;
				
				temp_send=	Crc16withTable( &ByteSend2[0],6);
				ByteSend2[6] = (temp_send>>8) & 0xFF;
				ByteSend2[7] = temp_send & 0xFF;
	
			for(i=0;i<8;i++)
				{			
				UART4_Put_Char(ByteSend2[i]);
					
				}

			}				
						
}

void  safei_work_send_control(void)
{
	static int k;
	
	if(k%2==0)
	{	work_send_control(11);		
		delay_ms(25);
		work_send_control(12);
		
	}
	
	else
	{
		work_send_control(13);		
		delay_ms(25);
		work_send_control(14);	
		
	}
	k++;


}

void TIM7_Init(void)
{
	

TIM_TimeBaseInitTypeDef TIM_TimeBaseInitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;

	RCC_APB1PeriphClockCmd(RCC_APB1Periph_TIM7,ENABLE);
	
	TIM_TimeBaseInitStructure.TIM_Period=1000;   //5000-1,8400-1  定时500ms一次
	TIM_TimeBaseInitStructure.TIM_Prescaler=84-1;  
	TIM_TimeBaseInitStructure.TIM_CounterMode=TIM_CounterMode_Up;
	TIM_TimeBaseInitStructure.TIM_ClockDivision=TIM_CKD_DIV1;
	
	TIM_TimeBaseInit(TIM7,&TIM_TimeBaseInitStructure);


	TIM_ITConfig(TIM7,TIM_IT_Update,ENABLE);
	TIM_Cmd(TIM7,ENABLE);
	//TIM_Cmd(TIM7,DISABLE);
	
	NVIC_InitStructure.NVIC_IRQChannel=TIM7_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelCmd=ENABLE;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=1;
	NVIC_InitStructure.NVIC_IRQChannelSubPriority=1;
	
	NVIC_Init(&NVIC_InitStructure);
	
}

int delay_usr=0;

void TIM7_IRQHandler(void)
{
		UartRxMonitor(1); ////串口接收监控

		//UartRxMonitor4(1); ////串口接收监控
	
		delay_usr++;  //  定时500ms一次
	
	  if (delay_usr>209866)  //是防止一直有障碍物时候计数溢出
			delay_usr=10000;
//		led2=!led2;       //指示灯 
	//delay_ms(100);
	    TIM_ClearITPendingBit(TIM7,TIM_IT_Update);	//更新中断
}



