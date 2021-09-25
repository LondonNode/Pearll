from typing import Iterator, Optional, Type, Union

import torch as T
from torch.nn.parameter import Parameter

from anvil.common.type_aliases import CriticUpdaterLog
from anvil.models.actor_critics import ActorCritic, Critic


class BaseCriticUpdater(object):
    """
    The base class with pre-defined methods for derived classes

    :param optimizer_class: the type of optimizer to use, defaults to Adam
    :param lr: the learning rate for the optimizer algorithm
    :param max_grad: maximum gradient clip value, defaults to no clipping with a value of 0
    """

    def __init__(
        self,
        optimizer_class: Type[T.optim.Optimizer] = T.optim.Adam,
        lr: float = 1e-3,
        max_grad: float = 0,
    ) -> None:
        self.optimizer_class = optimizer_class
        self.lr = lr
        self.max_grad = max_grad

    def _get_model_parameters(
        self, model: Union[Critic, ActorCritic]
    ) -> Iterator[Parameter]:
        """Get the critic model parameters"""
        if isinstance(model, Critic):
            return model.parameters()
        else:
            return model.critic.parameters()

    def run_optimizer(
        self,
        optimizer: T.optim.Optimizer,
        loss: T.Tensor,
        critic_parameters: Iterator[Parameter],
    ) -> None:
        """Run an optimization step"""
        optimizer.zero_grad()
        loss.backward()
        if self.max_grad > 0:
            T.nn.utils.clip_grad_norm_(critic_parameters, self.max_grad)
        optimizer.step()


class ValueRegression(BaseCriticUpdater):
    """
    Regression for a value function estimator

    :param loss_class: the distance loss class for regression, defaults to MSE
    :param optimizer_class: the type of optimizer to use, defaults to Adam
    :param lr: the learning rate for the optimizer algorithm
    :param max_grad: maximum gradient clip value, defaults to no clipping with a value of 0
    """

    def __init__(
        self,
        loss_class: T.nn.Module = T.nn.MSELoss(),
        optimizer_class: Type[T.optim.Optimizer] = T.optim.Adam,
        lr: float = 0.001,
        max_grad: float = 0,
    ) -> None:
        super().__init__(optimizer_class=optimizer_class, lr=lr, max_grad=max_grad)
        self.loss_class = loss_class

    def __call__(
        self,
        model: Union[Critic, ActorCritic],
        observations: T.Tensor,
        returns: T.Tensor,
    ) -> CriticUpdaterLog:
        """
        Perform an optimization step

        :param model: the model on which the optimization should be run
        :param observations: observation inputs
        :param returns: the target to regress to (e.g. TD Values, Monte-Carlo Values)
        """
        critic_parameters = self._get_model_parameters(model)
        optimizer = self.optimizer_class(critic_parameters, lr=self.lr)

        if isinstance(model, Critic):
            values = model(observations)
        else:
            values = model.forward_critic(observations)

        loss = self.loss_class(values, returns)

        self.run_optimizer(optimizer, loss, critic_parameters)

        return CriticUpdaterLog(loss=loss.detach())


class QRegression(BaseCriticUpdater):
    """
    Regression for a Q function estimator

    :param loss_class: the distance loss class for regression, defaults to MSE
    :param optimizer_class: the type of optimizer to use, defaults to Adam
    :param lr: the learning rate for the optimizer algorithm
    :param max_grad: maximum gradient clip value, defaults to no clipping with a value of 0
    """

    def __init__(
        self,
        loss_class: T.nn.Module = T.nn.MSELoss(),
        optimizer_class: Type[T.optim.Optimizer] = T.optim.Adam,
        lr: float = 0.001,
        max_grad: float = 0,
    ) -> None:
        super().__init__(optimizer_class=optimizer_class, lr=lr, max_grad=max_grad)
        self.loss_class = loss_class

    def __call__(
        self,
        model: Union[Critic, ActorCritic],
        observations: T.Tensor,
        returns: T.Tensor,
        actions: Optional[T.Tensor] = None,
    ) -> CriticUpdaterLog:
        """
        Perform an optimization step

        :param model: the model on which the optimization should be run
        :param observations: observation inputs
        :param returns: the target to regress to (e.g. TD Values, Monte-Carlo Values)
        :param actions: optional action inputs, defaults to None, needed for continuous Q function modelling
        """
        critic_parameters = self._get_model_parameters(model)
        optimizer = self.optimizer_class(critic_parameters, lr=self.lr)

        if isinstance(model, Critic):
            values = model(observations, actions)
        else:
            values = model.forward_critic(observations, actions)

        loss = self.loss_class(values, returns)

        self.run_optimizer(optimizer, loss, critic_parameters)

        return CriticUpdaterLog(loss=loss.detach())
