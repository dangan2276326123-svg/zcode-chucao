import os
import math
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.model_zoo as model_zoo

pretrained_settings = {
    'xception': {
        'imagenet': {
            'url': 'http://data.lip6.fr/cadene/pretrainedmodels/xception-43020ad28.pth',
            'input_space': 'RGB',
            'input_size': [3, 299, 299],
            'input_range': [0, 1],
            'mean': [0.5, 0.5, 0.5],
            'std': [0.5, 0.5, 0.5],
            'num_classes': 1000,
            'scale': 0.8975
        }
    }
}

class SeparableConv2d(nn.Module):
    def __init__(self,in_channels,out_channels,kernel_size=1,stride=1,padding=0,dilation=1,bias=False):
        super(SeparableConv2d,self).__init__()
        self.conv1 = nn.Conv2d(in_channels,in_channels,kernel_size,stride,padding,dilation,groups=in_channels,bias=bias)
        self.pointwise = nn.Conv2d(in_channels,out_channels,1,1,0,1,1,bias=bias)
    def forward(self,x):
        x = self.conv1(x)
        x = self.pointwise(x)
        return x

class Block(nn.Module):
    def __init__(self,in_filters,out_filters,reps,strides=1,start_with_relu=True,grow_first=True):
        super(Block, self).__init__()
        if out_filters != in_filters or strides!=1:
            self.skip = nn.Conv2d(in_filters,out_filters,1,stride=strides, bias=False)
            self.skipbn = nn.BatchNorm2d(out_filters)
        else:
            self.skip=None
        rep=[]
        filters=in_filters
        if grow_first:
            rep.append(nn.ReLU(inplace=True))
            rep.append(SeparableConv2d(in_filters,out_filters,3,stride=1,padding=1,bias=False))
            rep.append(nn.BatchNorm2d(out_filters))
            filters = out_filters
        for i in range(reps-1):
            rep.append(nn.ReLU(inplace=True))
            rep.append(SeparableConv2d(filters,filters,3,stride=1,padding=1,bias=False))
            rep.append(nn.BatchNorm2d(filters))
        if not grow_first:
            rep.append(nn.ReLU(inplace=True))
            rep.append(SeparableConv2d(in_filters,out_filters,3,stride=1,padding=1,bias=False))
            rep.append(nn.BatchNorm2d(out_filters))
        if not start_with_relu:
            rep = rep[1:]
        else:
            rep[0] = nn.ReLU(inplace=False)
        if strides != 1:
            rep.append(nn.MaxPool2d(3,strides,1))
        self.rep = nn.Sequential(*rep)
    def forward(self,inp):
        x = self.rep(inp)
        if self.skip is not None:
            skip = self.skip(inp)
            skip = self.skipbn(skip)
        else:
            skip = inp
        x+=skip
        return x

class Xception(nn.Module):
    def __init__(self, num_classes=1000, replace_stride_with_dilation=None):
        super(Xception, self).__init__()
        self.num_classes = num_classes
        self.replace_stride_with_dilation = replace_stride_with_dilation

        self.conv1 = nn.Conv2d(3, 32, 3,2, 0, bias=False)
        self.bn1 = nn.BatchNorm2d(32)
        self.relu1 = nn.ReLU(inplace=True)

        self.conv2 = nn.Conv2d(32,64,3,bias=False)
        self.bn2 = nn.BatchNorm2d(64)
        self.relu2 = nn.ReLU(inplace=True)

        dilation = 1
        if replace_stride_with_dilation is None:
            replace_stride_with_dilation = [False, False, False, False]
        if len(replace_stride_with_dilation) !=4:
            raise ValueError("replace_stride_with_dilation 长度必须为4")

        self.block1=Block(64,128,2,strides=2 if not replace_stride_with_dilation[0] else 1,start_with_relu=False,grow_first=True)
        if replace_stride_with_dilation[0]:
            dilation *=2
        self.block2=Block(128,256,2,strides=2 if not replace_stride_with_dilation[1] else 1,start_with_relu=True,grow_first=True)
        if replace_stride_with_dilation[1]:
            dilation *=2
        self.block3=Block(256,728,2,strides=2 if not replace_stride_with_dilation[2] else 1,start_with_relu=True,grow_first=True)
        if replace_stride_with_dilation[2]:
            dilation *=2

        self.block4=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block5=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block6=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block7=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block8=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block9=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block10=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)
        self.block11=Block(728,728,3,strides=1,start_with_relu=True,grow_first=True)

        self.block12=Block(728,1024,2,strides=2 if not replace_stride_with_dilation[3] else 1,start_with_relu=True,grow_first=False)
        if replace_stride_with_dilation[3]:
            dilation *=2

        self.conv3 = SeparableConv2d(1024,1536,3,1,dilation,bias=False)
        self.bn3 = nn.BatchNorm2d(1536)
        self.relu3 = nn.ReLU(inplace=True)

        self.conv4 = SeparableConv2d(1536,2048,3,1,dilation,bias=False)
        self.bn4 = nn.BatchNorm2d(2048)

        self.fc = nn.Linear(2048, num_classes)

    def forward(self, input):
        x = self.conv1(input)
        x = self.bn1(x)
        x = self.relu1(x)
        x = self.conv2(x)
        x = self.bn2(x)
        low_level = self.relu2(x)

        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        x = self.block4(x)
        x = self.block5(x)
        x = self.block6(x)
        x = self.block7(x)
        x = self.block8(x)
        x = self.block9(x)
        x = self.block10(x)
        x = self.block11(x)
        x = self.block12(x)

        x = self.conv3(x)
        x = self.bn3(x)
        x = self.relu3(x)
        out = self.conv4(x)
        out = self.bn4(out)
        return out, low_level


def xception(pretrained=False, replace_stride_with_dilation=None, local_weight_path=None):
    # 固定只识别 xception-43020ad28.pth，完全忽略 deeplab_xception.pth
    default_local = r"../model_data/xception-43020ad28.pth"
    if local_weight_path is None:
        local_weight_path = default_local

    model = Xception(num_classes=1000, replace_stride_with_dilation=replace_stride_with_dilation)
    if pretrained:
        settings = pretrained_settings['xception']['imagenet']
        # 仅加载原版imagenet预训练权重，旧deeplab_xception.pth不读取
        if os.path.exists(local_weight_path):
            print(f"加载本地ImageNet Xception预训练权重: {local_weight_path}")
            state_dict = torch.load(local_weight_path, map_location="cpu")
            model.load_state_dict(state_dict, strict=False)
        else:
            print("本地无xception-43020ad28.pth，在线自动下载预训练权重")
            model.load_state_dict(model_zoo.load_url(settings['url']), strict=False)
        model.mean = settings['mean']
        model.std = settings['std']
    return model