from .badnet import BadNet

from trojanzoo.attack.adv import PGD
from trojanzoo.optim import PGD as PGD_Optimizer
from trojanzoo.utils.model import weight_init
from trojanzoo.utils.data import MyDataset

import torch
import torchvision
import torch.nn as nn
import torch.optim as optim

import os
import numpy as numpy
from typing import List


from trojanzoo.utils.config import Config
env = Config.env


class Clean_Label(BadNet):
    r"""
    Contributor: Xiangshan Gao, Ren Pang

    Clean Label Backdoor Attack is described in detail in the paper `Clean Label Backdoor Attack`_ by Alexander Turner.

    The main idea is to perturb the poisoned samples in order to render learning the salient characteristic of the input more difficult,causing the model rely more heavily on the backdoor pattern in order to successfully introduce backdoor. Utilize the adversarial examples and GAB generated data, the resulted poisoned inputs appear to be consistent with their label and thus seem benign even upon human inspection.

    The authors haven't posted `original source code`_.

    Args:
        preprocess_layer (str): the chosen layer used to generate adversarial example. Default: 'classifier'.
        poison_generation_method (str): the chosen method to generate poisoned sample. Default: 'pgd'.
        tau (float): the interpolation constant used to balance source imgs and target imgs. Default: 0.4.
        epsilon (float): the perturbation bound in input space. Default: 0.1.
        noise_dim (int): the dimension of the input in the generator. Default: 100.
        generator_iters (int): the epoch for training the generator. Default: 1000.
        critic_iter (int): the critic iterations per generator training iteration. Default: 5.


    .. _Clean Label:
        https://people.csail.mit.edu/madry/lab/cleanlabel.pdf

    .. _related code:
        https://github.com/igul222/improved_wgan_training
        https://github.com/MadryLab/cifar10_challenge
        https://github.com/caogang/wgan-gp

    """
    name: str = 'clean_label'

    def __init__(self, preprocess_layer: str = 'classifier', poison_generation_method: str = 'pgd',
                 pgd_alpha: float = 2 / 255, pgd_epsilon: float = 16 / 255, pgd_iteration=20,
                 tau: float = 0.2, noise_dim: int = 100,
                 train_gan: bool = False, generator_iters: int = 1000, critic_iter: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.param_list['clean_label'] = ['preprocess_layer', 'poison_generation_method', 'poison_num']
        self.preprocess_layer: str = preprocess_layer
        self.poison_generation_method: str = poison_generation_method
        self.poison_num: int = int(len(self.dataset.get_dataset('train')) * self.percent)

        data_shape = [self.dataset.n_channel]
        data_shape.extend(self.dataset.n_dim)
        self.data_shape: List[int] = data_shape
        if poison_generation_method == 'pgd':
            self.param_list['pgd'] = ['pgd_alpha', 'pgd_epsilon', 'pgd_iteration']
            self.pgd_alpha: float = pgd_alpha
            self.pgd_epsilon: float = pgd_epsilon
            self.pgd_iteration: int = pgd_iteration
            self.pgd: PGD = PGD(alpha=pgd_alpha, epsilon=pgd_epsilon, iteration=pgd_iteration,
                                target_idx=0, output=self.output, dataset=self.dataset, model=self.model)
        elif poison_generation_method == 'gan':
            self.param_list['gan'] = ['tau', 'noise_dim', 'train_gan', 'critic_iter', 'generator_iters']
            self.tau: float = tau
            self.noise_dim: int = noise_dim
            self.train_gan: bool = train_gan
            self.generator_iters = generator_iters
            self.critic_iter = critic_iter
            self.wgan = WGAN(noise_dim=self.noise_dim, dim=64, data_shape=self.data_shape,
                             generator_iters=self.generator_iters, critic_iter=self.critic_iter)

    def attack(self, optimizer: torch.optim.Optimizer, lr_scheduler: torch.optim.lr_scheduler._LRScheduler, **kwargs):

        target_class_dataset = self.dataset.get_dataset('train', full=True, classes=[self.target_class])

        sample_target_class_dataset, target_original_dataset = self.dataset.split_set(
            target_class_dataset, self.poison_num)
        sample_target_dataloader = self.dataset.get_dataloader(mode='train', dataset=sample_target_class_dataset,
                                                               batch_size=self.poison_num, num_workers=0)
        target_imgs, _ = self.model.get_data(next(iter(sample_target_dataloader)))

        full_set = self.dataset.get_dataset('train', full=True)
        if self.poison_generation_method == 'pgd':
            poison_label = self.target_class * torch.ones(len(target_imgs), dtype=torch.long, device=target_imgs.device)

            poison_imgs, _ = self.model.remove_misclassify(data=(target_imgs, poison_label))
            poison_imgs, _ = self.pgd.craft_example(_input=poison_imgs)
            poison_imgs = self.add_mark(poison_imgs).cpu()

            poison_label = [self.target_class] * len(target_imgs)
            poison_set = MyDataset(poison_imgs, poison_label)
            # poison_set = torch.utils.data.ConcatDataset([poison_set, target_original_dataset])

        elif self.poison_generation_method == 'gan':
            other_classes = list(range(self.dataset.num_classes))
            other_classes.pop(self.target_class)
            x_list = []
            y_list = []
            for source_class in other_classes:
                source_class_dataset = self.dataset.get_dataset(mode='train', full=True, classes=[source_class])
                sample_source_class_dataset, _ = self.dataset.split_set(
                    source_class_dataset, self.poison_num)
                sample_source_class_dataloader = self.dataset.get_dataloader(mode='train', dataset=sample_source_class_dataset,
                                                                             batch_size=self.poison_num, num_workers=0)
                source_imgs, _ = self.model.get_data(next(iter(sample_source_class_dataloader)))

                g_path = f'{self.folder_path}gan_dim{self.noise_dim}_class{source_class}_g.pth'
                d_path = f'{self.folder_path}gan_dim{self.noise_dim}_class{source_class}_d.pth'
                if os.path.exists(g_path) and os.path.exists(d_path) and not self.train_gan:
                    self.wgan.G.load_state_dict(torch.load(g_path, map_location=env['device']))
                    self.wgan.D.load_state_dict(torch.load(d_path, map_location=env['device']))
                else:
                    self.train_gan = True
                    self.wgan.reset_parameters()
                    gan_dataset = torch.utils.data.ConcatDataset([source_class_dataset, target_class_dataset])
                    gan_dataloader = self.dataset.get_dataloader(
                        mode='train', dataset=gan_dataset, batch_size=self.dataset.batch_size, num_workers=0)
                    self.wgan.train(gan_dataloader)
                    torch.save(self.wgan.G.state_dict(), g_path)
                    torch.save(self.wgan.D.state_dict(), d_path)
                    print(f'GAN Model Saved at : \n{g_path}\n{d_path}')
                    continue
                source_encode = self.wgan.get_encode_value(source_imgs, self.poison_num).detach()
                target_encode = self.wgan.get_encode_value(target_imgs, self.poison_num).detach()
                # noise = torch.randn_like(source_encode)
                # from trojanzoo.utils.tensor import save_tensor_as_img
                # source_img = self.wgan.G(source_encode)
                # target_img = self.wgan.G(target_encode)
                # for i in range(len(source_img)):
                #     save_tensor_as_img(f'./imgs/source_{i}.png', source_img[i])
                # for i in range(len(target_img)):
                #     save_tensor_as_img(f'./imgs/target_{i}.png', target_img[i])
                # exit()
                interpolation_encode = source_encode * self.tau + target_encode * (1 - self.tau)
                poison_imgs = self.wgan.G(interpolation_encode).detach()
                poison_imgs = self.add_mark(poison_imgs)

                poison_label = [self.target_class] * len(poison_imgs)
                poison_imgs = poison_imgs.cpu()
                x_list.append(poison_imgs)
                y_list.extend(poison_label)
            if self.train_gan:
                exit()
            x_list = torch.cat(x_list)
            poison_set = MyDataset(x_list, y_list)
            # poison_set = torch.utils.data.ConcatDataset([poison_set, target_original_dataset])

        # all_classes = list(range(self.dataset.num_classes))
        # all_classes.pop(self.target_class)
        # original_set = self.dataset.get_dataset(mode='train', full=True, classes=[all_classes])
        # final_set = torch.utils.data.ConcatDataset([poison_set, original_set])
        final_set = torch.utils.data.ConcatDataset([poison_set, full_set])
        final_loader = self.dataset.get_dataloader(mode='train', dataset=final_set, num_workers=0)
        self.model._train(optimizer=optimizer, lr_scheduler=lr_scheduler, save_fn=self.save,
                          loader_train=final_loader, validate_func=self.validate_func, **kwargs)


class Generator(nn.Module):
    def __init__(self, noise_dim: int = 100, dim: int = 64, data_shape: List[int] = [3, 32, 32]):
        super().__init__()
        self.noise_dim: int = noise_dim
        self.dim: int = dim
        self.data_shape: List[int] = data_shape
        init_dim = dim * data_shape[1] * data_shape[2] // 16
        self.preprocess = nn.Linear(noise_dim, init_dim)
        self.preprocess_1 = nn.Sequential(
            nn.BatchNorm2d(init_dim),
            nn.ReLU(True),)
        self.block1 = nn.Sequential(
            nn.ConvTranspose2d(4 * dim, 2 * dim, 2, stride=2),
            nn.BatchNorm2d(2 * dim),
            nn.ReLU(True),)
        self.block2 = nn.Sequential(
            nn.ConvTranspose2d(2 * dim, dim, 2, stride=2),
            nn.BatchNorm2d(dim),
            nn.ReLU(True),)
        self.deconv_out = nn.ConvTranspose2d(dim, data_shape[0], 2, stride=2)
        self.tanh = nn.Tanh()

    def forward(self, x: torch.Tensor):
        # (N, noise_dim)
        x = self.preprocess(x)
        # (N, noise_dim)
        x = x.unsqueeze(-1).unsqueeze(-1)
        x = self.preprocess_1(x)
        x = x.view(len(x), 4 * self.dim, self.data_shape[1] // 8, self.data_shape[2] // 8)
        x = self.block1(x)
        x = self.block2(x)
        x = self.deconv_out(x)
        x = self.tanh(x)
        return x


class Discriminator(nn.Module):
    def __init__(self, dim: int = 64, data_shape: list = [3, 32, 32]):
        super(Discriminator, self).__init__()
        self.dim = dim
        self.main = nn.Sequential(
            nn.Conv2d(data_shape[0], dim, 3, 2, padding=1),
            nn.LeakyReLU(),
            nn.Conv2d(dim, 2 * dim, 3, 2, padding=1),
            nn.BatchNorm2d(2 * dim),
            nn.LeakyReLU(),
            nn.Conv2d(2 * dim, 4 * dim, 3, 2, padding=1),
            nn.BatchNorm2d(4 * dim),
            nn.LeakyReLU(),
        )
        init_dim = dim * data_shape[1] * data_shape[2] // 16
        self.linear = nn.Linear(init_dim, 1)

    def forward(self, x: torch.Tensor):
        x = self.main(x)
        x = x.flatten(start_dim=1)
        x = self.linear(x)
        return x


class WGAN(object):
    def __init__(self, noise_dim: int, dim: int, data_shape: List[int] = [3, 32, 32],
                 generator_iters: int = 1000, critic_iter: int = 5):
        self.noise_dim = noise_dim
        self.G: Generator = Generator(noise_dim, dim, data_shape)
        self.D: Discriminator = Discriminator(dim, data_shape)
        if env['num_gpus']:
            self.G.cuda()
            self.D.cuda()
        # the parameter in the original paper
        self.d_optimizer = optim.RMSprop(self.D.parameters(), lr=5e-5)
        self.g_optimizer = optim.RMSprop(self.G.parameters(), lr=5e-5)
        self.generator_iters = generator_iters  # larger: 1000
        self.critic_iter = critic_iter
        self.mse_loss = torch.nn.MSELoss()

        self.gan_pgd: PGD = PGD_Optimizer(epsilon=1.0, iteration=500, output=0)

    def reset_parameters(self):
        self.G.apply(weight_init)
        self.D.apply(weight_init)

    def train(self, train_dataloader):
        self.g_optimizer.zero_grad()
        self.d_optimizer.zero_grad()
        for g_iter in range(self.generator_iters):
            # Requires grad, Generator requires_grad = False
            for p in self.D.parameters():
                p.requires_grad = True
                p.data.clamp_(-0.01, 0.01)
            for p in self.G.parameters():
                p.requires_grad = False

            for d_iter in range(self.critic_iter):
                for i, (data, label) in enumerate(train_dataloader):
                    data = torch.tensor(data)
                    train_data = data.to(env['device'])
                    d_loss_real = self.D(train_data).mean()

                    z = torch.randn(train_data.shape[0], self.noise_dim, device=train_data.device)
                    fake_images = self.G(z)
                    d_loss_fake = self.D(fake_images).mean()

                    d_loss = d_loss_fake - d_loss_real
                    d_loss.backward()
                    self.d_optimizer.step()
                    self.d_optimizer.zero_grad()
                print(f'    Discriminator: loss_fake: {d_loss_fake:.5f}, loss_real: {d_loss_real:.5f}')
            for p in self.D.parameters():
                p.requires_grad = False
            for p in self.G.parameters():
                p.requires_grad = True
            for i, (data, label) in enumerate(train_dataloader):
                data = torch.tensor(data)
                train_data = data.to(env['device'])
                z = torch.randn(train_data.shape[0], self.noise_dim, device=train_data.device)
                fake_images = self.G(z)
                g_loss = - self.D(fake_images).mean()
                g_loss.backward()
                self.g_optimizer.step()
                self.g_optimizer.zero_grad()
            print(f'Generator iteration: {g_iter:5d} / {self.generator_iters:5d}, g_loss: {g_loss:.5f}')

    def get_encode_value(self, imgs: torch.Tensor, poison_num: int):
        """According to the image and Generator, utilize pgd optimization to get the d dimension encoding value.

        Args:
            imgs (torch.FloatTensor): the chosen image to get its encoding value, also considered as the output of Generator.
            poison_num (int): the amount of chosen target class image.
            noise_dim (int): the dimension of the input in the generator.

        Returns:
            torch.FloatTensor: the synthesized poisoned image.
        """

        def loss_func(X: torch.Tensor):
            loss = self.mse_loss(self.G(X), imgs)
            return loss
        x_1 = torch.randn(poison_num, self.noise_dim, device=imgs.device)
        x_1, _ = self.gan_pgd.optimize(_input=x_1, loss_fn=loss_func)
        return x_1
