from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
import os

import ray

from reinforce.env import BatchedEnv
from reinforce.policy import ProximalPolicyLoss
from reinforce.filter import MeanStdFilter
from reinforce.rollout import rollouts, add_advantage_values


class Agent(object):
  def __init__(self, name, batchsize, preprocessor, config, use_gpu):
    if not use_gpu:
      os.environ["CUDA_VISIBLE_DEVICES"] = ""
    self.env = BatchedEnv(name, batchsize, preprocessor=preprocessor)
    if preprocessor.shape is None:
      preprocessor.shape = self.env.observation_space.shape
    self.sess = tf.Session()
    with tf.name_scope("policy_gradient/train"):
      with tf.name_scope("proximal_policy_loss"):
        self.ppo = ProximalPolicyLoss(self.env.observation_space,
                                      self.env.action_space, preprocessor,
                                      config, self.sess)
      with tf.name_scope("adam_optimizer"):
        self.optimizer = tf.train.AdamOptimizer(config["sgd_stepsize"])
        self.train_op = self.optimizer.minimize(self.ppo.loss)
      self.variables = ray.experimental.TensorFlowVariables(self.ppo.loss,
                                                            self.sess)
      self.observation_filter = MeanStdFilter(preprocessor.shape, clip=None)
      self.reward_filter = MeanStdFilter((), clip=5.0)
    self.sess.run(tf.global_variables_initializer())

  def get_weights(self):
    return self.variables.get_weights()

  def load_weights(self, weights):
    self.variables.set_weights(weights)

  def compute_trajectory(self, gamma, lam, horizon):
    trajectory = rollouts(self.ppo, self.env, horizon, self.observation_filter,
                          self.reward_filter)
    add_advantage_values(trajectory, gamma, lam, self.reward_filter)
    return trajectory


RemoteAgent = ray.remote(Agent)
