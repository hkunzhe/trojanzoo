#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from .output import ansi
from .param import Param
from .miscellaneous import get_name
from trojanzoo.configs import Config, config

import torch
import torch.cuda
# import torch.distributed as dist
import torch.backends.cudnn
import numpy as np
import random
import argparse
from typing import Union


class Env(Param):

    @staticmethod
    def add_argument(group: argparse._ArgumentGroup):
        group.add_argument('--config', dest='config_path',
                           help='cmd config file path. (``package < project < cmd_config < cmd_param``)')

        group.add_argument('--seed', dest='seed', type=int,
                           help='the random seed for numpy, torch and cuda, defaults to config[env][seed]=1228')
        group.add_argument('--cache_threshold', dest='cache_threshold', type=float,
                           help='the threshold (MB) to call torch.cuda.empty_cache(), defaults to config[env][cache_threshold]=None (never).')

        group.add_argument('--device', dest='device',
                           help='set to \'cpu\' to force cpu-only and \'gpu\', \'cuda\' for gpu-only, defaults to None.')
        group.add_argument('--benchmark', dest='benchmark', action='store_true',
                           help='use torch.backends.cudnn.benchmark to accelerate without deterministic, defaults to False.')
        group.add_argument('--verbose', dest='verbose', type=int, default=0,
                           help='show arguments and module information, defaults to False.')
        group.add_argument('--color', dest='color', action='store_true',
                           help='Colorful Output, defaults to False.')
        group.add_argument('--tqdm', dest='tqdm', action='store_true',
                           help='Show tqdm Progress Bar, defaults to False.')

        # group.add_argument('--world_size', dest='world_size', type=int, default=1)
        return group


env = Env(default=None)


def add_argument(parser: argparse.ArgumentParser):
    group = parser.add_argument_group('{yellow}env{reset}'.format(**ansi))
    env.add_argument(group)
    return group


def create(config_path: str = None, dataset_name: str = None, dataset: str = None,
           seed: int = None, benchmark: bool = None,
           config: Config = config,
           cache_threshold: float = None, verbose: int = None,
           color: bool = None, tqdm: bool = None, **kwargs) -> Env:
    other_kwargs = {'cache_threshold': cache_threshold, 'verbose': verbose, 'color': color, 'tqdm': tqdm}
    config.update_cmd(config_path)
    dataset_name = get_name(name=dataset_name, module=dataset, arg_list=['-d', '--dataset'])
    dataset_name = dataset_name if dataset_name is not None else config.get_full_config()['dataset']['default_dataset']
    result = config.get_config(dataset_name=dataset_name)['env']._update(other_kwargs)
    env.update(config_path=config_path, **result)
    ansi.switch(env['color'])
    if seed is None and 'seed' in env.keys():
        seed = env['seed']
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    num_gpus: int = torch.cuda.device_count()
    device: Union[str, int] = result['device']
    if device == 'none':
        device = None
    else:
        if device is None or device == 'auto':
            device = 'cuda' if num_gpus else 'cpu'
        if isinstance(device, (str, int)):
            device = torch.device(device)
        if device.type == 'cpu':
            num_gpus = 0
        if device.index is not None and torch.cuda.is_available():
            num_gpus = 1
    if num_gpus == 0:
        device = torch.device('cpu')
    if benchmark is None and 'benchmark' in env.keys():
        benchmark = env['benchmark']
    if benchmark:
        torch.backends.cudnn.benchmark = benchmark

    # dist_backend = 'nccl' if num_gpus and dist.is_nccl_available() else 'gloo'
    # dist.init_process_group(backend=dist_backend)
    env.update(seed=seed, device=device, benchmark=benchmark, num_gpus=num_gpus)
    return env


# def init_distributed_mode():
