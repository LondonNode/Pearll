import logging
from typing import Optional, Union

import numpy as np
from torch.utils.tensorboard import SummaryWriter

from anvilrl.common.type_aliases import Log


def get_logger(file_handler_level: int, stream_handler_level: int) -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler("agent.log", mode="w")
    file_handler.setLevel(file_handler_level)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(stream_handler_level)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


class Logger(object):
    """
    The Logger object combines the torch SummaryWriter with python in-built logging

    :param tensorboard_log_path: path to store the tensorboard log
    :param file_handler_level: logging level for the file log
    :param stream_handeler_level: logging level for the streaming log
    :param verbose: whether to display at all or not
    :param num_envs: number of environments to run, useful for multi-agent
    """

    def __init__(
        self,
        tensorboard_log_path: Optional[str] = None,
        file_handler_level: int = logging.DEBUG,
        stream_handler_level: int = logging.INFO,
        verbose: bool = True,
        num_envs: int = 1,
    ) -> None:
        self.writer = SummaryWriter(tensorboard_log_path)
        self.logger = get_logger(file_handler_level, stream_handler_level)
        self.verbose = verbose
        self.num_envs = num_envs
        self.episode_actor_losses = []
        self.episode_critic_losses = []
        self.episode_kl_divergences = []
        self.episode_entropies = []
        self.episode_rewards = []
        # Keep track of which environments have completed an episode
        self.episode_dones = np.array([False for _ in range(num_envs)])

    def reset_episode_log(self) -> None:
        self.episode_actor_losses = []
        self.episode_critic_losses = []
        self.episode_kl_divergences = []
        self.episode_entropies = []
        self.episode_rewards = []
        self.episode_dones = np.array([False for _ in range(self.num_envs)])

    def add_train_log(self, train_log: Log) -> None:
        if train_log.actor_loss is not None:
            self.episode_actor_losses.append(train_log.actor_loss)
        if train_log.critic_loss is not None:
            self.episode_critic_losses.append(train_log.critic_loss)
        if train_log.entropy is not None:
            self.episode_entropies.append(train_log.entropy)
        if train_log.kl_divergence is not None:
            self.episode_kl_divergences.append(train_log.kl_divergence)

    def add_reward(self, reward: Union[float, np.ndarray]) -> None:
        """Add step reward to the episode rewards"""
        if isinstance(reward, (float, np.floating)):
            self.episode_rewards.append(reward)
        elif isinstance(reward, np.ndarray):
            self.episode_rewards.append(
                reward[np.where(self.episode_dones == False)[0]]
            )
        else:
            raise TypeError(
                f"Reward must be a float or numpy array, got {type(reward)}"
            )

    def _make_episode_log(self) -> Log:
        """Make an episode log out of the collected stats"""
        episode_log = Log(
            reward=np.sum(self.episode_rewards),
        )
        if self.episode_actor_losses:
            episode_log.actor_loss = np.mean(self.episode_actor_losses)
        if self.episode_critic_losses:
            episode_log.critic_loss = np.mean(self.episode_critic_losses)
        if self.episode_kl_divergences:
            episode_log.kl_divergence = np.mean(self.episode_kl_divergences)
        if self.episode_entropies:
            episode_log.entropy = np.mean(self.episode_entropies)

        return episode_log

    def write_episode_log(self, step: int) -> None:
        """Write a log to tensorboard and python logging"""
        episode_log = self._make_episode_log()
        self.writer.add_scalar("Reward/episode_reward", episode_log.reward, step)
        self.writer.add_scalar("Loss/actor_loss", episode_log.actor_loss, step)
        self.writer.add_scalar("Loss/critic_loss", episode_log.critic_loss, step)
        if episode_log.kl_divergence is not None:
            self.writer.add_scalar(
                "Metrics/kl_divergence", episode_log.kl_divergence, step
            )
        if episode_log.entropy is not None:
            self.writer.add_scalar("Metrics/entropy", episode_log.entropy, step)

        if self.verbose:
            self.logger.info(f"{step}: {episode_log}")

    def info(self, msg: str):
        if self.verbose:
            self.logger.info(msg)

    def debug(self, msg: str):
        if self.verbose:
            self.logger.debug(msg)

    def warning(self, msg: str):
        if self.verbose:
            self.logger.warning(msg)

    def error(self, msg: str):
        if self.verbose:
            self.logger.error(msg)

    def exception(self, msg: str):
        if self.verbose:
            self.logger.exception(msg)