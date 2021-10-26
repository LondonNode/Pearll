import enum
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pytest
import torch as T
from gym import GoalEnv, spaces
from gym.envs.registration import EnvSpec

from anvil.buffers import HERBuffer
from anvil.common.type_aliases import Trajectories


class BitFlippingEnv(GoalEnv):
    """
    Simple bit flipping env, useful to test HER.
    The goal is to flip all the bits to get a vector of ones.
    In the continuous variant, if the ith action component has a value > 0,
    then the ith bit will be flipped.
    :param n_bits: Number of bits to flip
    :param continuous: Whether to use the continuous actions version or not,
        by default, it uses the discrete one
    :param max_steps: Max number of steps, by default, equal to n_bits
    :param discrete_obs_space: Whether to use the discrete observation
        version or not, by default, it uses the ``MultiBinary`` one
    :param image_obs_space: Use image as input instead of the ``MultiBinary`` one.
    :param channel_first: Whether to use channel-first or last image.
    """

    spec = EnvSpec("BitFlippingEnv-v0")

    def __init__(
        self,
        n_bits: int = 10,
        continuous: bool = False,
        max_steps: Optional[int] = None,
        discrete_obs_space: bool = False,
        image_obs_space: bool = False,
        channel_first: bool = True,
    ):
        super(BitFlippingEnv, self).__init__()
        # Shape of the observation when using image space
        self.image_shape = (1, 36, 36) if channel_first else (36, 36, 1)
        # The achieved goal is determined by the current state
        # here, it is a special where they are equal
        if discrete_obs_space:
            # In the discrete case, the agent act on the binary
            # representation of the observation
            self.observation_space = spaces.Dict(
                {
                    "observation": spaces.Discrete(2 ** n_bits),
                    "achieved_goal": spaces.Discrete(2 ** n_bits),
                    "desired_goal": spaces.Discrete(2 ** n_bits),
                }
            )
        elif image_obs_space:
            # When using image as input,
            # one image contains the bits 0 -> 0, 1 -> 255
            # and the rest is filled with zeros
            self.observation_space = spaces.Dict(
                {
                    "observation": spaces.Box(
                        low=0,
                        high=255,
                        shape=self.image_shape,
                        dtype=np.uint8,
                    ),
                    "achieved_goal": spaces.Box(
                        low=0,
                        high=255,
                        shape=self.image_shape,
                        dtype=np.uint8,
                    ),
                    "desired_goal": spaces.Box(
                        low=0,
                        high=255,
                        shape=self.image_shape,
                        dtype=np.uint8,
                    ),
                }
            )
        else:
            self.observation_space = spaces.Dict(
                {
                    "observation": spaces.MultiBinary(n_bits),
                    "achieved_goal": spaces.MultiBinary(n_bits),
                    "desired_goal": spaces.MultiBinary(n_bits),
                }
            )

        self.obs_space = spaces.MultiBinary(n_bits)

        if continuous:
            self.action_space = spaces.Box(-1, 1, shape=(n_bits,), dtype=np.float32)
        else:
            self.action_space = spaces.Discrete(n_bits)
        self.continuous = continuous
        self.discrete_obs_space = discrete_obs_space
        self.image_obs_space = image_obs_space
        self.state = None
        self.desired_goal = np.ones((n_bits,))
        if max_steps is None:
            max_steps = n_bits
        self.max_steps = max_steps
        self.current_step = 0

    def seed(self, seed: int) -> None:
        self.obs_space.seed(seed)

    def convert_if_needed(self, state: np.ndarray) -> Union[int, np.ndarray]:
        """
        Convert to discrete space if needed.
        :param state:
        :return:
        """
        if self.discrete_obs_space:
            # The internal state is the binary representation of the
            # observed one
            return int(sum([state[i] * 2 ** i for i in range(len(state))]))

        if self.image_obs_space:
            size = np.prod(self.image_shape)
            image = np.concatenate(
                (state * 255, np.zeros(size - len(state), dtype=np.uint8))
            )
            return image.reshape(self.image_shape).astype(np.uint8)
        return state

    def convert_to_bit_vector(
        self, state: Union[int, np.ndarray], batch_size: int
    ) -> np.ndarray:
        """
        Convert to bit vector if needed.
        :param state:
        :param batch_size:
        :return:
        """
        # Convert back to bit vector
        if isinstance(state, int):
            state = np.array(state).reshape(batch_size, -1)
            # Convert to binary representation
            state = (((state[:, :] & (1 << np.arange(len(self.state))))) > 0).astype(
                int
            )
        elif self.image_obs_space:
            state = state.reshape(batch_size, -1)[:, : len(self.state)] / 255
        else:
            state = np.array(state).reshape(batch_size, -1)

        return state

    def _get_obs(self) -> Dict[str, Union[int, np.ndarray]]:
        """
        Helper to create the observation.
        :return: The current observation.
        """
        return OrderedDict(
            [
                ("observation", self.convert_if_needed(self.state.copy())),
                ("achieved_goal", self.convert_if_needed(self.state.copy())),
                ("desired_goal", self.convert_if_needed(self.desired_goal.copy())),
            ]
        )

    def reset(self) -> Dict[str, Union[int, np.ndarray]]:
        self.current_step = 0
        self.state = self.obs_space.sample()
        return self._get_obs()

    def step(self, action: Union[np.ndarray, int]) -> Tuple:
        if self.continuous:
            self.state[action > 0] = 1 - self.state[action > 0]
        else:
            self.state[action] = 1 - self.state[action]
        obs = self._get_obs()
        reward = float(
            self.compute_reward(obs["achieved_goal"], obs["desired_goal"], None)
        )
        done = reward == 0
        self.current_step += 1
        # Episode terminate when we reached the goal or the max number of steps
        info = {"is_success": done}
        done = done or self.current_step >= self.max_steps
        return obs, reward, done, info

    def compute_reward(
        self,
        achieved_goal: Union[int, np.ndarray],
        desired_goal: Union[int, np.ndarray],
        _info: Optional[Dict[str, Any]],
    ) -> np.float32:
        # As we are using a vectorized version, we need to keep track of the `batch_size`
        if isinstance(achieved_goal, int):
            batch_size = 1
        elif self.image_obs_space:
            batch_size = achieved_goal.shape[0] if len(achieved_goal.shape) > 3 else 1
        else:
            batch_size = achieved_goal.shape[0] if len(achieved_goal.shape) > 1 else 1

        desired_goal = self.convert_to_bit_vector(desired_goal, batch_size)
        achieved_goal = self.convert_to_bit_vector(achieved_goal, batch_size)

        # Deceptive reward: it is positive only when the goal is achieved
        # Here we are using a vectorized version
        distance = np.linalg.norm(achieved_goal - desired_goal, axis=-1)
        return -(distance > 0).astype(np.float32)

    def render(self, mode: str = "human") -> Optional[np.ndarray]:
        if mode == "rgb_array":
            return self.state.copy()
        print(self.state)

    def close(self) -> None:
        pass


NUM_BITS = 5
env = BitFlippingEnv(NUM_BITS)


def test_her_init():
    BUFFER_SIZE = int(1e6)
    buffer = HERBuffer(
        env=env,
        buffer_size=BUFFER_SIZE,
        observation_space=env.observation_space,
        action_space=env.action_space,
        goal_selection_strategy="final",
    )

    assert buffer.observations.shape == (BUFFER_SIZE, 1, NUM_BITS)
    assert buffer.actions.shape == (BUFFER_SIZE, 1, 1)
    assert buffer.rewards.shape == (BUFFER_SIZE, 1, 1)
    assert buffer.dones.shape == (BUFFER_SIZE, 1, 1)
    assert buffer.desired_goals.shape == (BUFFER_SIZE, 1, NUM_BITS)
    assert buffer.next_achieved_goals.shape == (BUFFER_SIZE, 1, NUM_BITS)


def test_her_add_trajectory():
    buffer = HERBuffer(
        env=env,
        buffer_size=2,
        observation_space=env.observation_space,
        action_space=env.action_space,
        goal_selection_strategy="final",
    )

    observation = env.reset()
    action = env.action_space.sample()
    next_obs, reward, done, _ = env.step(action)

    buffer.add_trajectory(observation, action, reward, next_obs, done)

    np.testing.assert_array_equal(buffer.observations[0][0], observation["observation"])
    np.testing.assert_array_equal(buffer.observations[1][0], next_obs["observation"])
    assert buffer.actions[0][0] == action
    assert buffer.rewards[0][0] == reward
    assert buffer.dones[0][0] == done
    np.testing.assert_array_equal(buffer.desired_goals[0][0], env.desired_goal)
    np.testing.assert_array_equal(
        buffer.next_achieved_goals[0][0], next_obs["achieved_goal"]
    )


@pytest.mark.parametrize("goal_selection_strategy", ["final", "future"])
@pytest.mark.parametrize("buffer_size", [15, 4])
def test_her_sample(goal_selection_strategy, buffer_size):
    NUM_EPISODES = 2
    OBSERVATION_BUFFER_SIZE = 15
    buffer = HERBuffer(
        env=env,
        buffer_size=buffer_size,
        observation_space=env.observation_space,
        action_space=env.action_space,
        goal_selection_strategy=goal_selection_strategy,
        n_sampled_goal=1,
    )
    # HER final goals
    her_goals = np.zeros((NUM_EPISODES, NUM_BITS))
    observations = np.zeros((OBSERVATION_BUFFER_SIZE, NUM_BITS))
    next_observations = np.zeros((OBSERVATION_BUFFER_SIZE, NUM_BITS))

    episode = 0
    pos = 0
    obs = env.reset()
    while episode != NUM_EPISODES:
        action = env.action_space.sample()
        next_obs, reward, done, _ = env.step(action)
        buffer.add_trajectory(obs, action, reward, next_obs, done)
        observations[pos] = obs["observation"]
        next_observations[pos] = next_obs["observation"]
        obs = next_obs
        pos += 1

        if done:
            her_goals[episode] = next_obs["achieved_goal"]
            episode += 1
            obs = env.reset()
    observations[pos] = next_observations[pos - 1]

    trajectories = buffer.sample(4)
    sampled_observations = trajectories.observations.reshape(4, NUM_BITS * 2)[
        :, :NUM_BITS
    ]
    sampled_next_observations = trajectories.next_observations.reshape(4, NUM_BITS * 2)[
        :, :NUM_BITS
    ]
    her_sampled_goals = trajectories.observations.reshape(4, NUM_BITS * 2)[:, NUM_BITS:]
    # Check if sampled next observations are actually the next observations
    for i, obs in enumerate(sampled_observations):
        array_idx = np.where(observations == obs)[0]
        possible_next_obs = next_observations[array_idx]
        assert sampled_next_observations[i] in possible_next_obs
    # Check if sampled goals are correct
    if goal_selection_strategy == "final":
        for goal in her_sampled_goals:
            assert goal in her_goals


@pytest.mark.parametrize("goal_selection_strategy", ["final", "future"])
def test_her_last(goal_selection_strategy):
    NUM_EPISODES = 2
    OBSERVATION_BUFFER_SIZE = 15
    buffer = HERBuffer(
        env=env,
        buffer_size=15,
        observation_space=env.observation_space,
        action_space=env.action_space,
        goal_selection_strategy=goal_selection_strategy,
        n_sampled_goal=1,
    )
    observations = np.zeros((OBSERVATION_BUFFER_SIZE, 1, NUM_BITS))
    next_observations = np.zeros((OBSERVATION_BUFFER_SIZE, 1, NUM_BITS))
    actions = np.zeros((OBSERVATION_BUFFER_SIZE, 1, 1))
    dones = np.zeros((OBSERVATION_BUFFER_SIZE, 1, 1))

    episode = 0
    pos = 0
    last_episode_pos = 0
    obs = env.reset()
    while episode != NUM_EPISODES:
        action = env.action_space.sample()
        next_obs, reward, done, _ = env.step(action)
        buffer.add_trajectory(obs, action, reward, next_obs, done)
        observations[pos] = obs["observation"]
        next_observations[pos] = next_obs["observation"]
        actions[pos] = action
        dones[pos] = done
        obs = next_obs
        pos += 1

        if done:
            last_episode_pos = pos - 1
            episode += 1
            obs = env.reset()

    most_recent = buffer.last(batch_size=2)

    # Don't assert rewards since these can change with HER sampled goals
    np.testing.assert_array_almost_equal(
        most_recent.observations[:, :, :NUM_BITS],
        observations[last_episode_pos - 1 : last_episode_pos + 1],
    )
    np.testing.assert_array_almost_equal(
        most_recent.actions, actions[last_episode_pos - 1 : last_episode_pos + 1]
    )
    np.testing.assert_array_almost_equal(
        most_recent.next_observations[:, :, :NUM_BITS],
        next_observations[last_episode_pos - 1 : last_episode_pos + 1],
    )
    np.testing.assert_array_almost_equal(
        most_recent.dones, dones[last_episode_pos - 1 : last_episode_pos + 1]
    )
    # Make sure we got the right number of samples
    assert len(most_recent.dones) == 2
