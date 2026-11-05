#include "sys.h"
#include "uart2.h"	
#include "delay.h"
#include "CRC2.h"
#include "path_plan.h"
#include "adc.h"


extern double control_flag[6];//0行驶还是停车，1前进还是后退，2转向方式，3角度值，4速度值，5作业机构是否起降
extern double AD_angle[4];//四个轮子的采集值  0左前，1右前，2左后，3右后

extern int ultrasonic_1,ultrasonic_2,ultrasonic_3,ultrasonic_4; //四路超声波的数值
u8 RS485_RX_BUF[32];  	//接收缓冲,最大64个字节.
//接收到的数据长度
u8 RS485_RX_CNT=0;   
double Encoder_Data = 0;


void USART2_IRQHandler(void)
{
	unsigned short int CRC_7;
	u8 res;	    
	if(USART_GetITStatus(USART2, USART_IT_RXNE) != RESET)//接收到数据
	{	 	
	  res =USART_ReceiveData(USART2);//;读取接收到的数据USART2->DR   接收到一个字节
		if(RS485_RX_CNT<32)
		{
			 RS485_RX_BUF[RS485_RX_CNT]=res;
			//		printf(" %d",RS485_RX_BUF[RS485_RX_CNT]);
			 RS485_RX_CNT++;

		}

	}  											 
} 


//////发送与接受数据
void read_encoder(u8 address)
{
	  char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;
	
	
		temp_send=address;  //1号电机
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x030000;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0001;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		


	  RS485_Send_Data(ByteSend2,8);//发送5个字节

		delay_ms(15);		//等待10ms,连续超过10ms没有接收到一个数据,则认为接收结束
		if(RS485_RX_CNT>0)//接收到了数据,且接收完成了
		{
		    temp_send=Crc16withTable(&RS485_RX_BUF[0],5); //计算出校验码
			if ((((temp_send>>8) & 0xFF)==RS485_RX_BUF[5])&&((temp_send & 0xFF)==RS485_RX_BUF[6]))		
			
			{				
					if(RS485_RX_BUF[0]==address)//判断编码器ID是否正确
					{
						//得到编码器位置数据
						Encoder_Data = ((RS485_RX_BUF[3]<<8)+(RS485_RX_BUF[4]))/4096.0*360.0/180.0*3.1415926;
						RS485_RX_CNT=0;		//清零				
						//printf("%d  %d \r\n ",address,Encoder_Data);
					if (address==0)
					{
					AD_angle[0]=Encoder_Data;
					}
					
					if (address==1)
					{
					AD_angle[1]=Encoder_Data;
					}
					if (address==2)
					{
					AD_angle[2]=Encoder_Data;
					}
					if (address==3)
					{
					AD_angle[3]=Encoder_Data;
					}
					
					
					}
		  }
			
		}

}

// 该函数未被调用
void read_ultrasonic_1(u8 address)  //读取超声波1
{
	  char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;
	
		//读取探头1测量值
	
		temp_send=address;  //超声波地址  01 03 01 06 00 01 65 F7
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x030106;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0001;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		
//					for(i=1;i<12;i++)
//						{
//						RS485_RX_BUF[i]=0;
//						
//						}

	  RS485_Send_Data(ByteSend2,8);//发送8个字节

		delay_ms(15);		//等待10ms,连续超过10ms没有接收到一个数据,则认为接收结束
	//	printf("号 %d %d  %d  %d  %d  %d  %d  %d\r\n",RS485_RX_CNT,RS485_RX_BUF[0],RS485_RX_BUF[1],RS485_RX_BUF[2],RS485_RX_BUF[3],RS485_RX_BUF[4],RS485_RX_BUF[5],RS485_RX_BUF[6]);
	//	if(RS485_RX_CNT>0)//接收到了数据,且接收完成了
		{
		    
	printf("数1据 %d  %d  %d  %d  %d  %d  %d  %d  %d  %d  %d\r\n",RS485_RX_BUF[0],RS485_RX_BUF[1],RS485_RX_BUF[2],RS485_RX_BUF[3],RS485_RX_BUF[4],RS485_RX_BUF[5],RS485_RX_BUF[6],RS485_RX_BUF[7],RS485_RX_BUF[8],RS485_RX_BUF[9],RS485_RX_BUF[10]);
			
			temp_send=Crc16withTable(&RS485_RX_BUF[0],5); //计算出校验码
			if ((((temp_send>>8) & 0xFF)==RS485_RX_BUF[5])&&((temp_send & 0xFF)==RS485_RX_BUF[6]))		
			
			{				
					if(RS485_RX_BUF[0]==address)//判断编码器ID是否正确
					{
						//得到探头1数据
						ultrasonic_1 = ((RS485_RX_BUF[3]<<8)+(RS485_RX_BUF[4]));
						RS485_RX_CNT=0;		//清零					
					

					
					}
		  }
			
		}
		
		//delay_ms(10);	
		
		
		

}






// 该函数未被调用
void read_ultrasonic_234(u8 address)  //读取超声波234
{
	  char ByteSend2[8]={0};//绝对位置设置的字节
	int i=0;
		uint32_t  temp_send;
				//读取探头234测量值
	
		temp_send=address;  //超声波地址  ：01 03 01 07 00 03 B5 F6
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x030107;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0003;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		

	  RS485_Send_Data(ByteSend2,8);//发送8个字节

		delay_ms(15);		//等待10ms,连续超过10ms没有接收到一个数据,则认为接收结束
//		if(RS485_RX_CNT>0)//接收到了数据,且接收完成了
		{
			
	printf("数234据 %d  %d  %d  %d  %d  %d  %d  %d %d  %d %d\r\n",RS485_RX_BUF[0],RS485_RX_BUF[1],RS485_RX_BUF[2],RS485_RX_BUF[3],RS485_RX_BUF[4],RS485_RX_BUF[5],RS485_RX_BUF[6],RS485_RX_BUF[7],RS485_RX_BUF[8],RS485_RX_BUF[9],RS485_RX_BUF[10]);
		    temp_send=Crc16withTable(&RS485_RX_BUF[0],9); //计算出校验码
			if ((((temp_send>>8) & 0xFF)==RS485_RX_BUF[9])&&((temp_send & 0xFF)==RS485_RX_BUF[10]))		
			
			{				
					if(RS485_RX_BUF[0]==address)//判断编码器ID是否正确
					{
						//得到探头2数据
						ultrasonic_2 = ((RS485_RX_BUF[3]<<8)+(RS485_RX_BUF[4]));
						//得到探头3数据
						ultrasonic_3 = ((RS485_RX_BUF[5]<<8)+(RS485_RX_BUF[6]));
						//得到探头4数据
						ultrasonic_4 = ((RS485_RX_BUF[7]<<8)+(RS485_RX_BUF[8]));
						
						RS485_RX_CNT=0;		//清零					
					}
		  }
			
		}
		

}


// 该函数未被调用
void read_ultrasonic_1234(u8 address)  //读取超声波234
{
char ByteSend2[8]={0};//绝对位置设置的字节
		int i=0;
		uint32_t  temp_send;
	
		//读取探头1测量值
	
		temp_send=address;  //超声波地址  01 03 01 06 00 01 65 F7
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x030106;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0001;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		


	  RS485_Send_Data(ByteSend2,8);//发送8个字节

		delay_ms(20);		//等待10ms,连续超过10ms没有接收到一个数据,则认为接收结束

  //  printf("数1据 %d  %d  %d  %d  %d  %d  %d\r\n",RS485_RX_BUF[0],RS485_RX_BUF[1],RS485_RX_BUF[2],RS485_RX_BUF[3],RS485_RX_BUF[4],RS485_RX_BUF[5],RS485_RX_BUF[6]);
			temp_send=Crc16withTable(&RS485_RX_BUF[0],5); //计算出校验码
			if ((((temp_send>>8) & 0xFF)==RS485_RX_BUF[5])&&((temp_send & 0xFF)==RS485_RX_BUF[6]))		
			
			{				
					if(RS485_RX_BUF[0]==address)//判断编码器ID是否正确
					{
						//得到探头1数据
						ultrasonic_1 = ((RS485_RX_BUF[3]<<8)+(RS485_RX_BUF[4]));
						RS485_RX_CNT=0;		//清零					
					

					
					}
		  }

    delay_ms(150);

    temp_send=address;  //超声波地址  ：01 03 01 07 00 03 B5 F6
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x030107;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0003;	

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		


	  RS485_Send_Data(ByteSend2,8);//发送8个字节

		delay_ms(20);		//等待10ms,连续超过10ms没有接收到一个数据,则认为接收结束
	 // printf("数234据 %d  %d  %d  %d  %d  %d  %d  %d %d \r\n",RS485_RX_BUF[0],RS485_RX_BUF[1],RS485_RX_BUF[2],RS485_RX_BUF[3],RS485_RX_BUF[4],RS485_RX_BUF[5],RS485_RX_BUF[6],RS485_RX_BUF[7],RS485_RX_BUF[8]);
		  temp_send=Crc16withTable(&RS485_RX_BUF[0],9); //计算出校验码
			if ((((temp_send>>8) & 0xFF)==RS485_RX_BUF[9])&&((temp_send & 0xFF)==RS485_RX_BUF[10]))		
			
			{				
					if(RS485_RX_BUF[0]==address)//判断编码器ID是否正确
					{
						//得到探头2数据
						ultrasonic_2 = ((RS485_RX_BUF[3]<<8)+(RS485_RX_BUF[4]));
						//得到探头3数据
						ultrasonic_3 = ((RS485_RX_BUF[5]<<8)+(RS485_RX_BUF[6]));
						//得到探头4数据
						ultrasonic_4 = ((RS485_RX_BUF[7]<<8)+(RS485_RX_BUF[8]));
						
						RS485_RX_CNT=0;		//清零					
					}
		  }
    delay_ms(150);

}



//初始化IO 串口2
//bound:波特率	  

// 该函数未被调用
void set_median(u8 address)
{
 char ByteSend2[8]={0};//绝对位置设置的字节  01 06 00 0E 00 01 (29 C9)
		int i=0;
		uint32_t  temp_send;
	
	
		temp_send=address;  //1号电机
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x06000E;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0001;	  ///地址

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		


	  RS485_Send_Data(ByteSend2,8);//发送5个字节

}
void set_adresss()
 {
 char ByteSend2[8]={0};//绝对位置设置的字节  01 06 00 04 00 02 (49 CA)
		int i=0;
		uint32_t  temp_send;
	
	
		temp_send=0x01;  //1号电机
		ByteSend2[0] = temp_send & 0xFF;	
		
		temp_send=0x060004;					
		ByteSend2[1] = (temp_send>>16) & 0xFF;
		ByteSend2[2] = (temp_send>>8) & 0xFF;
		ByteSend2[3] = temp_send & 0xFF;	
		
		temp_send=0x0003;	  ///地址

		ByteSend2[4] = (temp_send>>8) & 0xFF;
		ByteSend2[5] = temp_send & 0xFF;	
		
		temp_send=	Crc16withTable( &ByteSend2[0],6);
		ByteSend2[6] = (temp_send>>8) & 0xFF;
		ByteSend2[7] = temp_send & 0xFF;		
		


	  RS485_Send_Data(ByteSend2,8);//发送5个字节

}


void uart2_init(u32 bound)
{  	 
	
  GPIO_InitTypeDef GPIO_InitStructure;
	USART_InitTypeDef USART_InitStructure;
	NVIC_InitTypeDef NVIC_InitStructure;
	
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA,ENABLE); //使能GPIOA时钟
	RCC_APB1PeriphClockCmd(RCC_APB1Periph_USART2,ENABLE);//使能USART2时钟
	
  //串口2引脚复用映射
	GPIO_PinAFConfig(GPIOA,GPIO_PinSource2,GPIO_AF_USART2); //GPIOA2复用为USART2
	GPIO_PinAFConfig(GPIOA,GPIO_PinSource3,GPIO_AF_USART2); //GPIOA3复用为USART2
	
	//USART2    
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_2 | GPIO_Pin_3; //GPIOA2与GPIOA3
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;//复用功能
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽复用输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP; //上拉
	GPIO_Init(GPIOA,&GPIO_InitStructure); //初始化PA2，PA3
	
	//PG8推挽输出，485模式控制  
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_8; //GPIOG8
	GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;//输出
	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//速度100MHz
	GPIO_InitStructure.GPIO_OType = GPIO_OType_PP; //推挽输出
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP; //上拉
	GPIO_Init(GPIOG,&GPIO_InitStructure); //初始化PG8
	

   //USART2 初始化设置
	USART_InitStructure.USART_BaudRate = bound;//波特率设置
	USART_InitStructure.USART_WordLength = USART_WordLength_8b;//字长为8位数据格式
	USART_InitStructure.USART_StopBits = USART_StopBits_1;//一个停止位
	USART_InitStructure.USART_Parity = USART_Parity_No;//无奇偶校验位
	USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;//无硬件数据流控制
	USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;	//收发模式
  USART_Init(USART2, &USART_InitStructure); //初始化串口2
	
  USART_Cmd(USART2, ENABLE);  //使能串口 2
	
	USART_ClearFlag(USART2, USART_FLAG_TC);
	

	USART_ITConfig(USART2, USART_IT_RXNE, ENABLE);//开启接受中断

	//Usart2 NVIC 配置
  NVIC_InitStructure.NVIC_IRQChannel = USART2_IRQn;
	NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority=3;//抢占优先级3
	NVIC_InitStructure.NVIC_IRQChannelSubPriority =3;		//子优先级3
	NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;			//IRQ通道使能
	NVIC_Init(&NVIC_InitStructure);	//根据指定的参数初始化VIC寄存器、


	
//	RS485_TX_EN=0;				//默认为接收模式	
}

//RS485发送len个字节.
//buf:发送区首地址
//len:发送的字节数(为了和本代码的接收匹配,这里建议不要超过64个字节)
void RS485_Send_Data(u8 *buf,u8 len)
{
	u8 t;
	//RS485_TX_EN=1;			//设置为发送模式
  	for(t=0;t<len;t++)		//循环发送数据
	{
	  while(USART_GetFlagStatus(USART2,USART_FLAG_TC)==RESET); //等待发送结束		
    USART_SendData(USART2,buf[t]); //发送数据
	}	 
		while(USART_GetFlagStatus(USART2,USART_FLAG_TC)==RESET); //等待发送结束		
		RS485_RX_CNT=0;	  
	//RS485_TX_EN=0;				//设置为接收模式	
}



void get_angle_encode()
{

			read_encoder(0);
				delay_ms(10);	
		read_encoder(1);
				delay_ms(10);	
			read_encoder(2);
				delay_ms(10);	
			read_encoder(3);
			delay_ms(10);


}

