import warnings
from enum import Enum
from typing import Tuple, Union

import numpy as np
import torch as T
from gym import spaces


class NetworkType(Enum):
    MLP = "mlp"
    PARAMETER = "parameter"


def get_device(device: Union[T.device, str]) -> T.device:
    """
    Retrieve PyTorch device.
    It checks that the requested device is available first.
    For now, it supports only cpu and cuda.

    :param device: One for 'auto', 'cuda', 'cpu'
    :return:
    """
    # Cuda by default
    if device == "auto":
        device = "cuda"
    # Force conversion to th.device
    device = T.device(device)

    # Cuda not available
    if device.type == T.device("cuda").type and not T.cuda.is_available():
        return T.device("cpu")

    return device


def get_mlp_size(data_shape: Union[int, Tuple[int]]) -> int:
    """
    Convert the shape of some data into an integer size that defines
    how many neurons to create in an MLP layer

    :param data_shape: the tuple shape or already converted integer size
    :return: the integer size
    """

    if isinstance(data_shape, tuple):
        data_shape = data_shape[0]
    return data_shape


def is_image_space_channels_first(observation_space: spaces.Box) -> bool:
    """
    Check if an image observation space (see ``is_image_space``)
    is channels-first (CxHxW, True) or channels-last (HxWxC, False).
    Use a heuristic that channel dimension is the smallest of the three.
    If second dimension is smallest, raise an exception (no support).
    :param observation_space:
    :return: True if observation space is channels-first image, False if channels-last.
    """
    smallest_dimension = np.argmin(observation_space.shape).item()
    if smallest_dimension == 1:
        warnings.warn(
            "Treating image space as channels-last, while second dimension was smallest of the three."
        )
    return smallest_dimension == 0


def is_image_space(
    observation_space: spaces.Space,
    check_channels: bool = False,
) -> bool:
    """
    Check if a observation space has the shape, limits and dtype
    of a valid image.
    The check is conservative, so that it returns False if there is a doubt.
    Valid images: RGB, RGBD, GrayScale with values in [0, 255]
    :param observation_space:
    :param check_channels: Whether to do or not the check for the number of channels.
        e.g., with frame-stacking, the observation space may have more channels than expected.
    :return:
    """
    if isinstance(observation_space, spaces.Box) and len(observation_space.shape) == 3:
        # Check the type
        if observation_space.dtype != np.uint8:
            return False

        # Check the value range
        if np.any(observation_space.low != 0) or np.any(observation_space.high != 255):
            return False

        # Skip channels check
        if not check_channels:
            return True
        # Check the number of channels
        if is_image_space_channels_first(observation_space):
            n_channels = observation_space.shape[0]
        else:
            n_channels = observation_space.shape[-1]
        # RGB, RGBD, GrayScale
        return n_channels in [1, 3, 4]
    return False
