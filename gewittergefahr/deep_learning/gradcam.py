"""Methods for Grad-CAM (gradient-weighted class-activation-mapping).

Most of this was scavenged from:
https://github.com/jacobgil/keras-grad-cam/blob/master/grad-cam.py

--- REFERENCE ---

Selvaraju, R.R., M. Cogswell, A. Das, R. Vedantam, D. Parikh, and D. Batra,
2017: "Grad-CAM: Visual explanations from deep networks via gradient-based
localization".  International Conference on Computer Vision, IEEE,
https://doi.org/10.1109/ICCV.2017.74.
"""

import numpy
import keras
from keras import backend as K
import tensorflow
from tensorflow.python.framework import ops as tensorflow_ops
from scipy.interpolate import (
    UnivariateSpline, RectBivariateSpline, RegularGridInterpolator)
from gewittergefahr.gg_utils import error_checking

BACKPROP_FUNCTION_NAME = 'GuidedBackProp'


def _find_relevant_input_matrix(list_of_input_matrices, num_spatial_dim):
    """Finds relevant input matrix (with desired number of spatial dimensions).

    :param list_of_input_matrices: See doc for `run_gradcam`.
    :param num_spatial_dim: Desired number of spatial dimensions.
    :return: relevant_index: Array index for relevant input matrix.  If
        `relevant_index = q`, then list_of_input_matrices[q] is the relevant
        matrix.
    :raises: TypeError: if this method does not find exactly one input matrix
        with desired number of spatial dimensions.
    """

    num_spatial_dim_by_input = numpy.array(
        [len(m.shape) - 2 for m in list_of_input_matrices], dtype=int)

    these_indices = numpy.where(num_spatial_dim_by_input == num_spatial_dim)[0]
    if len(these_indices) != 1:
        error_string = (
            'Expected one input matrix with {0:d} dimensions.  Found {1:d} such'
            ' input matrices.'
        ).format(num_spatial_dim, len(these_indices))

        raise TypeError(error_string)

    return these_indices[0]


def _compute_gradients(loss_tensor, list_of_input_tensors):
    """Computes gradient of each input tensor with respect to loss tensor.

    :param loss_tensor: Loss tensor.
    :param list_of_input_tensors: 1-D list of input tensors.
    :return: list_of_gradient_tensors: 1-D list of gradient tensors.
    """

    list_of_gradient_tensors = tensorflow.gradients(
        loss_tensor, list_of_input_tensors)

    for i in range(len(list_of_gradient_tensors)):
        if list_of_gradient_tensors[i] is not None:
            continue

        list_of_gradient_tensors[i] = tensorflow.zeros_like(
            list_of_input_tensors[i])

    return list_of_gradient_tensors


def _normalize_tensor(input_tensor):
    """Normalizes tensor by its L2 norm.

    :param input_tensor: Unnormalized tensor.
    :return: output_tensor: Normalized tensor.
    """

    rms_tensor = K.sqrt(K.mean(K.square(input_tensor)))
    return input_tensor / (rms_tensor + K.epsilon())


def _upsample_cam(class_activation_matrix, new_dimensions):
    """Upsamples class-activation matrix (CAM).

    CAM may be 1-D, 2-D, or 3-D.

    :param class_activation_matrix: numpy array containing 1-D, 2-D, or 3-D
        class-activation matrix.
    :param new_dimensions: numpy array of new dimensions.  If matrix is
        {1D, 2D, 3D}, this must be a length-{1, 2, 3} array, respectively.
    :return: class_activation_matrix: Upsampled version of input.
    """

    num_rows_new = new_dimensions[0]
    row_indices_new = numpy.linspace(
        1, num_rows_new, num=num_rows_new, dtype=float)
    row_indices_orig = numpy.linspace(
        1, num_rows_new, num=class_activation_matrix.shape[0], dtype=float)

    if len(new_dimensions) == 1:
        interp_object = UnivariateSpline(
            x=row_indices_orig, y=numpy.ravel(class_activation_matrix),
            k=1, s=0)

        return interp_object(row_indices_new)

    num_columns_new = new_dimensions[1]
    column_indices_new = numpy.linspace(
        1, num_columns_new, num=num_columns_new, dtype=float)
    column_indices_orig = numpy.linspace(
        1, num_columns_new, num=class_activation_matrix.shape[1],
        dtype=float)

    if len(new_dimensions) == 2:
        interp_object = RectBivariateSpline(
            x=row_indices_orig, y=column_indices_orig,
            z=class_activation_matrix, kx=1, ky=1, s=0)

        return interp_object(x=row_indices_new, y=column_indices_new, grid=True)

    num_heights_new = new_dimensions[2]
    height_indices_new = numpy.linspace(
        1, num_heights_new, num=num_heights_new, dtype=float)
    height_indices_orig = numpy.linspace(
        1, num_heights_new, num=class_activation_matrix.shape[2],
        dtype=float)

    interp_object = RegularGridInterpolator(
        points=(row_indices_orig, column_indices_orig, height_indices_orig),
        values=class_activation_matrix, method='linear')

    row_index_matrix, column_index_matrix, height_index_matrix = (
        numpy.meshgrid(row_indices_new, column_indices_new, height_indices_new)
    )
    query_point_matrix = numpy.stack(
        (row_index_matrix, column_index_matrix, height_index_matrix), axis=-1)

    return interp_object(query_point_matrix)


def _register_guided_backprop():
    """Registers guided-backprop method with TensorFlow backend."""

    if (BACKPROP_FUNCTION_NAME not in
            tensorflow_ops._gradient_registry._registry):

        @tensorflow_ops.RegisterGradient(BACKPROP_FUNCTION_NAME)
        def _GuidedBackProp(operation, gradient_tensor):
            input_type = operation.inputs[0].dtype

            return (
                gradient_tensor *
                tensorflow.cast(gradient_tensor > 0., input_type) *
                tensorflow.cast(operation.inputs[0] > 0., input_type)
            )


def _change_backprop_function(model_object):
    """Changes backpropagation function for Keras model.

    :param model_object: Instance of `keras.models.Model` or
        `keras.models.Sequential`.
    :return: new_model_object: Same as `model_object` but with new backprop
        function.
    """

    # TODO(thunderhoser): I know that "Relu" is a valid operation name, but I
    # have no clue about the last three.
    orig_to_new_operation_dict = {
        'Relu': BACKPROP_FUNCTION_NAME,
        'LeakyRelu': BACKPROP_FUNCTION_NAME,
        'Elu': BACKPROP_FUNCTION_NAME,
        'Selu': BACKPROP_FUNCTION_NAME
    }

    graph_object = tensorflow.get_default_graph()

    with graph_object.gradient_override_map(orig_to_new_operation_dict):
        new_model_object = keras.models.clone_model(model_object)
        new_model_object.set_weights(model_object.get_weights())
        new_model_object.summary()

    return new_model_object


def _make_saliency_function(model_object, layer_name):
    """Creates saliency function.

    :param model_object: Instance of `keras.models.Model` or
        `keras.models.Sequential`.
    :param layer_name: Saliency will be computed with respect to activations in
        this layer.
    :return: saliency_function: Instance of `keras.backend.function`.
    """

    output_tensor = model_object.get_layer(name=layer_name).output
    filter_maxxed_output_tensor = K.max(output_tensor, axis=-1)

    if isinstance(model_object.input, list):
        list_of_input_tensors = model_object.input
    else:
        list_of_input_tensors = [model_object.input]

    list_of_saliency_tensors = K.gradients(
        K.sum(filter_maxxed_output_tensor), list_of_input_tensors)

    return K.function(
        list_of_input_tensors + [K.learning_phase()],
        list_of_saliency_tensors
    )


def _normalize_guided_gradcam_output(gradient_matrix):
    """Normalizes image produced by guided Grad-CAM.

    :param gradient_matrix: numpy array with output of guided Grad-CAM.
    :return: gradient_matrix: Normalized version of input.  If the first axis
        had length 1, it has been removed ("squeezed out").
    """

    if gradient_matrix.shape[0] == 1:
        gradient_matrix = gradient_matrix[0, ...]

    # Standardize.
    gradient_matrix -= numpy.mean(gradient_matrix)
    gradient_matrix /= (numpy.std(gradient_matrix, ddof=0) + K.epsilon())

    # Force standard deviation of 0.1 and mean of 0.5.
    gradient_matrix = 0.5 + gradient_matrix * 0.1
    gradient_matrix[gradient_matrix < 0.] = 0.
    gradient_matrix[gradient_matrix > 1.] = 1.

    return gradient_matrix


def run_gradcam(model_object, list_of_input_matrices, target_class,
                target_layer_name):
    """Runs Grad-CAM.

    T = number of input tensors to the model

    :param model_object: Trained instance of `keras.models.Model` or
        `keras.models.Sequential`.
    :param list_of_input_matrices: length-T list of numpy arrays, containing
        only one example (storm object).  list_of_input_matrices[i] must have
        the same dimensions as the [i]th input tensor to the model.
    :param target_class: Activation maps will be created for this class.  Must
        be an integer in 0...(K - 1), where K = number of classes.
    :param target_layer_name: Name of target layer.  Neuron-importance weights
        will be based on activations in this layer.
    :return: class_activation_matrix: Class-activation matrix.  Dimensions of
        this numpy array will be the spatial dimensions of whichever input
        tensor feeds into the target layer.  For example, if the given input
        tensor is 2-dimensional with M rows and N columns, this array will be
        M x N.
    """

    # Check input args.
    error_checking.assert_is_string(target_layer_name)
    for q in range(len(list_of_input_matrices)):
        error_checking.assert_is_numpy_array(list_of_input_matrices[q])

        if list_of_input_matrices[q].shape[0] != 1:
            list_of_input_matrices[q] = numpy.expand_dims(
                list_of_input_matrices[q], axis=0)

    # Create loss tensor.
    output_layer_object = model_object.layers[-1].output
    num_output_neurons = output_layer_object.get_shape().as_list()[-1]

    if num_output_neurons == 1:
        error_checking.assert_is_leq(target_class, 1)

        if target_class == 1:
            loss_tensor = model_object.layers[-1].output[..., 0]
        else:
            loss_tensor = 1 - model_object.layers[-1].output[..., 0]
    else:
        error_checking.assert_is_less_than(target_class, num_output_neurons)
        loss_tensor = model_object.layers[-1].output[..., target_class]

    # Create gradient function.
    target_layer_activation_tensor = model_object.get_layer(
        name=target_layer_name
    ).output

    gradient_tensor = _compute_gradients(
        loss_tensor, [target_layer_activation_tensor]
    )[0]
    gradient_tensor = _normalize_tensor(gradient_tensor)

    if isinstance(model_object.input, list):
        list_of_input_tensors = model_object.input
    else:
        list_of_input_tensors = [model_object.input]

    gradient_function = K.function(
        list_of_input_tensors, [target_layer_activation_tensor, gradient_tensor]
    )

    # Evaluate gradient function.
    target_layer_activation_matrix, gradient_matrix = gradient_function(
        list_of_input_matrices)
    target_layer_activation_matrix = target_layer_activation_matrix[0, ...]
    gradient_matrix = gradient_matrix[0, ...]

    # Compute class-activation matrix.
    mean_weight_by_filter = numpy.mean(gradient_matrix, axis=(0, 1))
    class_activation_matrix = numpy.ones(
        target_layer_activation_matrix.shape[:-1])

    num_filters = len(mean_weight_by_filter)
    for m in range(num_filters):
        class_activation_matrix += (
            mean_weight_by_filter[m] * target_layer_activation_matrix[..., m]
        )

    input_index = _find_relevant_input_matrix(
        list_of_input_matrices=list_of_input_matrices,
        num_spatial_dim=len(class_activation_matrix.shape)
    )

    spatial_dimensions = numpy.array(
        list_of_input_matrices[input_index].shape[1:-1], dtype=int)
    class_activation_matrix = _upsample_cam(
        class_activation_matrix=class_activation_matrix,
        new_dimensions=spatial_dimensions)

    class_activation_matrix[class_activation_matrix < 0.] = 0.
    denominator = numpy.maximum(numpy.max(class_activation_matrix), K.epsilon())
    return class_activation_matrix / denominator


def run_guided_gradcam(model_object, list_of_input_matrices, target_layer_name,
                       class_activation_matrix):
    """Runs guided Grad-CAM.

    M = number of rows in grid
    N = number of columns in grid
    C = number of channels

    :param model_object: See doc for `run_gradcam`.
    :param list_of_input_matrices: Same.
    :param target_layer_name: Same.
    :param class_activation_matrix: Matrix created by `run_gradcam`.
    :return: gradient_matrix: M-by-N-by-C numpy array of gradients.
    """

    _register_guided_backprop()

    new_model_object = _change_backprop_function(model_object=model_object)
    saliency_function = _make_saliency_function(
        model_object=new_model_object, layer_name=target_layer_name)

    input_index = _find_relevant_input_matrix(
        list_of_input_matrices=list_of_input_matrices,
        num_spatial_dim=len(class_activation_matrix.shape)
    )

    saliency_matrix = saliency_function(
        list_of_input_matrices + [0]
    )[input_index]

    gradient_matrix = saliency_matrix * class_activation_matrix[
        ..., numpy.newaxis]
    return _normalize_guided_gradcam_output(gradient_matrix)