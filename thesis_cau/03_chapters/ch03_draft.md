# 导航线提取
<!-- chapter_id: ch_3 -->

## 感知链总体设计

导航线提取的处理链为：图像采集→去畸变→DeepLabV3+ 二分类分割→逆透视变换→双墙提取→远/近场导航线解算。单目相机以低机位前视安装于车体前部，视场覆盖车前 2~3 m 的行间区域；分割网络区分作物行与行间背景；逆透视变换将前视图投影至田面物理坐标系；在鸟瞰域提取作物行左右内边界（双墙），并解算远场导航线（用于底盘轨迹跟踪）与近场草带中心线（用于中间刀对行）。

[[FIG:导航线提取处理链流程图]]

## 相机标定与图像去畸变

### 标定模型

采用张正友平面标定法[[REF:KEYWORD_PLACEHOLDER: Zhang Z. A flexible new technique for camera calibration[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 2000, 22(11): 1330-1334.]]获取相机内参矩阵与畸变系数。相机线性成像模型为[[EQ:s\\tilde{p}=K[R|t]\\tilde{P}]]，式中 [[SYM:K]] 为内参矩阵，[[SYM:[R|t]]] 为外参，[[SYM:\tilde{p}]]、[[SYM:\tilde{P}]] 分别为像点与空间点的齐次坐标。径向与切向畸变采用[[EQ:x_c=x(1+k_1r^2+k_2r^4+k_3r^6)+2p_1xy+p_2(r^2+2x^2)]][[EQ:y_c=y(1+k_1r^2+k_2r^4+k_3r^6)+p_1(r^2+2y^2)+2p_2xy]]描述，[[SYM:k_1,k_2,k_3]] 为径向系数，[[SYM:p_1,p_2]] 为切向系数。

标定采用棋盘格标定板多姿态采图，张正友法利用棋盘格平面与像平面的单应约束线性求解内参初值，再经最大似然优化联合估计畸变系数<待补充：标定图数量、重投影误差数值、标定参数表>。每帧图像推理前先按标定参数去畸变，消除镜头畸变对后续几何解算的影响。

### 标定参数管理

标定参数（内参、畸变系数、IPM 单应矩阵）以参数文件形式管理，支持低机位重新安装后的重标定与参数热更新；与 IPM 相关的梯形映射区参数改为可配置，避免硬编码导致换装相机后映射失效。

## 基于 DeepLabV3+ 的作物行分割

### 网络结构

本文采用 DeepLabv3+[[REF:KEYWORD_PLACEHOLDER: Chen L C, Zhu Y, Papandreou G, et al. Encoder-decoder with atrous separable convolution for semantic image segmentation[C]//Proceedings of the European Conference on Computer Vision (ECCV). Munich: Springer, 2018: 801-818.]]架构、MobileNetV2[[REF:KEYWORD_PLACEHOLDER: Sandler M, Howard A, Zhu M, et al. MobileNetV2: Inverted residuals and linear bottlenecks[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Salt Lake City: IEEE, 2018: 4510-4520.]]骨干的轻量化组合。网络以空洞空间金字塔池化（ASPP）模块并行采用多膨胀率空洞卷积[[REF:KEYWORD_PLACEHOLDER: Yu F, Koltun V. Multi-scale context aggregation by dilated convolutions[C]//International Conference on Learning Representations (ICLR). San Juan, 2016.]]捕获多尺度上下文，解码器以低层特征补全边界细节；MobileNetV2 骨干采用倒残差结构与线性瓶颈，以深度可分离卷积[[REF:KEYWORD_PLACEHOLDER: Chollet F. Xception: Deep learning with depthwise separable convolutions[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Honolulu: IEEE, 2017: 1251-1258.]]将计算量压缩至常规卷积的约 1/8~1/9，满足地面站逐帧推理需求。

输出为二分类掩膜：作物行（含药材苗带）为一类，行间杂草与裸土为背景类。备选骨干包括 Xception[[REF:KEYWORD_PLACEHOLDER: Chollet F. Xception: Deep learning with depthwise separable convolutions[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Honolulu: IEEE, 2017: 1251-1258.]]、ResNet[[REF:KEYWORD_PLACEHOLDER: He K, Zhang X, Ren S, et al. Deep residual learning for image recognition[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Las Vegas: IEEE, 2016: 770-778.]]与 HRNet<待核实：HRNet 文献，Wang J, et al., TPAMI 2020>，骨干可替换以支持精度-速度权衡实验。

### 损失函数与训练策略

训练采用交叉熵与 Dice 联合损失[[EQ:L=L_{CE}+\\lambda L_{Dice}]]，式中交叉熵项[[EQ:L_{CE}=-\\sum_i y_i\\log p_i+(1-y_i)\\log(1-p_i)]]，Dice 项[[EQ:L_{Dice}=1-\\frac{2\\sum_i p_i y_i}{\\sum_i p_i+\\sum_i y_i}]]。Dice 项缓解苗期作物行像素占比小、类别不均衡导致的边界欠分割问题；[[SYM:\lambda]] 为平衡权重<待补充：训练超参数表（学习率、批大小、优化器、增强策略）与数据集划分>。

训练采用混合精度加速、断点续训与早停策略；备选骨干支持消融对比。针对跨季节杂草种类与色泽差异造成的域偏移，计划补采 200~300 张目标物候期样本微调，并保留传统图像处理行线提取作为兜底通道。

### 分割模型训练与评估结果

模型在夏季田间图像数据集上训练 202 轮，验证集评估指标如表 3-1 所示（证据：项目训练日志）。

表 3-1 DeepLabV3+ 验证集评估指标（第 200~202 轮）

| 指标 | 第 200 轮 | 第 201 轮 | 第 202 轮 |
| --- | --- | --- | --- |
| 验证损失 | 0.2936 | 0.2978 | 0.2905 |
| mIoU | 0.7158 | 0.7163 | 0.7134 |
| MPA | 0.8480 | 0.8442 | 0.8508 |
| Dice | 0.7478 | 0.7465 | 0.7472 |
| 精确率 | 0.6978 | 0.7067 | 0.6863 |
| 召回率 | 0.8110 | 0.7968 | 0.8254 |
| 前景 IoU | 0.5994 | 0.5978 | 0.5990 |
| 背景 IoU | 0.8322 | 0.8347 | 0.8278 |

第 201 轮 mIoU 0.7163（该精调阶段末值）；全程验证集峰值为第 76 轮 0.7459（见训练日志）。背景（行间区域）IoU 达 0.8347，为双墙提取提供了可靠背景识别；前景 IoU 0.5978 相对偏低，主要原因是苗期作物行边缘像素占比小、类别不均衡，可通过损失加权与难例挖掘进一步改善<待补充：测试集指标、逐帧推理速度实测、典型分割结果可视化、不同骨干消融对比>。

需要说明指标的可比性口径：文献中报道的 90% 以上 mIoU 通常基于公开成熟数据集、多类别分割或多轮超参筛选，其类别构成与像素分布与本文任务不同；mIoU 取决于数据集、类别定义与标注口径，跨数据集直接比较不具学术意义。本文模型的定位是支撑双墙提取与导航线解算的系统级任务：行间背景区域分割可靠（背景 IoU 0.8347），足以稳定解算行间导航线；作物行前景 IoU 相对偏低主要源于苗期行带像素占比小与边缘标注的不确定性，属于类别不均衡问题，可通过补采样本微调、损失加权与难例挖掘继续提升（见 3.2.1 节域适应计划）。

## 逆透视变换与误差分析

### 变换原理

逆透视变换（IPM）利用相机外参将前视图投影至田面平面，使图像像素与田面物理坐标建立映射。设田面为平面 [[SYM:Z=0]]，相机内参 [[SYM:K]]、外参 [[SYM:[R|t]]] 已知，则田面点 [[SYM:(X,Y,0)]] 与像点 [[SYM:(u,v)]] 的关系为单应变换[[EQ:s\\begin{bmatrix}u\\\\v\\\\1\\end{bmatrix}=H\\begin{bmatrix}X\\\\Y\\\\1\\end{bmatrix}]]，[[SYM:H]] 为 3×3 单应矩阵。工程上 [[SYM:H]] 由田面已知标记点（4 点以上）直接反推，避免显式估计外参；IPM 映射区（梯形源区与目标区）参数配置化，适配不同安装高度与俯角。

### 投影误差传播分析

IPM 误差主要来源于三部分：（1）标定重投影误差引起的内参扰动 [[SYM:\Delta K]]；（2）田面平面假设误差（地表起伏与垄形）；（3）远场透视压缩放大效应。对 [[SYM:H]] 的扰动 [[SYM:\Delta H]]，像点误差经逆变换传播至田面坐标的相对误差近似为[[EQ:\\frac{\\Delta Y}{Y}\\approx\\frac{\\Delta H}{H}+2\\tan\\theta\\cdot\\frac{\\Delta v}{f}]]，式中 [[SYM:\theta]] 为相机俯角，[[SYM:f]] 为焦距，[[SYM:\Delta v]] 为像点行方向误差。该式表明：远场（[[SYM:Y]] 大）处误差被放大，且俯角越小放大越显著；低机位、大俯角安装可抑制远场误差，与本文低机位前视安装方案一致<待补充：代入实际标定参数后的定量误差曲线>。

## 双墙提取与导航线解算

### 双墙提取

对分割掩膜依次执行形态学开闭运算去噪、连通域分析，按面积与长宽比过滤虚假区域；分别对左右作物行区域提取内边界（面向行间一侧的轮廓），即"双墙"。为抑制单帧抖动，对边界点序列进行时间维度滑动平均滤波。

### 远/近场导航线解算

在 IPM 鸟瞰域内解算两条导航线：（1）远场导航线取双墙几何中线，作为底盘轨迹跟踪的横向偏差基准；（2）近场草带中心线取行间草带质心线，作为中间刀对行目标。单侧墙漏检时，以另一侧墙结合标定行距约束回退解算，回退阈值可配置，避免固定阈值在不同行距地块失效。连续多帧双墙均失效时判定视觉丢失，触发提刀停车联锁（见 4.3 节）。

[[FIG:双墙提取与导航线解算示意图]]

<待补充：avi 田间视频回放的导航线连续性与横向偏差曲线评价>

## 本章小结

本章构建了"标定—分割—IPM—双墙—导航线"的完整感知链：基于张正友标定完成去畸变，DeepLabV3+（MobileNetV2 骨干）分割模型验证集 mIoU 达 0.7163、背景 IoU 达 0.8347；IPM 将感知映射至田面物理坐标系并给出误差传播分析；双墙提取与远/近场导航线解算为第 4 章运动控制提供了统一基准。
