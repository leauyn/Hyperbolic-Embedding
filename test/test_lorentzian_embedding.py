"""
Tests for calculating lorentzian embeddings in the hyperboloid with tensorflow
"""
import sys
import os

sys.path.append(os.path.join('..', 'src', 'python'))

import utils
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from run_detectors import run_all_datasets
import numpy as np
import tensorflow as tf
import math


def minkowski_tensor_dot(u, v):
    """
    Minkowski dot product is the same as the Euclidean dot product, but the first element squared is subtracted
    :param u: a tensor of shape (#examples, dims)
    :param v: a tensor of shape (#examples, dims)
    :return: a scalar dot product
    """
    assert u.shape == v.shape, 'minkowski dot product not define for different shape tensors'
    try:
        temp = np.eye(u.shape[1])
    except IndentationError:
        temp = np.eye(u.shape)
    temp[0, 0] = -1.
    T = tf.constant(temp, dtype=u.dtype)
    # make the first column of v negative
    v_neg = tf.matmul(v, T)
    return tf.reduce_sum(tf.multiply(u, v_neg), 1, keep_dims=True)  # keep dims for broadcasting


def minkowski_vector_dot(u, v):
    """
        Minkowski dot product is the same as the Euclidean dot product, but the first element squared is subtracted
        :param u: a vector
        :param v: a vector
        :return: a scalar dot product
        """
    assert u.shape == v.shape, 'minkowski dot product not define for different shape vectors'
    # assert that the vectors have only 1d.
    # todo this currently fails because exp_map returns tensors with shape = None
    # assert u.get_shape().ndims == 1, 'applied minkowski_vector_dot to a tensor. Try using minkowski_tensor_dot'

    return tf.tensordot(u, v, 1) - 2 * tf.multiply(u[0], v[0])


def minkowski_dist(u, v):
    """
    The distance between two points in Minkowski space
    :param u:
    :param v:
    :return:
    """
    return tf.acosh(-minkowski_vector_dot(u, v))


def project_onto_tangent_space(hyperboloid_point, ambient_gradient):
    """
    project gradients in the ambiant space onto the tangent space
    :param hyperboloid_point: A point on the hyperboloid
    :param ambient_gradient: The gradient to project
    :return:
    """
    return ambient_gradient + minkowski_vector_dot(hyperboloid_point, ambient_gradient) * hyperboloid_point


def project_tensors_onto_tangent_space(hyperboloid_points, ambient_gradients):
    """
    project gradients in the ambiant space onto the tangent space
    :param hyperboloid_point: A point on the hyperboloid
    :param ambient_gradient: The gradient to project
    :return: gradients in the tangent spaces of the hyperboloid points
    """
    return ambient_gradients + tf.multiply(minkowski_tensor_dot(hyperboloid_points, ambient_gradients),
                                           hyperboloid_points)


def exp_map(base, tangent):
    """
    Map a vector 'tangent' from the tangent space at point 'base' onto the manifold.
    """
    norm = tf.sqrt(tf.maximum(minkowski_vector_dot(tangent, tangent), 0))
    if norm == 0:
        return base
    tangent /= norm
    return tf.cosh(norm) * base + tf.sinh(norm) * tangent


def tensor_exp_map(hyperboloid_points, tangent_grads):
    """
    Map vectors in the tangent space of the hyperboloid points back onto the hyperboloid
    :param hyperboloid_points: a tensor of points on the hyperboloid of shape (#examples, #dims)
    :param tangent_grads: a tensor of gradients on the tangent spaces of the hyperboloid_points of shape (#examples, #dims)
    :return:
    """
    # todo do we need to normalise the gradients?
    norms = tf.sqrt(tf.maximum(minkowski_tensor_dot(tangent_grads, tangent_grads), 0))
    zero = tf.constant(0, dtype=tf.float32)
    nonzero_flags = tf.squeeze(tf.not_equal(norms, zero))
    nonzero_indices = tf.squeeze(tf.where(nonzero_flags))
    nonzero_norms = tf.boolean_mask(norms, nonzero_flags)
    updated_grads = tf.boolean_mask(tangent_grads, tf.squeeze(nonzero_flags))
    updated_points = tf.boolean_mask(hyperboloid_points, nonzero_flags)
    # if norms == 0:
    #     return hyperboloid_points
    normed_grads = tf.divide(updated_grads, nonzero_norms)
    updates = tf.multiply(tf.cosh(nonzero_norms), updated_points) + tf.multiply(tf.sinh(nonzero_norms), normed_grads)
    return tf.scatter_update(hyperboloid_points, nonzero_indices, updates)


def test_project_onto_tangent_space():
    """
    Remember that we negate the first co-ordinate, so in 2D the hyperboloid appears rotated 90 degrees clockwise from how it is normally drawn
    :return:
    """
    y = tf.constant([1., 0])  # this the minima of the hyperboloid
    z = tf.constant([1., 0])
    w = tf.constant([0., 1.])
    u = tf.constant([0., -1.])
    v = tf.constant([1., 1.])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    # here the tangent space is x=1
    assert np.array_equal(sess.run(project_onto_tangent_space(y, z)), np.array([0., 0.]))
    assert np.array_equal(sess.run(project_onto_tangent_space(y, w)), np.array([0., 1.]))
    assert np.array_equal(sess.run(project_onto_tangent_space(y, u)), np.array([0., -1.]))
    assert np.array_equal(sess.run(project_onto_tangent_space(y, v)), np.array([0., 1.]))
    # consecutive projections don't change values
    s = tf.constant([math.sqrt(5), 2])  # point on hyperboloid
    t = tf.constant([6.2, 3.2])  # random grad
    temp1 = sess.run(project_onto_tangent_space(s, t))
    temp2 = sess.run(project_onto_tangent_space(s, temp1))
    assert np.array_equal(temp1, temp2)


def test_project_tensors_onto_tangent_space():
    u1 = tf.constant([[1., 0.], [1., 0.], [1., 0.], [1., 0.]], dtype=tf.float32)
    v1 = tf.constant([[1., 0.], [0., 1.], [0., -1.], [1., 1.]], dtype=tf.float32)
    retval1 = np.array([[0., 0.], [0., 1.], [0., -1.], [0., 1.]])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    assert np.array_equal(sess.run(project_tensors_onto_tangent_space(u1, v1)), retval1)
    # consecutive projections don't change values
    temp1 = sess.run(project_tensors_onto_tangent_space(u1, v1))
    temp2 = sess.run(project_tensors_onto_tangent_space(u1, temp1))
    assert np.array_equal(temp1, temp2)


def test_exp_map():
    """
    check that the exp_map takes vectors in the tangent space to the manifold
    :return:
    """
    p1 = tf.constant([1., 0.])  # this the minima of the hyperboloid
    g1 = tf.constant([0., 1.])
    g2 = tf.constant([0., -1.])
    g3 = tf.constant([0., 2.])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    # here the tangent space is x=1
    em1 = exp_map(p1, g1)
    em2 = exp_map(p1, g2)
    em3 = exp_map(p1, g3)
    # check that the points are on the hyperboloid
    assert round(sess.run(minkowski_vector_dot(em1, em1)), 4) == -1.
    assert round(sess.run(minkowski_vector_dot(em2, em2)), 4) == -1.
    assert round(sess.run(minkowski_vector_dot(em3, em3)), 4) == -1.
    em1 = sess.run(exp_map(p1, g1))
    em2 = sess.run(exp_map(p1, g2))
    em3 = sess.run(exp_map(p1, g3))
    assert em1[0] == em2[0]
    assert em1[1] == -em2[1]
    assert em3[0] > em1[0]
    assert em3[1] > em1[1]


def test_moving_along_hyperboloid():
    """
    test multiple series of e
    :return:
    """
    p1 = tf.constant([[1., 0.], [1., 0.], [1., 0.]])  # this the minima of the hyperboloid
    g1 = tf.constant([[0., 1.], [0., -1.], [0., 2.]])
    retval1 = np.array([[-1.], [-1.], [-1.]])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    for i in range(10):
        em = tensor_exp_map(p1, g1)
        # check that the points are on the hyperboloid
        norms = minkowski_tensor_dot(em, em)
        assert np.array_equal(np.around(sess.run(norms), 3), retval1)
        p1 = em
        g1 = project_tensors_onto_tangent_space(p1, g1)


def test_tensor_exp_map():
    """
    check that the exp_map takes vectors in the tangent space to the manifold
    :return:
    """
    p1 = tf.Variable([[1., 0.], [1., 0.], [1., 0.], [1., 0.]])  # this the minima of the hyperboloid
    g1 = tf.constant([[0., 1.], [0., -1.], [0., 2.], [0., 0.]])
    retval1 = np.array([[-1.], [-1.], [-1.], [-1.]])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    # here the tangent space is x=1
    em1 = tensor_exp_map(p1, g1)
    # check that the points are on the hyperboloid
    norms = sess.run(minkowski_tensor_dot(em1, em1))
    assert np.array_equal(np.around(norms, 3), retval1)
    em1 = sess.run(tensor_exp_map(p1, g1))
    assert em1[0, 0] == em1[1, 0]
    assert em1[0, 1] == -em1[1, 1]
    assert em1[2, 0] > em1[0, 0]
    assert em1[2, 1] > em1[0, 1]


def test_minkowski_vector_dot():
    u1 = tf.constant([1., 0])
    v1 = tf.constant([1., 0])
    v2 = tf.constant([10., 0])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    assert sess.run(minkowski_vector_dot(u1, v1)) == -1
    assert sess.run(minkowski_vector_dot(u1, v2)) == -10


def test_minkowski_tensor_dot():
    u1 = tf.constant([[1., 0., 1.], [1., 1., 1.]], dtype=tf.float32)
    v1 = tf.constant([[1., 1., 1.], [0., 0., 1.]], dtype=tf.float32)
    v2 = tf.constant([[2., 1., 1.], [2., 0., 1.]], dtype=tf.float32)
    retval1 = np.array([[0.], [1.]])
    retval2 = np.array([[-1.], [-1.]])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    assert np.array_equal(sess.run(minkowski_tensor_dot(u1, v1)), retval1)
    assert np.array_equal(sess.run(minkowski_tensor_dot(u1, v2)), retval2)


def test_minkowski_dist():
    u = tf.constant([1., 0])
    v = tf.constant([1., 0])
    x = tf.constant([10., 0])
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    assert sess.run(minkowski_dist(u, v)) == 0
    assert sess.run(minkowski_dist(v, x)) != 0


def test_gradient_transform_single_vector():
    grads = tf.Variable(np.array([1, 2]), dtype=tf.int32)
    x = np.eye(grads.shape[0])
    true_val = np.array([-1, 2])
    x[0, 0] = -1
    T = tf.constant(x, dtype=tf.int32)
    U = tf.tensordot(grads, T, 1)
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    retval = sess.run(U)
    print retval
    assert (np.array_equal(retval, true_val))


def test_gradient_transform_matrix():
    """
    grads come in a matrix of shape (n_vars, embedding_dim)
    :return:
    """
    grads = tf.Variable(np.array([[1., 2., 0.2], [3., 4., 0.5], [4., 2., 0.6]]))
    true_val = np.array([[-1., 2., 0.2], [-3., 4., 0.5], [-4., 2., 0.6]])
    x = np.eye(grads.shape[1])
    x[0, 0] = -1.
    T = tf.constant(x, dtype=tf.float64)
    U = tf.matmul(grads, T)
    sess = tf.Session()
    init = tf.global_variables_initializer()
    sess.run(init)
    retval = sess.run(U)
    print retval
    assert (np.array_equal(retval, true_val))


if __name__ == '__main__':
    test_gradient_transform_matrix()
