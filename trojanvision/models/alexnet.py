#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from .imagemodel import _ImageModel, ImageModel

import torch
import torch.nn as nn
from torch.utils import model_zoo
import torchvision.models
from torchvision.models.alexnet import model_urls
from collections import OrderedDict


class _AlexNet(_ImageModel):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        _model = torchvision.models.alexnet(num_classes=self.num_classes)
        self.features = _model.features
        self.pool = _model.avgpool   # nn.AdaptiveAvgPool2d((6, 6))
        if len(self.classifier) == 1 and isinstance(self.classifier[0], nn.Identity):
            self.classifier = _model.classifier

        # nn.Sequential(
        #     nn.Conv2d(3, 64, kernel_size=11, stride=4, padding=2),
        #     nn.ReLU(inplace=True),
        #     nn.MaxPool2d(kernel_size=3, stride=2),
        #     nn.Conv2d(64, 192, kernel_size=5, padding=2),
        #     nn.ReLU(inplace=True),
        #     nn.MaxPool2d(kernel_size=3, stride=2),
        #     nn.Conv2d(192, 384, kernel_size=3, padding=1),
        #     nn.ReLU(inplace=True),
        #     nn.Conv2d(384, 256, kernel_size=3, padding=1),
        #     nn.ReLU(inplace=True),
        #     nn.Conv2d(256, 256, kernel_size=3, padding=1),
        #     nn.ReLU(inplace=True),
        #     nn.MaxPool2d(kernel_size=3, stride=2),
        # )

        # nn.Sequential(
        #     nn.Dropout(),
        #     nn.Linear(256 * 6 * 6, 4096),
        #     nn.ReLU(inplace=True),
        #     nn.Dropout(),
        #     nn.Linear(4096, 4096),
        #     nn.ReLU(inplace=True),
        #     nn.Linear(4096, num_classes),
        # )


class AlexNet(ImageModel):

    def __init__(self, name: str = 'alexnet', model_class: type[_AlexNet] = _AlexNet, **kwargs):
        super().__init__(name=name, model_class=model_class, **kwargs)

    def get_official_weights(self, **kwargs) -> OrderedDict[str, torch.Tensor]:
        url = model_urls['resnet' + str(self.layer)]
        print('get official model weights from: ', url)
        return model_zoo.load_url(url, **kwargs)
