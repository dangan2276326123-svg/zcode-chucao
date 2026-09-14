# 绪论
<!-- chapter_id: ch_1 -->

## 研究背景与意义

中草药是我国中医药事业与大健康产业的物质基础，随着国家中医药发展战略的推进，中药材人工种植面积持续扩大。黄芩、柴胡、金银花、芍药等大宗中草药以露地栽培为主，部分产区采用林药套作模式（药材种植于林冠行间），地块面积小而分散[[REF:KEYWORD_PLACEHOLDER: 潘月占, 丁润锁, 杨顶浩, 等. 京津冀林下中草药种植除草机器人现状与需求调研[J]. 农业工程技术, 2026(待补卷期页).]]。在这一复合种植模式下，杂草与药材争水争肥、传播病虫害，是影响药材产量与品质的主要生物胁迫之一；同时中药材质量标准对农药残留有严格限定，多数药用植物为双子叶植物，对广谱性除草剂高度敏感，化学除草极易造成药害与土壤污染，应用受到严格限制[[REF:KEYWORD_PLACEHOLDER: Slaughter D C, Giles D K, Downey D. Autonomous robotic weed control systems: A review[J]. Computers and Electronics in Agriculture, 2008, 61(1): 63-78.]]。

除草因此成为中草药种植中用工量最大、成本占比最高的田间管理环节。调研数据显示：人工除草效率仅约 0.3~0.5 亩/(人·天)，日薪 120~180 元，除草环节投入占种植管理总成本的 40% 以上，是占比最高的单项管理成本[[REF:KEYWORD_PLACEHOLDER: 潘月占, 丁润锁, 杨顶浩, 等. 京津冀林下中草药种植除草机器人现状与需求调研[J]. 农业工程技术, 2026(待补卷期页).]]。农村劳动力老龄化加剧，除草作业人员以中老年为主，用工旺季普遍存在"招工难"问题，劳动力短缺将进一步推高除草成本。小型割灌机等通用机械虽可提高效率至 2~3 亩/(台·天)，但其作业原理以切割茎叶为主，不切断杂草根系导致再生迅速，且作业精度低，对药材幼苗的机械损伤率可达 8%~15%，不适用于幼苗期精细作业。

机械化除草难以推广的另一重障碍在于导航与结构适配。中草药多为窄行密植，行距普遍为 30~60 cm，行间作业空间狭小；地块面积小而分散，部分产区地表起伏、田块不规则。传统农机依赖的 GNSS-RTK 高精度定位设备成本高、需要基站支持，且在树冠遮挡与设施环境条件下信号可靠性下降，与中草药种植的小规模、分散化经营特点不匹配[[REF:KEYWORD_PLACEHOLDER: 潘月占, 丁润锁, 杨顶浩, 等. 京津冀林下中草药种植除草机器人现状与需求调研[J]. 农业工程技术, 2026(待补卷期页).]]。相比之下，基于机器视觉的导航方式以作物行本身为参照，不需外部定位设施，设备成本低，且能同时提供苗草识别信息，是中草药行间除草装备最适宜的感知路线[[REF:KEYWORD_PLACEHOLDER: Åstrand B, Baerveldt A J. An agricultural mobile robot with vision-based perception for mechanical weed control[J]. Autonomous Robots, 2002, 13(1): 21-35.]]。

综上所述，研制一种以纯视觉导航为核心、面向中草药窄行行间作业的小型除草机，实现对行行走、深度控制与除草装置的协同作业，对降低除草成本、减少药材损伤、推动中草药生产机械化具有重要的现实意义，也为非结构化农田环境下农业机器人的视觉导航提供方法参考。

## 国内外研究现状

### 除草机器人整机研究现状

国外对除草机器人的研究起步较早。Åstrand 等[[REF:KEYWORD_PLACEHOLDER: Åstrand B, Baerveldt A J. An agricultural mobile robot with vision-based perception for mechanical weed control[J]. Autonomous Robots, 2002, 13(1): 21-35.]]研制的园艺除草机器人采用视觉感知与机械锄铲结合的方案，实现了甘蓝行间的自主除草，验证了"视觉导航+行间机械除草"技术路线的可行性。Slaughter 等[[REF:KEYWORD_PLACEHOLDER: Slaughter D C, Giles D K, Downey D. Autonomous robotic weed control systems: A review[J]. Computers and Electronics in Agriculture, 2008, 61(1): 63-78.]]系统综述了自主除草控制系统的感知、决策与执行技术，指出作物行几何信息的可靠获取是行间除草装备的前提。德国 Osnabrück 应用科学大学研制的 BoniRob 平台[[REF:KEYWORD_PLACEHOLDER: Ruckelshausen A, Bise P B, Heme P, et al. BoniRob—an autonomous field robot platform for individual plant phenotyping[C]//Precision Agriculture '09. Wageningen: Wageningen Academic Publishers, 2009: 741-747.]]为株间与行间作业提供了通用移动平台，其四轮独立驱动、独立转向的底盘构型被后续多种除草样机借鉴。丹麦 Robovator 系列行间除草机采用相机识别作物行并液压控制锄铲横向跟踪，已在多国商品化应用；丹麦 Agro Intelligence 公司的 Robovator 与法国的 EcoWeeder 等产品代表了行间除草装备的商品化水平<待核实：Robovator 与 EcoWeeder 等商品化机型的公开文献，建议检索厂商技术资料及期刊报道>。

在视觉导航研究方面，Hague 等[[REF:KEYWORD_PLACEHOLDER: Hague T, Marchant J A, Tillett N D. Ground based sensing systems for autonomous agricultural vehicles[J]. Computers and Electronics in Agriculture, 2000, 25(1/2): 11-28.]]较早综述了地面移动农业机器人基于视觉的导航感知体系；Bakker 等[[REF:KEYWORD_PLACEHOLDER: Bakker T, Wouters H, van Asselt K, et al. A vision based row detection system for sugar beet[J]. Computers and Electronics in Agriculture, 2008, 60(1): 87-95.]]开发了甜菜田基于视觉的行检测系统，采用过绿指数分割与 Hough 变换拟合行线；Kise 等[[REF:KEYWORD_PLACEHOLDER: Kise M, Zhang Q, Rovira Más F. A stereovision-based crop row detection method for tractor-automated guidance[J]. Biosystems Engineering, 2005, 90(4): 357-367.]]提出基于立体视觉与 Hough 变换的作物行检测方法用于拖拉机自动导航。国内方面，高校与科研院所在视觉导航除草装备领域开展了大量研究，已有"谷物联合收割机视觉导航路径识别系统"等授权专利[[REF:KEYWORD_PLACEHOLDER: 谭彧, 等. 谷物联合收割机视觉导航路径识别系统: 中国专利 CN103914071.]]。<待补充：国内除草机器人整机与视觉导航研究综述 3~5 篇（建议检索《农业机械学报》《农业工程学报》《智慧农业》"除草机器人""视觉导航"关键词），以及 Hortibot、EcoRobotix 等机型的公开文献>。

总体来看，除草机器人整机的成熟应用集中于大田粮食作物与标准化果园，面向中草药这类窄行、高值、小地块作物的专用装备仍属空白，其核心难点在于窄行空间下的高精度对行与低伤苗率除草。

### 作物行视觉感知研究现状

作物行感知的经典方法以颜色特征与几何拟合为主：利用过绿指数（ExG）等颜色指数分割植被与土壤背景，再以 Hough 变换、灰度重心法或最小二乘拟合提取行线[[REF:KEYWORD_PLACEHOLDER: Bakker T, Wouters H, van Asselt K, et al. A vision based row detection system for sugar beet[J]. Computers and Electronics in Agriculture, 2008, 60(1): 87-95.]]。此类方法在光照变化、杂草密度高、作物苗期覆盖率低时鲁棒性不足。

随着深度学习的发展，语义分割成为作物/杂草识别的主流方法。Long 等[[REF:KEYWORD_PLACEHOLDER: Long J, Shelhamer E, Darrell T. Fully convolutional networks for semantic segmentation[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Boston: IEEE, 2015: 3431-3440.]]提出的全卷积网络（FCN）确立了端到端像素级分割范式；Ronneberger 等[[REF:KEYWORD_PLACEHOLDER: Ronneberger O, Fischer P, Brox T. U-Net: Convolutional networks for biomedical image segmentation[C]//Medical Image Computing and Computer-Assisted Intervention (MICCAI 2015). Cham: Springer, 2015: 234-241.]]提出的 U-Net 以编解码跳连结构在小样本农业图像中表现优异；He 等[[REF:KEYWORD_PLACEHOLDER: He K, Zhang X, Ren S, et al. Deep residual learning for image recognition[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Las Vegas: IEEE, 2016: 770-778.]]的残差学习解决了深层网络退化问题，为分割骨干网络奠定基础。在多尺度上下文建模方面，Yu 等[[REF:KEYWORD_PLACEHOLDER: Yu F, Koltun V. Multi-scale context aggregation by dilated convolutions[C]//International Conference on Learning Representations (ICLR). San Juan, 2016.]]提出空洞卷积扩大感受野，Zhao 等[[REF:KEYWORD_PLACEHOLDER: Zhao H, Shi J, Qi X, et al. Pyramid scene parsing network[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Honolulu: IEEE, 2017: 2881-2890.]]提出金字塔场景解析网络（PSPNet），Badrinarayanan 等[[REF:KEYWORD_PLACEHOLDER: Badrinarayanan V, Kendall A, Cipolla R. SegNet: A deep convolutional encoder-decoder architecture for image segmentation[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 2017, 39(12): 2481-2495.]]提出 SegNet 编解码结构。Chen 等[[REF:KEYWORD_PLACEHOLDER: Chen L C, Papandreou G, Schroff F, et al. Rethinking atrous convolution for semantic image segmentation[EB/OL]. (2017-06-15). arXiv: 1706.05587.]]在空洞卷积基础上提出 DeepLabv3，并进一步提出融合编码-解码与空洞空间金字塔池化（ASPP）的 DeepLabv3+[[REF:KEYWORD_PLACEHOLDER: Chen L C, Zhu Y, Papandreou G, et al. Encoder-decoder with atrous separable convolution for semantic image segmentation[C]//Proceedings of the European Conference on Computer Vision (ECCV). Munich: Springer, 2018: 801-818.]]，在边界细节与多尺度目标分割上具有优势，适合作物行这类细长条带状目标的提取。

面向田间部署的实时性需求，轻量化网络成为研究热点。Howard 等[[REF:KEYWORD_PLACEHOLDER: Howard A G, Zhu M, Chen B, et al. MobileNets: Efficient convolutional neural networks for mobile vision applications[EB/OL]. (2017-04-17). arXiv: 1704.04861.]]与 Sandler 等[[REF:KEYWORD_PLACEHOLDER: Sandler M, Howard A, Zhu M, et al. MobileNetV2: Inverted residuals and linear bottlenecks[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Salt Lake City: IEEE, 2018: 4510-4520.]]提出的 MobileNet 系列以深度可分离卷积大幅降低计算量，Chollet[[REF:KEYWORD_PLACEHOLDER: Chollet F. Xception: Deep learning with depthwise separable convolutions[C]//Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition. Honolulu: IEEE, 2017: 1251-1258.]]的 Xception 将深度可分离卷积推到极致。以 MobileNetV2 为骨干的 DeepLabv3+ 在精度与速度之间取得较好平衡，是农业视觉嵌入式部署的常用选择。此外，注意力机制[[REF:KEYWORD_PLACEHOLDER: Oktay O, Schlemper J, Folgoc L L, et al. Attention U-Net: Learning where to look for the pancreas[EB/OL]. (2018-04-11). arXiv: 1804.03999.]]与目标检测框架[[REF:KEYWORD_PLACEHOLDER: Redmon J, Farhadi A. YOLOv3: An incremental improvement[EB/OL]. (2018-04-08). arXiv: 1804.02767.]]也被用于苗草识别与株间定位。<待补充：语义分割在作物与杂草识别中的应用文献 3~5 篇（建议检索农业工程领域英文期刊数据库）>

### 行间除草工作部件研究现状

行间除草工作部件决定除草机理与伤苗风险。Åstrand 等[[REF:KEYWORD_PLACEHOLDER: Åstrand B, Baerveldt A J. An agricultural mobile robot with vision-based perception for mechanical weed control[J]. Autonomous Robots, 2002, 13(1): 21-35.]]采用锄铲式部件；Robovator 采用液压驱动锄铲横向跟踪行间；弹齿式、圆盘式、旋转锄等部件在大田中耕领域应用成熟[[REF:KEYWORD_PLACEHOLDER: Slaughter D C, Giles D K, Downey D. Autonomous robotic weed control systems: A review[J]. Computers and Electronics in Agriculture, 2008, 61(1): 63-78.]]。铲类部件与土壤相互作用的研究以土壤-刀具力学模型为基础，McKyes[[REF:KEYWORD_PLACEHOLDER: McKyes E. Soil cutting and tillage[M]. Amsterdam: Elsevier, 1985.]]系统建立了铲刃切削土壤的阻力模型，为铲式部件的参数设计与牵引阻力估算提供了理论工具。已有研究多针对单一部件的阻力与除草效果，缺少面向中草药农艺约束（浅根、幼苗脆嫩、行间窄）按作用机理逐项比选的系统性论证，本文在第 2 章完成这一工作。

### 研究现状总结

综合国内外研究现状可得：（1）"视觉导航+行间机械除草"路线已在多种作物上验证可行，但面向中草药窄行高值场景的专用装备缺乏；（2）以 DeepLabv3+ 为代表的语义分割方法能够为行间除草提供鲁棒的作物行感知，其轻量化组合具备田间部署能力，但需要针对具体作物与物候期进行训练与域适应；（3）除草部件选型缺少面向中草药农艺的机理化论证，除草深度控制与刀具横向对行的协同控制研究不足。上述缺口构成本文的研究切入点。

## 主要研究内容与技术路线

本文以"纯视觉导航+行间机械除草"为技术主线，围绕中草药行间除草机的系统设计开展研究，主要研究内容如下：

（1）中草药行间除草机总体方案与机械系统设计。完成移动平台选型与改造、入土深度（限深仿形）装置设计、除草装置选型论证与结构设计（含铲类部件受力分析），以及车载电控与固件的双指令源线控改造。

（2）基于语义分割的导航线提取方法。构建"相机标定—去畸变—DeepLabV3+ 分割—逆透视变换—双墙提取"的感知链，从单目图像中解算作物行双墙边界与行间导航线，并在夏季田间数据集上训练评估分割模型。

（3）运动控制系统设计。建立四轮独立转向（4WS）阿克曼底盘运动学模型与横向偏差卡尔曼滤波估计方法，设计轨迹跟踪 PD 控制、除草深度控制（入土控制）与中间除草刀横向对行 PID 控制，并研究无线链路时延估计与前馈补偿方法。

（4）田间对比试验方案设计与验证。设计不同除草装置（鸭掌铲与弹齿）对比试验、刀具控制与不控制（主动对行与固定刀）对比试验，验证整机作业性能。

技术路线如图所示：需求分析→总体方案→机械系统设计→感知算法开发与训练→控制系统设计→台架验证→田间试验→统计分析。

[[FIG:技术路线图]]

## 论文组织结构

本文共分 6 章：第 1 章绪论；第 2 章中草药行间除草机总体与机械系统设计，包括移动平台、入土深度装置、除草装置设计与车载固件；第 3 章导航线提取，包括相机标定、语义分割模型与双墙中心线解算；第 4 章运动控制，包括轨迹跟踪控制、入土控制与除草装置控制；第 5 章田间试验；第 6 章结论与展望。
