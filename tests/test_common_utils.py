import numpy as np
import pytest
import torch as T

from anvil.common.utils import numpy_to_torch, torch_to_numpy

numpy_data = (np.zeros(shape=(2, 2)), np.zeros(shape=(3, 3)))
torch_data = (T.zeros(2, 2), T.zeros(3, 3))
mixed_data = (np.zeros(shape=(2, 2)), T.zeros(3, 3))


@pytest.mark.parametrize("input", [numpy_data, torch_data, mixed_data])
def test_numpy_to_torch(input):
    actual_output = numpy_to_torch(*input)
    for i in range(len(actual_output)):
        assert T.equal(actual_output[i], torch_data[i])


@pytest.mark.parametrize("input", [numpy_data, torch_data, mixed_data])
def test_torch_to_numpy(input):
    actual_output = torch_to_numpy(*input)
    for i in range(len(actual_output)):
        np.testing.assert_array_equal(actual_output[i], numpy_data[i])