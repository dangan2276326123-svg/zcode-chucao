#include "iic.h"
#include "delay.h"
#include "usart.h"

//初始化IIC  //这实际上是用来与测量四轮转角 角度传感器角度AD电压值的ADS1115模块使用的IIC通信设置  
//函数名的中的2是按照例程改的 可以等熟悉之后 自己再改成自己独特的函数名
 
double battery_voltage,stop_voltage,base_voltage,control_voltage;   //定义电池电压 刹车电压 基准电压 遥控器电压
 
double volt0,volt1,volt2,volt3;                                      //第一个ADC1115模块采集到的车轮角度电压值
double check_current0,check_current1,check_current2,check_current3;  //第二个ADC1115模块采集到的检测值 后两个目前是空闲
extern double angle[4];                                              //每个车轮的转角
extern double AD_angle[4];//四个轮子的采集值  0左前，1右前，2左后，3右后
	extern u8 LOCK_FLAG; //遥控器锁	
void IIC_1_Init(void)
{                       
  GPIO_InitTypeDef  GPIO_InitStructure;

  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB, ENABLE);

   
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_8 | GPIO_Pin_9;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;
  GPIO_Init(GPIOB, &GPIO_InitStructure);
        IIC_1_SCL=1;
        IIC_1_SDA=1;
}
//产生IIC起始信号
void IIC_1_Start(void)
{
        IIC_1_SDA_OUT();      
        IIC_1_SDA=1;     //数据的有效性：传输数据是 SDA上的数据必须得在SCL高电平到来之前就得准备好！所以 SDA先拉高下一行SCL再拉高               
        IIC_1_SCL=1;
        delay_us(4);
        IIC_1_SDA=0;  
        delay_us(4); //在SCL为高电平期间 将SDA由高拉到低
        IIC_1_SCL=0;
}          
//产生IIC停止信号
void IIC_1_Stop(void)
{
        IIC_1_SDA_OUT();
        IIC_1_SCL=0;
        IIC_1_SDA=0;
        delay_us(4);
        IIC_1_SCL=1;
        IIC_1_SDA=1;
        delay_us(4);                                                                  
}
//等待应答信号到来
//返回值：1，接收应答失败
//        0，接收应答成功 //0为成功是因为低电平有效
u8 IIC_1_Wait_Ack(void)
{
        u8 ucErrTime=0;
        IIC_1_SDA_IN();  //主机的把信号线设置为输入，等到接收器反馈过来的信号 所以我们把数据线设置为输入    
        IIC_1_SDA=1;delay_us(1);          
        IIC_1_SCL=1;delay_us(1);         
        while(IIC_1_READ_SDA)
        {
                ucErrTime++;
                if(ucErrTime>250)
                {
                        IIC_1_Stop();
                        return 1;
                }
        }
        IIC_1_SCL=0;   
        return 0;  
}
//产生ACK应答
void IIC_1_Ack(void)
{
        IIC_1_SCL=0;
        IIC_1_SDA_OUT();
        IIC_1_SDA=0;//有效应答SDA就是0  低电平为有效应答
        delay_us(2);
        IIC_1_SCL=1;
        delay_us(2);
        IIC_1_SCL=0;
}
//不产生ACK应答                    
void IIC_1_NAck(void)
{
        IIC_1_SCL=0;
        IIC_1_SDA_OUT();
        IIC_1_SDA=1; //有效应答SDA是1  高电平为有效应答
        delay_us(2);
        IIC_1_SCL=1;
        delay_us(2);
        IIC_1_SCL=0;
}                                                                              
//IIC发送一个字节
//返回从机有无应答
//1，有应答
//0，无应答                          
void IIC_1_Send_Byte(u8 txd)
{                        
    u8 t;   
         IIC_1_SDA_OUT();             
   IIC_1_SCL=0; //发送数据肯定先把SCL拉低钳住，先趁此时SCL低电平期间先把SDA给确认了准备好
    for(t=0;t<8;t++)
    {              
        IIC_1_SDA=(txd&0x80)>>7; //哈哈 没错，趁着SCL前面被搞成低电平，被恢复成高电平之前先把SDA给确定了  一共八个位的数据，那就先从最左边开始处理呗
        txd<<=1;          //准备一下次高位  第二轮就是这个了 
                delay_us(2);   
                IIC_1_SCL=1;
                delay_us(2);
                IIC_1_SCL=0;    //一轮又一轮 一共0-7 八轮  都是如此   
                delay_us(2);
    }         
}             
//读1个字节，ack=1时，发送ACK，ack=0，发送nACK   
u8 IIC_1_Read_Byte(unsigned char ack)
{
        unsigned char i,receive=0;
        IIC_1_SDA_IN();//读的话数据线肯定设置为输入啊
    for(i=0;i<8;i++ )
        {
        IIC_1_SCL=0;
        delay_us(2);
                IIC_1_SCL=1;
        receive<<=1;
        if(IIC_1_READ_SDA)receive++;  //这个位的数据是1你才加一，不是1往左移一位就ok 
                delay_us(1);
    }  //ok 8轮的循环完成  数据接收完成                                       
    if (!ack)
        IIC_1_NAck();
    else
        IIC_1_Ack();  
    return receive;
}
/*
        ADS1115
        测试平台是STM32F407VET6
        读取双通道电压，通道1是IN0脚对地电压        ，通道2是IN2脚对地电压
        读取范围为±6.144 V，注意是正负，所以变量不要定义为uint,                               
        base计算方式：6.144*2/65535≈0.00018750，放大100000000倍为18750整数比较好计算
        注意delay_ms(10)不能删除，读取双通道的时候不加这个延迟，会出现读取通道1 却读到的是通道2的值，读通道2又读的是通道1的值
*/
u16 base=18750;                 
int v0,v1,v2,v3;  // 转角AD的原始数据

void ADS_angle_Read(void)                 
{
        short  int sensor0=0;
        short  int sensor1=0;
        short  int sensor2=0;
        short  int sensor3=0;
        u8  data1=0;                       
        u8  data2=0;       
        u8  data3=0;                       
        u8  data4=0;
        u8  data5=0;                       
        u8  data6=0;       
        u8  data7=0;                       
        u8  data8=0;   
//////////////////////////////////////////////////////////////////////////////////开始A0通道的转换

        IIC_1_Start();
        IIC_1_Send_Byte(0X90);//发送写地址给ADS1115(0x90);
        IIC_1_Wait_Ack();   //等待应答
        IIC_1_Send_Byte(0X01);//要配置01地址的寄存器（配置寄存器）向地址指针寄存器写数据，后两位有效，只能写0x00,0x01,0x02,0x03;
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0xC1);//这里原来是c0 我改成了c5  配置配置寄存器高8位
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X63);//配置配置寄存器低8位  yuan lai shi 83
        IIC_1_Wait_Ack();
        IIC_1_Stop();          
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X90);//发送写地址给ADS1115(0x90); 进行一次转换
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X00);//要配置0x00地址的寄存器（转换寄存器 只读）
        IIC_1_Wait_Ack();
        IIC_1_Stop();         
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X91);//发送读地址给ADS1115(0x91);
        IIC_1_Wait_Ack();       //等待应答
        data1=IIC_1_Read_Byte(1);//读取ADS1115高位的数据
        data2=IIC_1_Read_Byte(1); // 读取ADS1115低位的数据     
        IIC_1_Stop();       

        sensor0=data1;
        sensor0=sensor0<<8;
        sensor0=sensor0+data2;  //ok  到这里 16位数据搞到手了                                             
        v0=sensor0*base;               //自己算吧，这个值是放大后的值，要自己缩回去比如3.3V
//////////////////////////////////////////////////////////////////////////////////A0通道转换结束
//////////////////////////////////////////////////////////////////////////////////开始A1通道的转换
       delay_ms(10);
        IIC_1_Start();
        IIC_1_Send_Byte(0X90);
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X01);
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0xD1); //这里原来是e0
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X63);
        IIC_1_Wait_Ack();
        IIC_1_Stop();                 
        delay_ms(10);


        IIC_1_Start();
        IIC_1_Send_Byte(0X90);
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X00);
        IIC_1_Wait_Ack();
        IIC_1_Stop();                 
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X91);
        IIC_1_Wait_Ack();       
        data3=IIC_1_Read_Byte(1);
        data4=IIC_1_Read_Byte(1);       
        IIC_1_Stop();       

        sensor1=data3;
        sensor1<<=8;
        sensor1=sensor1+data4; 
				v1=sensor1*base;
        //v2=sensor2*base ;
//////////////////////////////////////////////////////////////////////////////////A1通道转换结束
//////////////////////////////////////////////////////////////////////////////////开始A2通道的转换
delay_ms(10);
        IIC_1_Start();
        IIC_1_Send_Byte(0X90);//发送写地址给ADS1115(0x90);
        IIC_1_Wait_Ack();   //等待应答
        IIC_1_Send_Byte(0X01);//要配置01地址的寄存器（配置寄存器）向地址指针寄存器写数据，后两位有效，只能写0x00,0x01,0x02,0x03;
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0xE1);//这里原来是c0 我改成了c5  配置配置寄存器高8位
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X63);//配置配置寄存器低8位
        IIC_1_Wait_Ack();
        IIC_1_Stop();          
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X90);//发送写地址给ADS1115(0x90); 进行一次转换
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X00);//要配置0x00地址的寄存器（转换寄存器 只读）
        IIC_1_Wait_Ack();
        IIC_1_Stop();         
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X91);//发送读地址给ADS1115(0x91);
        IIC_1_Wait_Ack();       //等待应答
        data5=IIC_1_Read_Byte(1);//读取ADS1115高位的数据
        data6=IIC_1_Read_Byte(1); // 读取ADS1115低位的数据     
        IIC_1_Stop();       

        sensor2=data5;
        sensor2=sensor2<<8;
        sensor2=sensor2+data6;                                               
        v2=sensor2*base;
//////////////////////////////////////////////////////////////////////////////////A2通道转换结束
//////////////////////////////////////////////////////////////////////////////////开始A3通道的转换
delay_ms(10);
        IIC_1_Start();
        IIC_1_Send_Byte(0X90);//发送写地址给ADS1115(0x90);
        IIC_1_Wait_Ack();   //等待应答
        IIC_1_Send_Byte(0X01);//要配置01地址的寄存器（配置寄存器）向地址指针寄存器写数据，后两位有效，只能写0x00,0x01,0x02,0x03;
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0xF1);//这里原来是c0 我改成了c5  配置配置寄存器高8位
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X63);//配置配置寄存器低8位
        IIC_1_Wait_Ack();
        IIC_1_Stop();          
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X90);//发送写地址给ADS1115(0x90); 进行一次转换
        IIC_1_Wait_Ack();
        IIC_1_Send_Byte(0X00);//要配置0x00地址的寄存器（转换寄存器 只读）
        IIC_1_Wait_Ack();
        IIC_1_Stop();         
        delay_ms(10);

        IIC_1_Start();
        IIC_1_Send_Byte(0X91);//发送读地址给ADS1115(0x91);
        IIC_1_Wait_Ack();       //等待应答
        data7=IIC_1_Read_Byte(1);//读取ADS1115高位的数据
        data8=IIC_1_Read_Byte(1); // 读取ADS1115低位的数据     
        IIC_1_Stop();       

        sensor3=data7;
        sensor3=sensor3<<8;
        sensor3=sensor3+data8;                                               
        v3=sensor3*base;
//////////////////////////////////////////////////////////////////////////////////A3通道转换结束
} 
////////////////////////***********************************************************************
////////////////////////***********************************************************************
////////////////////////***********************************************************************
////////////////////////***********************************************************************
////////////////////////***********************************************************************
////////////////////////***********************************************************************
////////////////////////***********************************************************************
////////////////////////***********************************************************************
void IIC_2_Init(void)    //这个1好IIC是用来采集数据的
{                       
  GPIO_InitTypeDef  GPIO_InitStructure;

  RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOB, ENABLE);

   
  GPIO_InitStructure.GPIO_Pin = GPIO_Pin_10 | GPIO_Pin_11;
  GPIO_InitStructure.GPIO_Mode = GPIO_Mode_OUT;
  GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;
  GPIO_InitStructure.GPIO_Speed = GPIO_Speed_100MHz;
  GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;
  GPIO_Init(GPIOB, &GPIO_InitStructure);
        IIC_1_SCL=1;
        IIC_1_SDA=1;
}
//产生IIC起始信号
void IIC_2_Start(void)
{
        IIC_2_SDA_OUT();      
        IIC_2_SDA=1;     //数据的有效性：传输数据是 SDA上的数据必须得在SCL高电平到来之前就得准备好！所以 SDA先拉高下一行SCL再拉高               
        IIC_2_SCL=1;
        delay_us(4);
        IIC_2_SDA=0;  
        delay_us(4); //在SCL为高电平期间 将SDA由高拉到低
        IIC_2_SCL=0;
}          
//产生IIC停止信号
void IIC_2_Stop(void)
{
        IIC_2_SDA_OUT();
        IIC_2_SCL=0;
        IIC_2_SDA=0;
        delay_us(4);
        IIC_2_SCL=1;
        IIC_2_SDA=1;
        delay_us(4);                                                                  
}
//等待应答信号到来
//返回值：1，接收应答失败
//        0，接收应答成功 //0为成功是因为低电平有效
u8 IIC_2_Wait_Ack(void)
{
        u8 ucErrTime=0;
        IIC_2_SDA_IN();  //主机的把信号线设置为输入，等到接收器反馈过来的信号 所以我们把数据线设置为输入    
        IIC_2_SDA=1;delay_us(1);          
        IIC_2_SCL=1;delay_us(1);         
        while(IIC_2_READ_SDA)
        {
                ucErrTime++;
                if(ucErrTime>250)
                {
                        IIC_2_Stop();
								//	printf("修正:");
                        return 1;
                }
        }
        IIC_2_SCL=0;   
        return 0;  
}
//产生ACK应答
void IIC_2_Ack(void)
{
        IIC_2_SCL=0;
        IIC_2_SDA_OUT();
        IIC_2_SDA=0;//有效应答SDA就是0  低电平为有效应答
        delay_us(2);
        IIC_2_SCL=1;
        delay_us(2);
        IIC_2_SCL=0;
}
//不产生ACK应答                    
void IIC_2_NAck(void)
{
        IIC_2_SCL=0;
        IIC_2_SDA_OUT();
        IIC_2_SDA=1; //有效应答SDA是1  高电平为有效应答
        delay_us(2);
        IIC_2_SCL=1;
        delay_us(2);
        IIC_2_SCL=0;
}                                                                              
//IIC发送一个字节
//返回从机有无应答
//1，有应答
//0，无应答                          
void IIC_2_Send_Byte(u8 txd)
{                        
    u8 t;   
         IIC_2_SDA_OUT();             
   IIC_2_SCL=0; //发送数据肯定先把SCL拉低钳住，先趁此时SCL低电平期间先把SDA给确认了准备好
    for(t=0;t<8;t++)
    {              
        IIC_2_SDA=(txd&0x80)>>7; //哈哈 没错，趁着SCL前面被搞成低电平，被恢复成高电平之前先把SDA给确定了  一共八个位的数据，那就先从最左边开始处理呗
        txd<<=1;          //准备一下次高位  第二轮就是这个了 
                delay_us(2);   
                IIC_2_SCL=1;
                delay_us(2);
                IIC_2_SCL=0;    //一轮又一轮 一共0-7 八轮  都是如此   
                delay_us(2);
    }         
}             
//读1个字节，ack=1时，发送ACK，ack=0，发送nACK   
u8 IIC_2_Read_Byte(unsigned char ack)
{
        unsigned char i,receive=0;
        IIC_2_SDA_IN();//读的话数据线肯定设置为输入啊
    for(i=0;i<8;i++ )
        {
        IIC_2_SCL=0;
        delay_us(2);
                IIC_2_SCL=1;
        receive<<=1;
        if(IIC_2_READ_SDA)receive++;  //这个位的数据是1你才加一，不是1往左移一位就ok 
                delay_us(1);
    }  //ok 8轮的循环完成  数据接收完成                                       
    if (!ack)
        IIC_2_NAck();
    else
        IIC_2_Ack();  
    return receive;
}


/*
        ADS1115
        测试平台是STM32F407VET6
        读取双通道电压，通道1是IN0脚对地电压        ，通道2是IN2脚对地电压
        读取范围为±6.144 V，注意是正负，所以变量不要定义为uint,                               
        base计算方式：6.144*2/65535≈0.00018750，放大100000000倍为18750整数比较好计算
        注意delay_ms(10)不能删除，读取双通道的时候不加这个延迟，会出现读取通道1 却读到的是通道2的值，读通道2又读的是通道1的值
*/
u16 base1=18750;                 
int v1_0,v1_1,v1_2,v1_3;

void ADS_1_Read(void)                 
{
        short  int sensor0=0;
        short  int sensor1=0;
        short  int sensor2=0;
        short  int sensor3=0;
        u8  data1=0;                       
        u8  data2=0;       
        u8  data3=0;                       
        u8  data4=0;
        u8  data5=0;                       
        u8  data6=0;       
        u8  data7=0;                       
        u8  data8=0;  

		
//////////////////////////////////////////////////////////////////////////////////开始A0通道的转换

        IIC_2_Start();
        IIC_2_Send_Byte(0X90);//发送写地址给ADS1115(0x90);
        IIC_2_Wait_Ack();   //等待应答
        IIC_2_Send_Byte(0X01);//要配置01地址的寄存器（配置寄存器）向地址指针寄存器写数据，后两位有效，只能写0x00,0x01,0x02,0x03;
        IIC_2_Wait_Ack();
	
			
	
        IIC_2_Send_Byte(0xC1);//这里原来是c0 我改成了c5  配置配置寄存器高8位
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X63);//配置配置寄存器低8位  yuan lai shi 83
        IIC_2_Wait_Ack();
        IIC_2_Stop();          
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X90);//发送写地址给ADS1115(0x90); 进行一次转换
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X00);//要配置0x00地址的寄存器（转换寄存器 只读）
        IIC_2_Wait_Ack();
        IIC_2_Stop();         
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X91);//发送读地址给ADS1115(0x91);
        IIC_2_Wait_Ack();       //等待应答
        data1=IIC_2_Read_Byte(1);//读取ADS1115高位的数据
        data2=IIC_2_Read_Byte(1); // 读取ADS1115低位的数据     
        IIC_2_Stop();  

        sensor0=data1;
        sensor0=sensor0<<8;
        sensor0=sensor0+data2;  //ok  到这里 16位数据搞到手了                                             
        v1_0=sensor0*base1;               //自己算吧，这个值是放大后的值，要自己缩回去比如3.3V
//////////////////////////////////////////////////////////////////////////////////A0通道转换结束
//////////////////////////////////////////////////////////////////////////////////开始A1通道的转换
       // delay_ms(1);
        IIC_2_Start();
        IIC_2_Send_Byte(0X90);
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X01);
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0xD1); //这里原来是e0
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X63);
        IIC_2_Wait_Ack();
        IIC_2_Stop();                 
        delay_ms(10);


        IIC_2_Start();
        IIC_2_Send_Byte(0X90);
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X00);
        IIC_2_Wait_Ack();
        IIC_2_Stop();                 
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X91);
        IIC_2_Wait_Ack();       
        data3=IIC_2_Read_Byte(1);
        data4=IIC_2_Read_Byte(1);       
        IIC_2_Stop();       

        sensor1=data3;
        sensor1<<=8;
        sensor1=sensor1+data4; 
				v1_1=sensor1*base1;
        //v2=sensor2*base ;
//////////////////////////////////////////////////////////////////////////////////A1通道转换结束
//////////////////////////////////////////////////////////////////////////////////开始A2通道的转换
        //delay_ms(1);
        IIC_2_Start();
        IIC_2_Send_Byte(0X90);//发送写地址给ADS1115(0x90);
        IIC_2_Wait_Ack();   //等待应答
				

				
        IIC_2_Send_Byte(0X01);//要配置01地址的寄存器（配置寄存器）向地址指针寄存器写数据，后两位有效，只能写0x00,0x01,0x02,0x03;
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0xE1);//这里原来是c0 我改成了c5  配置配置寄存器高8位
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X63);//配置配置寄存器低8位
        IIC_2_Wait_Ack();
        IIC_2_Stop();          
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X90);//发送写地址给ADS1115(0x90); 进行一次转换
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X00);//要配置0x00地址的寄存器（转换寄存器 只读）
        IIC_2_Wait_Ack();
        IIC_2_Stop();         
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X91);//发送读地址给ADS1115(0x91);
        IIC_2_Wait_Ack();       //等待应答
        data5=IIC_2_Read_Byte(1);//读取ADS1115高位的数据
        data6=IIC_2_Read_Byte(1); // 读取ADS1115低位的数据     
        IIC_2_Stop();       

        sensor2=data5;
        sensor2=sensor2<<8;
        sensor2=sensor2+data6;                                               
        v1_2=sensor2*base1;
//////////////////////////////////////////////////////////////////////////////////A2通道转换结束
//////////////////////////////////////////////////////////////////////////////////开始A3通道的转换
        //delay_ms(1);
        IIC_2_Start();
        IIC_2_Send_Byte(0X90);//发送写地址给ADS1115(0x90);
        IIC_2_Wait_Ack();   //等待应答
        IIC_2_Send_Byte(0X01);//要配置01地址的寄存器（配置寄存器）向地址指针寄存器写数据，后两位有效，只能写0x00,0x01,0x02,0x03;
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0xF1);//这里原来是c0 我改成了c5  配置配置寄存器高8位
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X63);//配置配置寄存器低8位
        IIC_2_Wait_Ack();
        IIC_2_Stop();          
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X90);//发送写地址给ADS1115(0x90); 进行一次转换
        IIC_2_Wait_Ack();
        IIC_2_Send_Byte(0X00);//要配置0x00地址的寄存器（转换寄存器 只读）
        IIC_2_Wait_Ack();
        IIC_2_Stop();         
        delay_ms(10);

        IIC_2_Start();
        IIC_2_Send_Byte(0X91);//发送读地址给ADS1115(0x91);
        IIC_2_Wait_Ack();       //等待应答
        data7=IIC_2_Read_Byte(1);//读取ADS1115高位的数据
        data8=IIC_2_Read_Byte(1); // 读取ADS1115低位的数据     
        IIC_2_Stop();       

        sensor3=data7;
        sensor3=sensor3<<8;
        sensor3=sensor3+data8;                                               
        v1_3=sensor3*base1;
//////////////////////////////////////////////////////////////////////////////////A3通道转换结束
} 


void ADC_angle_Check(void)
{

 //0左前，1右前，2左后，3右后
	ADS_angle_Read();   //上电后等电压值稳定了 就第一次采集一下角度电位计的电压值确定初始位置 左后AD是A0 左前AD是A1  右前AD是A2 右后AD是A3


				 volt0=v0*0.00000001; //是电压值   左前
				 volt1=v1*0.00000001;  // 左后
				 volt2=v2*0.00000001;   // 右前
				 volt3=v3*0.00000001;   // 左后

	AD_angle[0]=volt0*2*3.1415/3.294;
	AD_angle[1]=volt3*2*3.1415/3.294;
  AD_angle[2]=volt1*2*3.1415/3.294;
	AD_angle[3]=volt2*2*3.1415/3.294;
	
	
	
	
//	printf(" conf0 %f  conf1 %f conf2 %f conf3 %f dd %f dd %f dd %f dd %f\r\n ",volt0,volt1,volt2,volt3,check_current0,check_current1,check_current2,check_current3) ; 
	
}


void ADC_electric_Check(void)
{
   ADS_1_Read();  

			check_current0=v1_0*0.00000001;
			check_current1=v1_1*0.00000001;
			check_current2=v1_2*0.00000001;
			check_current3=v1_3*0.00000001;
	
	
//  battery_voltage=check_current1*17.579;  // 乘固定放大倍数
//	battery_voltage=check_current1*31.14875;
	battery_voltage=check_current1*30.00875;
  stop_voltage=check_current0;
	base_voltage=check_current2;
	control_voltage=check_current3;
	

//printf("  dd %f dd %f dd %f hhh %f\r\n ",battery_voltage,stop_voltage,base_voltage,check_current3) ; 
	

}
	

