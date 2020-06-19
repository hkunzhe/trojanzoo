# -*- coding: utf-8 -*-

# python badnet.py --verbose --pretrain --validate_interval 1 --mark_ratio 0.3

from trojanzoo.parser import Parser_Dataset, Parser_Model, Parser_Train, Parser_Seq
from trojanzoo.parser import Parser_Mark
from trojanzoo.parser.attack import Parser_BadNet

from trojanzoo.dataset import ImageSet
from trojanzoo.model import ImageModel
from trojanzoo.attack import BadNet
from trojanzoo.utils.mark import Watermark

from trojanzoo.utils import save_tensor_as_img

import warnings
warnings.filterwarnings("ignore")

if __name__ == '__main__':
    parser = Parser_Seq(Parser_Dataset(), Parser_Model(), Parser_Train(),
                        Parser_Mark(), Parser_BadNet())
    parser.parse_args()
    parser.get_module()

    dataset: ImageSet = parser.module_list['dataset']
    model: ImageModel = parser.module_list['model']
    optimizer, lr_scheduler, train_args = parser.module_list['train']
    mark: Watermark = parser.module_list['mark']
    attack: BadNet = parser.module_list['attack']

    # ------------------------------------------------------------------------ #
    attack.attack(optimizer=optimizer, lr_scheduler=lr_scheduler, **train_args)
