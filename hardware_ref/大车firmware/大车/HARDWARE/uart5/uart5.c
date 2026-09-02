#include "sys.h"
#include "uart2.h"	
#include "uart5.h"	
#include "delay.h"
#include "CRC2.h"
#include "path_plan.h"

u8 USART_RX_BUF2[100];     //接收缓冲,最大USART_REC_LEN个字节.
extern double veloc_limit ;

double Upper_computer_date[4]={2,2,1.5,1}; //0 表示行驶模式；1表示作业模式；2最大速度；3停车
extern u8 Obstacle_avoidance_flag,flag_Steering_mode;
//调整轴距标志位
extern u8 Adjusting_wheelbase; 
void uart5_init(u32 bound)
	{
   //GPIO端口设置
  GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOC,ENABLE); //使能GPIOA时钟
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOD,ENABLE); //使能GPIOA时钟		
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_UART5,ENABLE);//使能USART2时钟

	//串口5对应引脚复用映射

	GPIO_PinAFConfig(GPIOC,GPIO_PinSource12,GPIO_AF_UART5); //GPIOA2复用为USART2
	GPIO_PinAFConfig(GPIOD,GPIO_PinSource2,GPIO_AF_UART5); //GPIOA3复用为USART2

	//USART5端口配置
  GPIO_InitStructure.GPIO_Pin =GPIO_Pin_12; //GPIOA9与GPIOA10
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;	//速度50MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP; //上拉
	GPIO_Init(GPIOC,&GPIO_InitStructure); //初始化PA9，PA10
	
	GPIO_InitStructure.GPIO_Pin =GPIO_Pin_2; //GPIOA9与GPIOA10
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;	//速度50MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP; //上拉
	GPIO_Init(GPIOD,&GPIO_InitStructure); //初始化PA9，PA10
	
	
	

   //USART5 初始化设置
	USART_InitStructure.USART_BaudRate = bound;//波特率设置
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;//字长为8位数据格式
	USART_InitStructure.USART_StopBits = USART_StopBits_1;//一个停止位
	USART_InitStructure.USART_Parity = USART_Parity_No;//无奇偶校验位
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//无硬件数据流控制
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;	//收发模式

  USART_Init(UART5, &USART_InitStructure); //初始化串口5


  USART_Cmd(UART5, ENABLE);  //使能串口5

	USART_ITConfig(UART5, USART_IT_RXNE, ENABLE);//开启相关中断


	NVIC_InitStructure.NVIC_IRQChannel = UART5_IRQn;//串口5中断通道
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=0;//抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority =1;		//子优先级3
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			//IRQ通道使能
	NVIC_Init(&NVIC_InitStructure);	//根据指定的参数初始化VIC寄存器、
}



u8 state=0;//接收状态
u8 uart_byte_count=0;        //接收到的数据长度

u8 recive_flag=0;


//u8 Usartsendflag;

//  定义的数组  伸缩调整 FF 01 02 03 03 05 06 07 08 FE  
// FF 01 00 FE伸缩调整（0不调。1打开，2收回） FF 02 00 FE 避障（0 不避障 1避障） FF 03 00 FE 一键调整编码器   FF 04 00 FE 转向方式  FF 04 00 FE 速度选择



void UART5_IRQHandler(void)                	//串口5中断服务程序
{u8 Res;
	static int RecState=0;    //静态整型变量用来解析帧头
	static int JiaQianState=0;
	static int JiannQianState=0; 
	
	if(USART_GetITStatus(UART5, USART_IT_RXNE) != RESET)  //接收中断(接收到的数据必须是0x0d 0x0a结尾)
	{
		Res =USART_ReceiveData(UART5);//(USART1->DR);	//读取接收到的数据

		}
USART_ClearFlag(UART5,USART_IT_RXNE);	
		
		if(state==0&&Res==0xFF)//开启接收
			{
					state=1;
					uart_byte_count=0x00; 		
			}
		
			if(state==1)//一位位接收数据并装入缓存
			{
					USART_RX_BUF2[uart_byte_count]=Res;
					uart_byte_count++;
					if(Res==0xFE)//停止字符
						state=2;
			}
		
		if(state==2)//接收完成
			{
					state=0;
					//解析代码
       printf("数据 %d %d %d %d\r\n",USART_RX_BUF2[0],USART_RX_BUF2[1],USART_RX_BUF2[2],USART_RX_BUF2[3]);

					//////////////////////////////	伸缩调整	
						if (USART_RX_BUF2[1]==1)	 //说明是伸缩调整
						{
							
									if(USART_RX_BUF2[2]==1) //说明要收回
									{
											PAout(11)=0;

											PDout(3)=0;
										Adjusting_wheelbase=1; 
										
									//	printf("收回 \r\n");
										
									
									}
									if(USART_RX_BUF2[2]==2) //说明要张开
									{
											PAout(11)=1;

											PDout(3)=1;
											Adjusting_wheelbase=1;
										
								//		printf("打开 \r\n");
									}
									if(USART_RX_BUF2[2]==0)
									{
										  PAout(11)=1;

											PDout(3)=0;
											Adjusting_wheelbase=0;
								//		printf("不动 \r\n");
									}

						}
         //////////////////////////////	是否避障
						if (USART_RX_BUF2[1]==2)	 //说明是否避障
						{
									if(USART_RX_BUF2[2]==0) //关闭避障
									{
										Obstacle_avoidance_flag=0; 
									}
									if(USART_RX_BUF2[2]==1)         //打开避障
									{
									Obstacle_avoidance_flag=1; 
									}
							
						}
					 //////////////////////////////	转向方式选择
						if (USART_RX_BUF2[1]==4)	 //说明是	转向方式选择
						{
									if(USART_RX_BUF2[2]==0) //绝对值转向
									{
										flag_Steering_mode=0;
									}
									if(USART_RX_BUF2[2]==1)        //增量转向
									{

										flag_Steering_mode=1;
									}
							
						}


					 //////////////////////////////	速度模式选择
						if (USART_RX_BUF2[1]==4)	 //说明是	速度模式选择
						{
									if(USART_RX_BUF2[2]==0) //低速
									{
										 PCout(3)=0;
										PCout(4)=1;
									}
									
									if(USART_RX_BUF2[2]==2) //高速
									{
										 PCout(3)=1;
											PCout(4)=0; //
									}
									if(USART_RX_BUF2[2]==1)        //中速
									{

											PCout(3)=1;
											PCout(4)=1; //
									}
							
						}	
						
	
			}

		 		 
  } 



void UART5_Put_Char(u16 DataToSend)
{
  while(USART_GetFlagStatus(UART5,USART_FLAG_TC)==RESET);//循环发送,直到发送完毕   
			USART_SendData(UART5,DataToSend); 
}

//send_Operation_parameters(1.2,48,3,5);
void send_Operation_parameters(double speed,double voltage,double electric_current,double mileage)
{
		u8 temp_speed,temp_voltage,temp_electric_current,temp_mileage;
	
		UART5_Put_Char(0xFC);
///速度 
		temp_speed=speed;
	temp_speed = temp_speed & 0xFF;	
		UART5_Put_Char(temp_speed);
		temp_speed=(speed-temp_speed)*100;
				if(temp_speed>0xFB)
				temp_speed=0xFB;
			temp_speed = temp_speed & 0xFF;	
		UART5_Put_Char(temp_speed);
				
///电压 
		temp_voltage=voltage;
			temp_voltage = temp_voltage & 0xFF;			
		UART5_Put_Char(temp_voltage);
			
		temp_voltage=(voltage-temp_voltage)*100;
				if(temp_speed>0xFB)
				temp_voltage=0xFB;
		temp_voltage = temp_voltage & 0xFF;			
		UART5_Put_Char(temp_voltage);
					
///电流 
		temp_electric_current=electric_current;
		temp_electric_current = temp_electric_current & 0xFF;	
				
		UART5_Put_Char(temp_electric_current);
		temp_electric_current=(electric_current-temp_electric_current)*100;
				if(temp_electric_current>0xFB)
				temp_electric_current=0xFB;
					temp_electric_current = temp_electric_current & 0xFF;			
		UART5_Put_Char(temp_electric_current);
	
///里程 
		temp_mileage=mileage;
		UART5_Put_Char(temp_mileage);
		temp_mileage=(mileage-temp_mileage)*100;
				if(temp_mileage>0xFB)
				temp_mileage=0xFB;
		UART5_Put_Char(temp_mileage);
		UART5_Put_Char(0);

UART5_Put_Char(0xFD);


}

//字符串发送函数
void HMISends(char *buf1)		  
{
	u8 i=0;
	while(1)
	{
		if(buf1[i] != 0)
	 	{
			USART_SendData(UART5,buf1[i]);  //发送一个字节
			while(USART_GetFlagStatus(UART5,USART_FLAG_TXE)==RESET){};//等待发送结束
		 	i++;
		}
		else
		{
			return ;
		}
	}
}







