#include "sys.h"
#include "uart3.h"	
#include "delay.h"
#include "CRC2.h"

u8 USART3_RX_BUF[64];                   //接收缓冲，最大64字节
u8 USART3_RX_CNT=0;                       //接收字节计数器
u8 flagFrame=0;                         //帧接收完成标志，即接收到一帧新数据
unsigned char regGroup[16]={0};  //Modbus寄存器组，地址为0x00~0x015

//  0停车或运行 1速度方向（0前进，1后退）	2 3 速度乘1000  4 角度方向（0左，1右）	4	5 角度乘1000	 6X小数低位	7Y整数高位	 8Y整数低位	9Y小数高位 	10Y小数低位 11预留	12预留	13预留	14预留	15预留




void uart3_init(u32 bound)
	{
   //GPIO端口设置
  GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB,ENABLE); //使能GPIOA时钟

	

	RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART3,ENABLE);//使能USART2时钟

 
	//串口1对应引脚复用映射

	GPIO_PinAFConfig(GPIOB,GPIO_PinSource10,GPIO_AF_USART3); //GPIOA2复用为USART2
	GPIO_PinAFConfig(GPIOB,GPIO_PinSource11,GPIO_AF_USART3); //GPIOA3复用为USART2

	//USART1端口配置
  GPIO_InitStructure.GPIO_Pin =GPIO_Pin_10|GPIO_Pin_11; //GPIOA9与GPIOA10
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;	//速度50MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP; //上拉
	GPIO_Init(GPIOB,&GPIO_InitStructure); //初始化PA9，PA10
	
	

   //USART1 初始化设置
	USART_InitStructure.USART_BaudRate = bound;//波特率设置
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;//字长为8位数据格式
	USART_InitStructure.USART_StopBits = USART_StopBits_1;//一个停止位
	USART_InitStructure.USART_Parity = USART_Parity_No;//无奇偶校验位
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//无硬件数据流控制
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;	//收发模式

  USART_Init(USART3, &USART_InitStructure); //初始化串口2


  USART_Cmd(USART3, ENABLE);  //使能串口2

	
	//USART_ClearFlag(USART1, USART_FLAG_TC);
	

	USART_ITConfig(USART3, USART_IT_RXNE, ENABLE);//开启相关中断


	NVIC_InitStructure.NVIC_IRQChannel = USART3_IRQn;//串口1中断通道
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=0;//抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority =1;		//子优先级3
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			//IRQ通道使能
	NVIC_Init(&NVIC_InitStructure);	//根据指定的参数初始化VIC寄存器、
}


void USART3_IRQHandler(void)                	//串口3中断服务程序
{

	u8 res;	                                    //定义数据缓存变量
	//	printf("11！\r\n");	
	if(USART_GetITStatus(USART3, USART_IT_RXNE) != RESET)//接收到数据
	{
	//printf("22！\r\n");	
	 	
		res =USART_ReceiveData(USART3);//;读取接收到的数据USART2->DR
		if(USART3_RX_CNT<sizeof(USART3_RX_BUF))    //一次只能接收64个字节，人为设定，可以更大，但浪费时间
		{
			USART3_RX_BUF[USART3_RX_CNT]=res;  //记录接收到的值
			USART3_RX_CNT++;        //使收数据增加1 
		}
	}

}


void UART3_Put_Char(unsigned char DataToSend)
{
  while(USART_GetFlagStatus(USART3,USART_FLAG_TC)==RESET);//循环发送,直到发送完毕   
			USART_SendData(USART3,DataToSend); 
}



//计算发送的数据长度，并且将数据放到*buf数组中                     
u8 UartRead(u8 *buf, u8 len)  
{
	 u8 i;
	if(len>USART3_RX_CNT)  //指定读取长度大于实际接收到的数据长度时
	{
		len=USART3_RX_CNT; //读取长度设置为实际接收到的数据长度
	}
	for(i=0;i<len;i++)  //拷贝接收到的数据到接收指针中
	{
		*buf=USART3_RX_BUF[i];  //将数据复制到buf中
		buf++;
	}
	USART3_RX_CNT=0;              //接收计数器清零
	return len;                   //返回实际读取长度
}


u8 rs485_UartWrite(u8 *buf ,u8 len) 										//发送
{
	u8 i=0; 
   delay_ms(3);                                                               //3MS延时
    for(i=0;i<=len-1;i++)
    {
	USART_SendData(USART3,buf[i]);	                                      //通过USARTx外设发送单个数据
	while(USART_GetFlagStatus(USART3,USART_FLAG_TXE)==RESET);             //检查指定的USART标志位设置与否，发送数据空位标志
    }


}


//串口驱动函数，检测数据帧的接收，调度功能函数，需在主循环中调用
void UartDriver()
{
	unsigned char i=0,cnt;
	unsigned int crc;
	unsigned char crch,crcl;
	static u8 len,num; //num位寄存器的数量
	static u8 buf[60];
	if(flagFrame)            //帧接收完成标志，即接收到一帧新数据
	{
		
		
		flagFrame=0;           //帧接收完成标志清零
		len = UartRead(buf,sizeof(buf));   //将接收到的命令读到缓冲区中
		if(buf[0]==0x01)                   //判断地址是不是0x01
		{
			
			
			crc=Crc16withTable(buf,len-2);       //计算CRC校验值，出去CRC校验值temp_send=	Crc16withTable( &ByteSend2[0],11);
			crch=crc>>8;    				//crc高位
			crcl=crc&0xFF;					//crc低位
			if((buf[len-2]==crch)&&(buf[len-1]==crcl))  //判断CRC校验是否正确
			{
				
				//printf(" 2222222222222222222222222！\r\n");	
				
				switch (buf[1])  //按功能码执行操作
				{
					case 0x03:     //读数据
						if((buf[2]==0x00)&&(buf[3]<=0x0F))  //寄存器地址支持0x0000~0x0005
						{
							
							if(buf[3]<=0x0F) 
							{
								i=buf[3];//提取寄存器地址
								cnt=buf[5];  //提取待读取的寄存器数量
								buf[2]=cnt*2;  //读取数据的字节数，为寄存器*2，因modbus定义的寄存器为16位
								len=3;							
								while(cnt--)
								{
									buf[len++]=0x00;				//寄存器高字节补0
									buf[len++]=regGroup[i++];		//低字节
							}
							
						}
							break;
					}
						else  //寄存器地址不被支持时，返回错误码
						{   
							buf[1]=0x83;  //功能码最高位置1
							buf[2]=0x02;  //设置异常码为02-无效地址
							len=3;
							break;
						}
					case 0x10:           //写入多个寄存器
						if((buf[2]==0x00)&&(buf[3]<=0x0F))   //寄存器地址支持0x0000-0x000F
						{
							if(buf[3]<=0x0F)
							{
								i=buf[3];				//提取寄存器地址
								num=buf[4]<<8+buf[5];
								
							
								{
								regGroup[1]=buf[7];		//速度方向
								regGroup[2]=buf[8];		//速度高位
								regGroup[3]=buf[9];		//速度低位	
								
								regGroup[4]=buf[10];		//角度方向
								regGroup[5]=buf[11];		//角度高位
								regGroup[6]=buf[12];		//角度低位	
								}
								
							
							}
							len -=2;                 //长度-2以重新计算CRC并返回原帧
							break;
						}
						else  
						{							//寄存器地址不被支持，返回错误码
							buf[1]=0x86;           //功能码最高位置1
							buf[2]=0x02;           //设置异常码为02-无效地址
							len=3;
							break;
					   }	
					case 0x06:           //写入单个寄存器
						if((buf[2]==0x00)&&(buf[3]<=0x0F))   //寄存器地址支持0x0000-0x0005
						{
							if(buf[3]<=0x0F)
							{
								i=buf[3];				//提取寄存器地址
								regGroup[i]=buf[5];		//保存寄存器数据
							
							}
							len -=2;                 //长度-2以重新计算CRC并返回原帧
							break;
						}
						else  
						{							//寄存器地址不被支持，返回错误码
							buf[1]=0x86;           //功能码最高位置1
							buf[2]=0x02;           //设置异常码为02-无效地址
							len=3;
							break;
					}
					default:    //其他不支持的功能码
						    buf[1]=0x80;     //功能码最高位置1
							buf[2]=0x01;     //设置异常码为01—无效功能
							len=3;
							break;
				}
			    crc=Crc16withTable(buf,len);           //计算CRC校验值
				buf[len++]=crc>>8;           //CRC高字节
				buf[len++]=crc&0xff;        //CRC低字节
				rs485_UartWrite(buf,len);  //发送响应帧
			}
		}
	}
}


				
void UartRxMonitor(u8 ms) //串口接收监控
{
	static u8 USART3_RX_BKP=0;  //定义USART2_RC_BKP暂时存储诗句长度与实际长度比较
	static u8 idletmr=0;        //定义监控时间
	
		//	printf("11！\r\n");	
	if(USART3_RX_CNT>0)//接收计数器大于零时，监控总线空闲时间
	{
		if(USART3_RX_BKP!=USART3_RX_CNT) //接收计数器改变，即刚接收到数据时，清零空闲计时
		{
			USART3_RX_BKP=USART3_RX_CNT;  //赋值操作，将实际长度给USART2_RX_BKP
			idletmr=0;                    //将监控时间清零
		}
		else                              ////接收计数器未改变，即总线空闲时，累计空闲时间
		{
			//如果在一帧数据完成之前有超过3.5个字节时间的停顿，接收设备将刷新当前的消息并假定下一个字节是一个新的数据帧的开始
			if(idletmr<5)                  //空闲时间小于1ms时，持续累加
			{
				idletmr +=ms;
				if(idletmr>=5)             //空闲时间达到1ms时，即判定为1帧接收完毕
				{
					flagFrame=1;//设置命令到达标志，帧接收完毕标志
					UartDriver();
				}
			}
		}
	}
	else
	{
		USART3_RX_BKP=0;
	}
}
							
						






