#include "telecontrol.h"
#include "lcd.h"
#include "sys.h" 



//#include "servo.h"
#include "led.h"
#include "retrofit.h"


u8 rec_sbus_data[SBUS_DATA_LEN];   // 接收数据
int sbus_channel[16];  //////////////////////////////////////数据的代表
u16 flag_sbus;
int sbus_filiter_channel[16];
u8 CHANGE_FLAG = 0;

u8 LOCK_FLAG = 1;
u8 HEIGHT_FIXED_FLAG = 0;
u8 OPTICAL_FLOW_FLAG = 0;

/*********************************************************************
*							初始化串口
**********************************************************************/

void USART1_SBUS_Init(void)
{
	NVIC_InitTypeDef NVIC_InitStructure ;//定义中断结构体
 	GPIO_InitTypeDef GPIO_InitStructure;//定义IO初始化结构体
	USART_InitTypeDef USART_InitStructure;//定义串口结构体
	DMA_InitTypeDef DMA_InitStructure;//定义DMA结构体
	
	//打开串口对应的外设时钟
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_USART1, ENABLE);
	//设置IO口时钟
	RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE);
	GPIO_PinAFConfig(GPIOA,GPIO_PinSource10,GPIO_AF_USART1);


	GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;	//IO口速度
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;	//管脚模式:输入口
	GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_NOPULL;	 //上拉下拉设置
	GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10;    //管脚指定
	GPIO_Init(GPIOA, &GPIO_InitStructure);      //初始化

	//**********************串口 接受 DMA 设置**************************
	// 1 启动DMA时钟
    RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_DMA2, ENABLE);//DMA通道配置
	
	// 2 DMA通道配置
	DMA_DeInit(DMA2_Stream5);
	DMA_InitStructure.DMA_Channel = DMA_Channel_4;
	DMA_InitStructure.DMA_PeripheralBaseAddr = (uint32_t)(&USART1->DR);//外设地址
	DMA_InitStructure.DMA_Memory0BaseAddr = (uint32_t)rec_sbus_data;//内存地址
	DMA_InitStructure.DMA_DIR = DMA_DIR_PeripheralToMemory;//dma传输方向
	DMA_InitStructure.DMA_BufferSize = SBUS_DATA_LEN;//设置DMA在传输时缓冲区的长度
	DMA_InitStructure.DMA_PeripheralInc = DMA_PeripheralInc_Disable;//设置DMA的外设一个外设
	DMA_InitStructure.DMA_MemoryInc = DMA_MemoryInc_Enable;//设置DMA的内存递增模式
	DMA_InitStructure.DMA_PeripheralDataSize = DMA_PeripheralDataSize_Byte;//外设数据字长
	DMA_InitStructure.DMA_MemoryDataSize = DMA_MemoryDataSize_Byte;//内存数据字长
	DMA_InitStructure.DMA_Mode = DMA_Mode_Normal;//设置DMA的传输模式
	DMA_InitStructure.DMA_Priority = DMA_Priority_VeryHigh;//设置DMA的优先级别
	DMA_InitStructure.DMA_Priority = DMA_Priority_Medium;//中等优先级
	DMA_InitStructure.DMA_FIFOMode = DMA_FIFOMode_Disable;         
	DMA_InitStructure.DMA_FIFOThreshold = DMA_FIFOThreshold_Full;
	DMA_InitStructure.DMA_MemoryBurst = DMA_MemoryBurst_Single;//存储器突发单次传输
	DMA_InitStructure.DMA_PeripheralBurst = DMA_PeripheralBurst_Single;//外设突发单次传输
	// 3 配置DMA2的通道
	DMA_Init(DMA2_Stream5, &DMA_InitStructure);
	// 4 使能通道
	DMA_Cmd(DMA2_Stream5,ENABLE);

	/* 5.使能串口的DMA接收 */
	USART_DMACmd(USART1,USART_DMAReq_Rx,ENABLE);


    //初始化串口参数
    USART_InitStructure.USART_WordLength = USART_WordLength_8b;
    USART_InitStructure.USART_StopBits = USART_StopBits_1;
    USART_InitStructure.USART_Parity = USART_Parity_No;
    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    USART_InitStructure.USART_Mode = USART_Mode_Rx;
    USART_InitStructure.USART_BaudRate = 115200;
	
	//初始化串口
    USART_Init(USART1,&USART_InitStructure);

	//配置中断
    NVIC_InitStructure.NVIC_IRQChannel = USART1_IRQn;               //通道设置为串口中断
    NVIC_InitStructure.NVIC_IRQChannelPreemptionPriority = 0;       //中断占先等级
    NVIC_InitStructure.NVIC_IRQChannelSubPriority = 0;              //中断响应优先级
    NVIC_InitStructure.NVIC_IRQChannelCmd = ENABLE;                 //打开中断
    NVIC_Init(&NVIC_InitStructure);

	//中断配置
	USART_ITConfig(USART1,USART_IT_TC,DISABLE);
	USART_ITConfig(USART1,USART_IT_RXNE,DISABLE);
	USART_ITConfig(USART1,USART_IT_TXE,DISABLE);
	USART_ITConfig(USART1,USART_IT_IDLE,ENABLE);
	
	//启动串口
    USART_Cmd(USART1, ENABLE);
}

/*********************************************************************
*							接口函数:发送数据
*参数:BufferSRC:发送数据存放地址
*	  BufferSize:发送数据字节数
**********************************************************************/
void USART1_DMATransfer(uint32_t *BufferSRC, uint32_t BufferSize)//UASRT DMA发送设置
{
	DMA_ClearFlag(DMA2_Stream7,DMA_FLAG_TCIF7);
	DMA2_Stream7->NDTR = BufferSize;    //配置BUFFER大小
	DMA2_Stream7->M0AR = (uint32_t)BufferSRC;   //配置地址
	DMA2_Stream7->CR |= DMA_SxCR_EN;	//打开DMA,开始发送
}



/*********************************************************************
*		串口中断处理函数:接收完成
**********************************************************************/

void USART1_IRQHandler(void)
{
	static uint8_t UART1_Rec_Len = 0;
	int i,t;
	u8 XOR;
	if(USART_GetITStatus(USART1, USART_IT_IDLE) != RESET)  //接收中断
	{
		t= USART_ReceiveData(USART1);//读取数据 注意：这句必须要，否则不能够清除中断标志位。
		UART1_Rec_Len = SBUS_DATA_LEN - DMA2_Stream5->NDTR;	//算出接本帧数据长度

		//***********帧数据处理函数************//		
		DMA_ClearFlag(DMA2_Stream7,DMA_FLAG_TCIF7);
		CHANGE_FLAG = 1;
		retrofit_notify_sbus();	/* RETROFIT: SBUS heartbeat */
		XOR=rec_sbus_data[1];
		for(i=2;i<34;i++)
		{
			XOR=XOR^rec_sbus_data[i];
		}                                                                               
	if(rec_sbus_data[0]==0x0F&&rec_sbus_data[34]==XOR)//
		{
		sbus_channel[0]  = (rec_sbus_data[1]<<8|rec_sbus_data[2])   ;
		sbus_channel[1]  = (rec_sbus_data[3]<<8|rec_sbus_data[4])   ;
		sbus_channel[2]  = (rec_sbus_data[5]<<8|rec_sbus_data[6])   ;
		sbus_channel[3]  = (rec_sbus_data[7]<<8|rec_sbus_data[8])   ;
		sbus_channel[4]  = (rec_sbus_data[9]<<8|rec_sbus_data[10])   ;
		sbus_channel[5]  = (rec_sbus_data[11]<<8|rec_sbus_data[12])   ;
		sbus_channel[6]  = (rec_sbus_data[13]<<8|rec_sbus_data[14])   ;
		sbus_channel[7]  = (rec_sbus_data[15]<<8|rec_sbus_data[16])   ;
		sbus_channel[8]  = (rec_sbus_data[17]<<8|rec_sbus_data[18])   ;
		sbus_channel[9]  = (rec_sbus_data[19]<<8|rec_sbus_data[20])   ;
		sbus_channel[10] = (rec_sbus_data[21]<<8|rec_sbus_data[22])   ;
		sbus_channel[11] = (rec_sbus_data[23]<<8|rec_sbus_data[24])   ;
		sbus_channel[12] = (rec_sbus_data[25]<<8|rec_sbus_data[26])   ;
		sbus_channel[13] = (rec_sbus_data[27]<<8|rec_sbus_data[28])   ;
		sbus_channel[14] = (rec_sbus_data[29]<<8|rec_sbus_data[30])   ;
		sbus_channel[15] = (rec_sbus_data[31]<<8|rec_sbus_data[32])   ;
			
		flag_sbus=	rec_sbus_data[33];
		}
		
		if (flag_sbus >0)//电机锁上锁（默认上锁）		
			LOCK_FLAG = 0;
		else
			LOCK_FLAG = 1;
//		
//		if (sbus_channel[4] <500)//定高模式（默认不定高）
//			HEIGHT_FIXED_FLAG = 0;
//		else
//			HEIGHT_FIXED_FLAG = 1;
//		
//		if ((sbus_channel[5] > 1024)&&(HEIGHT_FIXED_FLAG))//光流模式（默认不开光流）
//			OPTICAL_FLOW_FLAG = 1;
//		else
//			OPTICAL_FLOW_FLAG = 0;
		
		CHANGE_FLAG = 0;
		
		//*************************************//
		DMA2_S5_Reset();                                       //恢复DMA指针，等待下一次的接收
		USART_ClearITPendingBit(USART1, USART_IT_IDLE);         //清除中断标志

    }
	else if(USART_GetITStatus(USART1, USART_IT_TC) != RESET)
	{
		USART_ClearITPendingBit(USART1, USART_IT_TC);

		DMA2_Stream7->CR &= (uint32_t)(~DMA_SxCR_EN);   //关闭DMA,发送完成
	}
}

void DMA2_Stream7_IRQHandler(void)
{
    if(DMA_GetITStatus(DMA2_Stream7,DMA_IT_TCIF7) != RESET)
    {
        /* 清除标志位 */
        DMA_ClearFlag(DMA2_Stream7,DMA_IT_TCIF7);
        /* 关闭DMA */
        DMA_Cmd(DMA2_Stream7,DISABLE);
        /* 打开发送完成中断,确保最后一个字节发送成功 */
        USART_ITConfig(USART1,USART_IT_TC,ENABLE);
    }
}


void DMA2_S5_Reset(void)//DMA2_Stream6 接收重置
{ 
	DMA_ClearFlag(DMA2_Stream5,DMA_IT_TCIF5|DMA_FLAG_HTIF5|DMA_FLAG_TEIF5|DMA_FLAG_DMEIF5|DMA_FLAG_FEIF5);  
	
	DMA_Cmd(DMA2_Stream5,DISABLE); //关闭USART1 TX DMA1 所指示的通道

 	//DMA_SetCurrDataCounter(DMA1_Channel5,Uart1_DMA_Len);//DMA通道的DMA缓存的大小
	DMA2_Stream5->NDTR = SBUS_DATA_LEN;
 	//DMA_Cmd(DMA1_Channel5, ENABLE);                    
	DMA_Cmd(DMA2_Stream5,ENABLE); //使能USART1 TX DMA1 所指示的通道
	/* 清除标志位 */
   
}

void sbus_filter(u8 count_filiter)
{		
//10ms来一次数据
	u8 i;
	u8 j;
	
	for(i=0;i<count_filiter;i++)
		{
					for(j=0;j<16;j++)
				{
					sbus_filiter_channel[j]=sbus_channel[j]+sbus_filiter_channel[j];
				}
		}
	
	for(j=0;j<16;j++)
		{
			sbus_filiter_channel[j]=sbus_filiter_channel[j]/count_filiter;
		}

}



