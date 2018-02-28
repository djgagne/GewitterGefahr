"""Model evaluation.

This module can be used to evaluate any kind of weather model (machine learning,
NWP, heuristics, human forecasting, etc.).  This module is completely agnostic
of where the forecasts come from.

--- REFERENCES ---

Roebber, P., 2009: Visualizing multiple measures of forecast quality. Weather
    and Forecasting, 24 (2), 601-608.

Lagerquist, R., McGovern, A., and Smith, T., 2017: Machine learning for real-
    time prediction of damaging straight-line convective wind. Weather and
    Forecasting, 2017, in press.
"""

import copy
import numpy
import sklearn.metrics
from gewittergefahr.gg_utils import grids
from gewittergefahr.gg_utils import histograms
from gewittergefahr.gg_utils import bootstrapping
from gewittergefahr.gg_utils import number_rounding as rounder
from gewittergefahr.gg_utils import error_checking

# TODO(thunderhoser): All classification metrics are currently for binary
# classification only.  Need to allow multiclass.

# TODO(thunderhoser): May create different modules for binary classification,
# multiclass classification, and regression.

TOLERANCE = 1e-6
MIN_FORECAST_PROB_FOR_XENTROPY = numpy.finfo(float).eps
MAX_FORECAST_PROB_FOR_XENTROPY = 1. - numpy.finfo(float).eps

DEFAULT_NUM_BOOTSTRAP_ITERS = 100
DEFAULT_BOOTSTRAP_CONFIDENCE_LEVEL = 0.95

NUM_TRUE_POSITIVES_KEY = 'num_true_positives'
NUM_FALSE_POSITIVES_KEY = 'num_false_positives'
NUM_FALSE_NEGATIVES_KEY = 'num_false_negatives'
NUM_TRUE_NEGATIVES_KEY = 'num_true_negatives'

BRIER_SKILL_SCORE_KEY = 'brier_skill_score'
BRIER_SCORE_KEY = 'brier_score'
RESOLUTION_KEY = 'resolution'
RELIABILITY_KEY = 'reliability'
UNCERTAINTY_KEY = 'uncertainty'

POD_BY_THRESHOLD_KEY = 'pod_by_threshold'
POFD_BY_THRESHOLD_KEY = 'pofd_by_threshold'
AREA_UNDER_ROC_CURVE_KEY = 'area_under_curve'
SUCCESS_RATIO_BY_THRESHOLD_KEY = 'success_ratio_by_threshold'
MAX_CSI_KEY = 'max_csi_over_thresholds'
MEAN_FORECAST_PROB_BY_BIN_KEY = 'mean_forecast_prob_by_bin'
MEAN_OBSERVED_LABEL_BY_BIN_KEY = 'mean_observed_label_by_bin'

MIN_BINARIZATION_THRESHOLD = 0.
MAX_BINARIZATION_THRESHOLD = 1. + TOLERANCE

DEFAULT_NUM_BINS_FOR_RELIABILITY_CURVE = 10
DEFAULT_PRECISION_FOR_THRESHOLDS = 1e-4
THRESHOLD_ARG_FOR_UNIQUE_FORECASTS = 'unique_forecasts'

DEFAULT_SUCCESS_RATIO_SPACING = 0.01
DEFAULT_POD_SPACING = 0.01


def _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels):
    """Error-checks forecast probabilities and observed labels.

    N = number of forecasts

    :param forecast_probabilities: length-N numpy array with forecast
        probabilities of some event (e.g., tornado).
    :param observed_labels: length-N integer numpy array of observed labels
        (1 for "yes", 0 for "no").
    """

    error_checking.assert_is_numpy_array(
        forecast_probabilities, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(forecast_probabilities, 0.)
    error_checking.assert_is_leq_numpy_array(forecast_probabilities, 1.)
    num_forecasts = len(forecast_probabilities)

    error_checking.assert_is_integer_numpy_array(observed_labels)
    error_checking.assert_is_numpy_array(
        observed_labels, exact_dimensions=numpy.array([num_forecasts]))
    error_checking.assert_is_geq_numpy_array(observed_labels, 0)
    error_checking.assert_is_leq_numpy_array(observed_labels, 1)


def _check_forecast_and_observed_labels(forecast_labels, observed_labels):
    """Error-checks forecast and observed labels.

    N = number of forecasts

    :param forecast_labels: length-N integer numpy array of forecast labels
        (1 for "yes", 0 for "no").
    :param observed_labels: Same but for observed labels.
    """

    error_checking.assert_is_integer_numpy_array(forecast_labels)
    error_checking.assert_is_numpy_array(forecast_labels, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(forecast_labels, 0)
    error_checking.assert_is_leq_numpy_array(forecast_labels, 1)
    num_forecasts = len(forecast_labels)

    error_checking.assert_is_integer_numpy_array(observed_labels)
    error_checking.assert_is_numpy_array(
        observed_labels, exact_dimensions=numpy.array([num_forecasts]))
    error_checking.assert_is_geq_numpy_array(observed_labels, 0)
    error_checking.assert_is_leq_numpy_array(observed_labels, 1)


def _pad_binarization_thresholds(thresholds):
    """Pads an array of binarization thresholds.

    Specifically, this method ensures that the array contains 0 and a number
        slightly greater than 1.  This ensures that:

    [1] For the lowest threshold, POD = POFD = 1, which is the top-right corner
        of the ROC curve.
    [2] For the highest threshold, POD = POFD = 0, which is the bottom-left
        corner of the ROC curve.

    :param thresholds: 1-D numpy array of binarization thresholds.
    :return: thresholds: 1-D numpy array of binarization thresholds (possibly
        with new elements).
    """

    thresholds = numpy.sort(thresholds)
    if thresholds[0] > MIN_BINARIZATION_THRESHOLD:
        thresholds = numpy.concatenate((
            numpy.array([MIN_BINARIZATION_THRESHOLD]), thresholds))

    if thresholds[-1] < MAX_BINARIZATION_THRESHOLD:
        thresholds = numpy.concatenate((
            thresholds, numpy.array([MAX_BINARIZATION_THRESHOLD])))

    return thresholds


def _split_forecast_probs_into_bins(forecast_probabilities, num_bins):
    """Splits forecast probabilities into bins.

    N = number of forecasts

    :param forecast_probabilities: length-N numpy array of forecast
        probabilities.
    :param num_bins: Number of bins into which forecasts will be discretized.
    :return: bin_index_by_forecast: length-N numpy array of indices.  If
        bin_index_by_forecast[i] = j, the [i]th forecast belongs in the [j]th
        bin.
    """

    bin_index_by_forecast, _ = histograms.create_histogram(
        input_values=forecast_probabilities, num_bins=num_bins, min_value=0.,
        max_value=1.)
    return bin_index_by_forecast


def get_binarization_thresholds(
        threshold_arg, forecast_probabilities=None,
        unique_forecast_precision=DEFAULT_PRECISION_FOR_THRESHOLDS):
    """Returns list of binarization thresholds.

    To understand the role of binarization thresholds, see
    binarize_forecast_probs.

    :param threshold_arg: Main threshold argument.  May be in one of 3 formats.
    [1] threshold_arg = "unique_forecasts".  In this case all unique forecast
        probabilities will become binarization thresholds.
    [2] 1-D numpy array.  In this case threshold_arg will be treated as an array
        of binarization thresholds.
    [3] Positive integer.  In this case threshold_arg will be treated as the
        number of binarization thresholds, equally spaced from 0...1.

    :param forecast_probabilities:
        [used only if threshold_arg = "unique_forecasts"]
        1-D numpy array of forecast probabilities to binarize.
    :param unique_forecast_precision:
        [used only if threshold_arg = "unique_forecasts"]
        Before computing unique forecast probabilities, they will all be rounded
        to the nearest `unique_forecast_precision`.  This prevents the number of
        thresholds from becoming ridiculous (millions).
    :return: binarization_thresholds: 1-D numpy array of binarization
        thresholds.
    :raises: ValueError: if threshold_arg cannot be interpreted.
    """

    if isinstance(threshold_arg, str):
        if threshold_arg != THRESHOLD_ARG_FOR_UNIQUE_FORECASTS:
            error_string = (
                'If string, threshold_arg must be "{0:s}".  Instead, got '
                '"{1:s}".').format(THRESHOLD_ARG_FOR_UNIQUE_FORECASTS,
                                   threshold_arg)
            raise ValueError(error_string)

        error_checking.assert_is_geq(unique_forecast_precision, 0.)
        error_checking.assert_is_leq(unique_forecast_precision, 0.01)

        binarization_thresholds = numpy.unique(rounder.round_to_nearest(
            copy.deepcopy(forecast_probabilities), unique_forecast_precision))

    elif isinstance(threshold_arg, numpy.ndarray):
        binarization_thresholds = copy.deepcopy(threshold_arg)

        error_checking.assert_is_numpy_array(
            binarization_thresholds, num_dimensions=1)
        error_checking.assert_is_geq_numpy_array(
            binarization_thresholds, MIN_BINARIZATION_THRESHOLD)
        error_checking.assert_is_leq_numpy_array(
            binarization_thresholds, MAX_BINARIZATION_THRESHOLD)

    else:
        num_thresholds = copy.deepcopy(threshold_arg)
        error_checking.assert_is_integer(num_thresholds)
        error_checking.assert_is_geq(num_thresholds, 2)

        binarization_thresholds = numpy.linspace(0., 1., num=num_thresholds)

    return _pad_binarization_thresholds(binarization_thresholds)


def binarize_forecast_probs(forecast_probabilities, binarization_threshold):
    """Binarizes probabilistic forecasts, turning them into deterministic ones.

    N = number of forecasts

    :param forecast_probabilities: length-N numpy array with forecast
        probabilities of some event (e.g., tornado).
    :param binarization_threshold: Binarization threshold (f*).  All forecasts
        >= f* will be turned into "yes" forecasts; all forecasts < f* will be
        turned into "no".
    :return: forecast_labels: length-N integer numpy array of deterministic
        forecasts (1 for "yes", 0 for "no").
    """

    error_checking.assert_is_numpy_array(
        forecast_probabilities, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(forecast_probabilities, 0.)
    error_checking.assert_is_leq_numpy_array(forecast_probabilities, 1.)

    error_checking.assert_is_geq(
        binarization_threshold, MIN_BINARIZATION_THRESHOLD)
    error_checking.assert_is_leq(
        binarization_threshold, MAX_BINARIZATION_THRESHOLD)

    forecast_labels = numpy.full(len(forecast_probabilities), False, dtype=bool)
    positive_label_indices = numpy.where(
        forecast_probabilities >= binarization_threshold)[0]
    forecast_labels[positive_label_indices] = True

    return forecast_labels.astype(int)


def get_contingency_table(forecast_labels, observed_labels):
    """Computes contingency table.

    N = number of forecasts

    :param forecast_labels: See documentation for
        _check_forecast_and_observed_labels.
    :param observed_labels: See doc for _check_forecast_and_observed_labels.
    :return: contingency_table_as_dict: Dictionary with the following keys.
    contingency_table_as_dict['num_true_positives']: Number of true positives.
    contingency_table_as_dict['num_false_positives']: Number of false positives.
    contingency_table_as_dict['num_false_negatives']: Number of false negatives.
    contingency_table_as_dict['num_true_negatives']: Number of true negatives.
    """

    _check_forecast_and_observed_labels(forecast_labels, observed_labels)

    true_positive_indices = numpy.where(numpy.logical_and(
        forecast_labels == 1, observed_labels == 1))[0]
    false_positive_indices = numpy.where(numpy.logical_and(
        forecast_labels == 1, observed_labels == 0))[0]
    false_negative_indices = numpy.where(numpy.logical_and(
        forecast_labels == 0, observed_labels == 1))[0]
    true_negative_indices = numpy.where(numpy.logical_and(
        forecast_labels == 0, observed_labels == 0))[0]

    return {
        NUM_TRUE_POSITIVES_KEY: len(true_positive_indices),
        NUM_FALSE_POSITIVES_KEY: len(false_positive_indices),
        NUM_FALSE_NEGATIVES_KEY: len(false_negative_indices),
        NUM_TRUE_NEGATIVES_KEY: len(true_negative_indices)
    }


def get_pod(contingency_table_as_dict):
    """Computes POD (probability of detection).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: probability_of_detection: POD.
    """

    try:
        return float(contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY]) / (
            contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
            contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_fom(contingency_table_as_dict):
    """Computes FOM (frequency of misses).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: frequency_of_misses: FOM.
    """

    return 1. - get_pod(contingency_table_as_dict)


def get_pofd(contingency_table_as_dict):
    """Computes POFD (probability of false detection).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: probability_of_false_detection: POFD.
    """

    try:
        return float(contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY]) / (
            contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY] +
            contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_npv(contingency_table_as_dict):
    """Computes NPV (negative predictive value).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: negative_predictive_value: NPV.
    """

    return 1. - get_pofd(contingency_table_as_dict)


def get_success_ratio(contingency_table_as_dict):
    """Computes success ratio.

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: success_ratio: Success ratio.
    """

    try:
        return float(contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY]) / (
            contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
            contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_far(contingency_table_as_dict):
    """Computes FAR (false-alarm rate).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: false_alarm_rate: FAR.
    """

    return 1. - get_success_ratio(contingency_table_as_dict)


def get_dfr(contingency_table_as_dict):
    """Computes DFR (detection-failure ratio).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: detection_failure_ratio: DFR.
    """

    try:
        return float(contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY]) / (
            contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY] +
            contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_focn(contingency_table_as_dict):
    """Computes FOCN (frequency of correct nulls).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: frequency_of_correct_nulls: FOCN.
    """

    return 1. - get_dfr(contingency_table_as_dict)


def get_accuracy(contingency_table_as_dict):
    """Computes accuracy.

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: accuracy: Accuracy.
    """

    try:
        return float(contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
                     contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY]) / (
                         contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
                         contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY] +
                         contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY] +
                         contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_csi(contingency_table_as_dict):
    """Computes CSI (critical success index).

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: critical_success_index: CSI.
    """

    try:
        return float(contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY]) / (
            contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
            contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY] +
            contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_frequency_bias(contingency_table_as_dict):
    """Computes frequency bias.

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: frequency_bias: Frequency bias.
    """

    try:
        return float(contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
                     contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY]) / (
                         contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
                         contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY])
    except ZeroDivisionError:
        return numpy.nan


def get_peirce_score(contingency_table_as_dict):
    """Computes Peirce score.

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: peirce_score: Peirce score.
    """

    return (get_pod(contingency_table_as_dict) -
            get_pofd(contingency_table_as_dict))


def get_heidke_score(contingency_table_as_dict):
    """Computes Heidke score.

    :param contingency_table_as_dict: Dictionary created by
        get_contingency_table.
    :return: heidke_score: Heidke score.
    """

    try:
        numerator = 2 * (contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] *
                         contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY] -
                         contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY] *
                         contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY])

        num_positives = (contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
                         contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY])
        num_negatives = (contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY] +
                         contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY])
        num_events = (contingency_table_as_dict[NUM_TRUE_POSITIVES_KEY] +
                      contingency_table_as_dict[NUM_FALSE_NEGATIVES_KEY])
        num_non_events = (contingency_table_as_dict[NUM_TRUE_NEGATIVES_KEY] +
                          contingency_table_as_dict[NUM_FALSE_POSITIVES_KEY])

        return float(numerator) / (
            num_positives * num_non_events + num_negatives * num_events)
    except ZeroDivisionError:
        return numpy.nan


def get_brier_score(forecast_probabilities=None, observed_labels=None):
    """Computes Brier score.

    N = number of forecasts

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :return: brier_score: Brier score.
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    return numpy.mean((forecast_probabilities - observed_labels) ** 2)


def get_cross_entropy(forecast_probabilities=None, observed_labels=None):
    """Computes cross-entropy.

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :return: cross_entropy: Cross-entropy.
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    forecast_probabilities[
        forecast_probabilities <
        MIN_FORECAST_PROB_FOR_XENTROPY] = MIN_FORECAST_PROB_FOR_XENTROPY
    forecast_probabilities[
        forecast_probabilities >
        MAX_FORECAST_PROB_FOR_XENTROPY] = MAX_FORECAST_PROB_FOR_XENTROPY
    observed_labels = observed_labels.astype(numpy.float)

    return -numpy.mean(
        observed_labels * numpy.log2(forecast_probabilities) +
        (1 - observed_labels) * numpy.log2(1 - forecast_probabilities))


def get_area_under_roc_curve(pofd_by_threshold, pod_by_threshold):
    """Computes area under ROC curve.

    This calculation ignores NaN's.  If you use `sklearn.metrics.auc` without
    this wrapper, if either input array contains any NaN, the result will be
    NaN.

    T = number of binarization thresholds

    :param pofd_by_threshold: length-T numpy array of POFD values.
    :param pod_by_threshold: length-T numpy array of corresponding POD values.
    :return: area_under_curve: Area under ROC curve.
    """

    error_checking.assert_is_numpy_array(pofd_by_threshold, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(
        pofd_by_threshold, 0., allow_nan=True)
    error_checking.assert_is_leq_numpy_array(
        pofd_by_threshold, 1., allow_nan=True)
    num_thresholds = len(pofd_by_threshold)

    error_checking.assert_is_numpy_array(
        pod_by_threshold, exact_dimensions=numpy.array([num_thresholds]))
    error_checking.assert_is_geq_numpy_array(
        pod_by_threshold, 0., allow_nan=True)
    error_checking.assert_is_leq_numpy_array(
        pod_by_threshold, 1., allow_nan=True)

    sort_indices = numpy.argsort(-pofd_by_threshold)
    pofd_by_threshold = pofd_by_threshold[sort_indices]
    pod_by_threshold = pod_by_threshold[sort_indices]

    nan_flags = numpy.logical_or(
        numpy.isnan(pofd_by_threshold), numpy.isnan(pod_by_threshold))
    if numpy.all(nan_flags):
        return numpy.nan

    real_indices = numpy.where(numpy.invert(nan_flags))[0]
    return sklearn.metrics.auc(
        pofd_by_threshold[real_indices], pod_by_threshold[real_indices])


def get_points_in_roc_curve(
        forecast_probabilities=None, observed_labels=None, threshold_arg=None,
        unique_forecast_precision=DEFAULT_PRECISION_FOR_THRESHOLDS):
    """Determines points in ROC (receiver operating characteristic) curve.

    N = number of forecasts
    T = number of binarization thresholds

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :param threshold_arg: See documentation for get_binarization_thresholds.
    :param unique_forecast_precision: See doc for get_binarization_thresholds.
    :return: pofd_by_threshold: length-T numpy array of POFD values, to be
        plotted on the x-axis.
    :return: pod_by_threshold: length-T numpy array of POD values, to be plotted
        on the y-axis.
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    binarization_thresholds = get_binarization_thresholds(
        threshold_arg=threshold_arg,
        forecast_probabilities=forecast_probabilities,
        unique_forecast_precision=unique_forecast_precision)

    num_thresholds = len(binarization_thresholds)
    pofd_by_threshold = numpy.full(num_thresholds, numpy.nan)
    pod_by_threshold = numpy.full(num_thresholds, numpy.nan)

    for i in range(num_thresholds):
        these_forecast_labels = binarize_forecast_probs(
            forecast_probabilities, binarization_thresholds[i])
        this_contingency_table_as_dict = get_contingency_table(
            these_forecast_labels, observed_labels)

        pofd_by_threshold[i] = get_pofd(this_contingency_table_as_dict)
        pod_by_threshold[i] = get_pod(this_contingency_table_as_dict)

    return pofd_by_threshold, pod_by_threshold


def bootstrap_roc_curve(
        forecast_probabilities=None, observed_labels=None, threshold_arg=None,
        unique_forecast_precision=DEFAULT_PRECISION_FOR_THRESHOLDS,
        num_bootstrap_iters=DEFAULT_NUM_BOOTSTRAP_ITERS,
        confidence_level=DEFAULT_BOOTSTRAP_CONFIDENCE_LEVEL):
    """Bootstrapped version of get_points_in_roc_curve.

    T = number of binarization thresholds (same for top, middle, and bottom of
        confidence interval).

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :param threshold_arg: See documentation for get_binarization_thresholds.
    :param unique_forecast_precision: See doc for get_binarization_thresholds.
    :param num_bootstrap_iters: Number of bootstrapping iterations (number of
        samples to draw from full set of forecast-observation pairs).
    :param confidence_level: Confidence level.  Will be used to create
        confidence interval ("envelope") for ROC curve.
    :return: roc_dictionary_bottom: Dictionary with the following keys.
    roc_dictionary_bottom['pofd_by_threshold']: length-T numpy array of POFD
        values for bottom of envelope (confidence interval).
    roc_dictionary_bottom['pod_by_threshold']: Same but for POD.
    roc_dictionary_bottom['area_under_curve']: Area under ROC curve.

    :return: roc_dictionary_mean: Same as roc_dictionary_bottom, but for middle
        of envelope (confidence interval).
    :return: roc_dictionary_top: Same as roc_dictionary_bottom, but for top of
        envelope (confidence interval).
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    binarization_thresholds = get_binarization_thresholds(
        threshold_arg=threshold_arg,
        forecast_probabilities=forecast_probabilities,
        unique_forecast_precision=unique_forecast_precision)

    error_checking.assert_is_integer(num_bootstrap_iters)
    error_checking.assert_is_greater(num_bootstrap_iters, 1)

    num_thresholds = len(binarization_thresholds)
    pod_matrix = numpy.full((num_thresholds, num_bootstrap_iters), numpy.nan)
    pofd_matrix = numpy.full((num_thresholds, num_bootstrap_iters), numpy.nan)
    auc_values = numpy.full(num_bootstrap_iters, numpy.nan)

    for j in range(num_bootstrap_iters):
        _, these_sample_indices = bootstrapping.draw_sample(
            forecast_probabilities)

        for i in range(num_thresholds):
            these_forecast_labels = binarize_forecast_probs(
                forecast_probabilities[these_sample_indices],
                binarization_thresholds[i])
            this_contingency_table_as_dict = get_contingency_table(
                these_forecast_labels, observed_labels[these_sample_indices])

            pofd_matrix[i, j] = get_pofd(this_contingency_table_as_dict)
            pod_matrix[i, j] = get_pod(this_contingency_table_as_dict)

        auc_values[j] = get_area_under_roc_curve(
            pofd_matrix[:, j], pod_matrix[:, j])

    roc_dictionary_bottom = {
        POD_BY_THRESHOLD_KEY: numpy.full(num_thresholds, numpy.nan),
        POFD_BY_THRESHOLD_KEY: numpy.full(num_thresholds, numpy.nan),
        AREA_UNDER_ROC_CURVE_KEY: numpy.nan
    }
    roc_dictionary_top = copy.deepcopy(roc_dictionary_bottom)
    roc_dictionary_mean = copy.deepcopy(roc_dictionary_bottom)

    for i in range(num_thresholds):
        (roc_dictionary_top[POFD_BY_THRESHOLD_KEY][i],
         roc_dictionary_bottom[POFD_BY_THRESHOLD_KEY][i]) = (
             bootstrapping.get_confidence_interval(
                 pofd_matrix[i, :], confidence_level))

        (roc_dictionary_bottom[POD_BY_THRESHOLD_KEY][i],
         roc_dictionary_top[POD_BY_THRESHOLD_KEY][i]) = (
             bootstrapping.get_confidence_interval(
                 pod_matrix[i, :], confidence_level))

    roc_dictionary_mean[POFD_BY_THRESHOLD_KEY] = numpy.nanmean(
        pofd_matrix, axis=1)
    roc_dictionary_mean[POD_BY_THRESHOLD_KEY] = numpy.nanmean(
        pod_matrix, axis=1)

    (roc_dictionary_bottom[AREA_UNDER_ROC_CURVE_KEY],
     roc_dictionary_top[AREA_UNDER_ROC_CURVE_KEY]) = (
         bootstrapping.get_confidence_interval(auc_values, confidence_level))
    roc_dictionary_mean[AREA_UNDER_ROC_CURVE_KEY] = numpy.nanmean(auc_values)

    return roc_dictionary_bottom, roc_dictionary_mean, roc_dictionary_top


def get_random_roc_curve():
    """Returns points in random ROC (receiver operating characteristic) curve.

    :return: pofd_by_threshold: length-2 numpy array of POFD values.
    :return: pod_by_threshold: length-2 numpy array of POD values.
    """

    return numpy.array([0., 1.]), numpy.array([0., 1.])


def get_points_in_performance_diagram(
        forecast_probabilities=None, observed_labels=None, threshold_arg=None,
        unique_forecast_precision=DEFAULT_PRECISION_FOR_THRESHOLDS):
    """Determines points in performance diagram (Roebber 2009).

    T = number of binarization thresholds

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :param threshold_arg: See doc for get_binarization_thresholds.
    :param unique_forecast_precision: See doc for get_binarization_thresholds.
    :return: success_ratio_by_threshold: length-T numpy array of success ratios,
        to be plotted on the x-axis.
    :return: pod_by_threshold: length-T numpy array of POD values, to be plotted
        on the y-axis.
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    binarization_thresholds = get_binarization_thresholds(
        threshold_arg=threshold_arg,
        forecast_probabilities=forecast_probabilities,
        unique_forecast_precision=unique_forecast_precision)

    num_thresholds = len(binarization_thresholds)
    success_ratio_by_threshold = numpy.full(num_thresholds, numpy.nan)
    pod_by_threshold = numpy.full(num_thresholds, numpy.nan)

    for i in range(num_thresholds):
        these_forecast_labels = binarize_forecast_probs(
            forecast_probabilities, binarization_thresholds[i])
        this_contingency_table_as_dict = get_contingency_table(
            these_forecast_labels, observed_labels)

        success_ratio_by_threshold[i] = get_success_ratio(
            this_contingency_table_as_dict)
        pod_by_threshold[i] = get_pod(this_contingency_table_as_dict)

    return success_ratio_by_threshold, pod_by_threshold


def bootstrap_performance_diagram(
        forecast_probabilities=None, observed_labels=None, threshold_arg=None,
        unique_forecast_precision=DEFAULT_PRECISION_FOR_THRESHOLDS,
        num_bootstrap_iters=DEFAULT_NUM_BOOTSTRAP_ITERS,
        confidence_level=DEFAULT_BOOTSTRAP_CONFIDENCE_LEVEL):
    """Bootstrapped version of get_points_in_performance_diagram.

    T = number of binarization thresholds (same for top, middle, and bottom of
        confidence interval).

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :param threshold_arg: See documentation for get_binarization_thresholds.
    :param unique_forecast_precision: See doc for get_binarization_thresholds.
    :param num_bootstrap_iters: Number of bootstrapping iterations (number of
        samples to draw from full set of forecast-observation pairs).
    :param confidence_level: Confidence level.  Will be used to create
        confidence interval ("envelope") for performance diagram.
    :return: performance_diagram_dict_bottom: Dictionary with the following
        keys.
    performance_diagram_dict_bottom['success_ratio_by_threshold']: length-T
        numpy array of success ratios for bottom of envelope (confidence
        interval).
    performance_diagram_dict_bottom['pod_by_threshold']: Same but for POD.
    performance_diagram_dict_bottom['max_csi_over_thresholds']: Maximum CSI
        (critical success index) over all thresholds.

    :return: performance_diagram_dict_mean: Same as
        performance_diagram_dict_bottom, but for middle of envelope (confidence
        interval).
    :return: performance_diagram_dict_top: Same as
        performance_diagram_dict_bottom, but for top of envelope (confidence
        interval).
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    binarization_thresholds = get_binarization_thresholds(
        threshold_arg=threshold_arg,
        forecast_probabilities=forecast_probabilities,
        unique_forecast_precision=unique_forecast_precision)

    error_checking.assert_is_integer(num_bootstrap_iters)
    error_checking.assert_is_greater(num_bootstrap_iters, 1)

    num_thresholds = len(binarization_thresholds)
    pod_matrix = numpy.full((num_thresholds, num_bootstrap_iters), numpy.nan)
    success_ratio_matrix = numpy.full((num_thresholds, num_bootstrap_iters),
                                      numpy.nan)
    max_csi_values = numpy.full(num_bootstrap_iters, numpy.nan)

    for j in range(num_bootstrap_iters):
        _, these_sample_indices = bootstrapping.draw_sample(
            forecast_probabilities)
        these_csi_values = numpy.full(num_thresholds, numpy.nan)

        for i in range(num_thresholds):
            these_forecast_labels = binarize_forecast_probs(
                forecast_probabilities[these_sample_indices],
                binarization_thresholds[i])
            this_contingency_table_as_dict = get_contingency_table(
                these_forecast_labels, observed_labels[these_sample_indices])

            pod_matrix[i, j] = get_pod(this_contingency_table_as_dict)
            success_ratio_matrix[i, j] = get_success_ratio(
                this_contingency_table_as_dict)
            these_csi_values[i] = csi_from_sr_and_pod(
                numpy.array([success_ratio_matrix[i, j]]),
                numpy.array([pod_matrix[i, j]]))[0]

        max_csi_values[j] = numpy.nanmax(these_csi_values)

    performance_diagram_dict_bottom = {
        POD_BY_THRESHOLD_KEY: numpy.full(num_thresholds, numpy.nan),
        SUCCESS_RATIO_BY_THRESHOLD_KEY: numpy.full(num_thresholds, numpy.nan)
    }
    performance_diagram_dict_top = copy.deepcopy(
        performance_diagram_dict_bottom)
    performance_diagram_dict_mean = copy.deepcopy(
        performance_diagram_dict_bottom)

    for i in range(num_thresholds):
        (performance_diagram_dict_bottom[POD_BY_THRESHOLD_KEY][i],
         performance_diagram_dict_top[POD_BY_THRESHOLD_KEY][i]) = (
             bootstrapping.get_confidence_interval(
                 pod_matrix[i, :], confidence_level))

        (performance_diagram_dict_bottom[SUCCESS_RATIO_BY_THRESHOLD_KEY][i],
         performance_diagram_dict_top[SUCCESS_RATIO_BY_THRESHOLD_KEY][i]) = (
             bootstrapping.get_confidence_interval(
                 success_ratio_matrix[i, :], confidence_level))

    performance_diagram_dict_mean[POD_BY_THRESHOLD_KEY] = numpy.nanmean(
        pod_matrix, axis=1)
    performance_diagram_dict_mean[SUCCESS_RATIO_BY_THRESHOLD_KEY] = (
        numpy.nanmean(success_ratio_matrix, axis=1))

    (performance_diagram_dict_bottom[MAX_CSI_KEY],
     performance_diagram_dict_top[MAX_CSI_KEY]) = (
         bootstrapping.get_confidence_interval(
             max_csi_values, confidence_level))
    performance_diagram_dict_mean[MAX_CSI_KEY] = numpy.nanmean(max_csi_values)

    return (performance_diagram_dict_bottom,
            performance_diagram_dict_mean,
            performance_diagram_dict_top)


def get_sr_pod_grid(success_ratio_spacing=DEFAULT_SUCCESS_RATIO_SPACING,
                    pod_spacing=DEFAULT_POD_SPACING):
    """Creates grid in SR-POD space

    SR = success ratio
    POD = probability of detection
    SR-POD space is the same as performance-diagram.

    M = number of rows (unique POD values) in grid
    N = number of columns (unique success ratios) in grid

    :param success_ratio_spacing: Spacing between adjacent success ratios
        (x-values) in grid.
    :param pod_spacing: Spacing between adjacent POD values (y-values) in grid.
    :return: success_ratio_matrix: M-by-N numpy array of success ratios.
        Success ratio increases while traveling right along a row.
    :return: pod_matrix: M-by-N numpy array of POD values.  POD increases while
        traveling up a column.
    """

    error_checking.assert_is_greater(success_ratio_spacing, 0.)
    error_checking.assert_is_less_than(success_ratio_spacing, 1.)
    error_checking.assert_is_greater(pod_spacing, 0.)
    error_checking.assert_is_less_than(pod_spacing, 1.)

    num_success_ratios = int(numpy.ceil(1. / success_ratio_spacing))
    num_pod_values = int(numpy.ceil(1. / pod_spacing))
    success_ratio_spacing = 1. / num_success_ratios
    pod_spacing = 1. / num_pod_values

    unique_success_ratios, unique_pod_values = grids.get_xy_grid_points(
        x_min_metres=success_ratio_spacing / 2, y_min_metres=pod_spacing / 2,
        x_spacing_metres=success_ratio_spacing, y_spacing_metres=pod_spacing,
        num_rows=num_pod_values, num_columns=num_success_ratios)
    return grids.xy_vectors_to_matrices(
        unique_success_ratios, unique_pod_values[::-1])


def frequency_bias_from_sr_and_pod(success_ratio_array, pod_array):
    """Computes frequency bias from success ratio and POD.

    POD = probability of detection

    :param success_ratio_array: numpy array (any shape) of success ratios.
    :param pod_array: numpy array (same shape) of POD values.
    :return: frequency_bias_array: numpy array (same shape) of frequency biases.
    """

    error_checking.assert_is_numpy_array(success_ratio_array)
    error_checking.assert_is_geq_numpy_array(success_ratio_array, 0.)
    error_checking.assert_is_leq_numpy_array(success_ratio_array, 1.)

    success_ratio_dimensions = numpy.asarray(success_ratio_array.shape)
    error_checking.assert_is_numpy_array(
        pod_array, exact_dimensions=success_ratio_dimensions)
    error_checking.assert_is_geq_numpy_array(pod_array, 0.)
    error_checking.assert_is_leq_numpy_array(pod_array, 1.)

    return pod_array / success_ratio_array


def csi_from_sr_and_pod(success_ratio_array, pod_array):
    """Computes CSI (critical success index) from success ratio and POD.

    POD = probability of detection

    :param success_ratio_array: numpy array (any shape) of success ratios.
    :param pod_array: numpy array (same shape) of POD values.
    :return: csi_array: numpy array (same shape) of CSI values.
    """

    error_checking.assert_is_numpy_array(success_ratio_array)
    error_checking.assert_is_geq_numpy_array(
        success_ratio_array, 0., allow_nan=True)
    error_checking.assert_is_leq_numpy_array(
        success_ratio_array, 1., allow_nan=True)

    success_ratio_dimensions = numpy.asarray(success_ratio_array.shape)
    error_checking.assert_is_numpy_array(
        pod_array, exact_dimensions=success_ratio_dimensions)
    error_checking.assert_is_geq_numpy_array(pod_array, 0., allow_nan=True)
    error_checking.assert_is_leq_numpy_array(pod_array, 1., allow_nan=True)

    return (success_ratio_array ** -1 + pod_array ** -1 - 1.) ** -1


def get_points_in_reliability_curve(
        forecast_probabilities=None, observed_labels=None,
        num_forecast_bins=DEFAULT_NUM_BINS_FOR_RELIABILITY_CURVE):
    """Determines points in reliability curve.

    B = number of forecast bins

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :param num_forecast_bins: Number of bins in which to discretize forecast
        probabilities.
    :return: mean_forecast_prob_by_bin: length-B numpy array of mean forecast
        probabilities.
    :return: mean_observed_label_by_bin: length-B numpy array of mean observed
        labels (conditional event frequencies).
    :return: num_examples_by_bin: length-B numpy array with number of examples
        in each bin.
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)

    bin_index_by_example = _split_forecast_probs_into_bins(
        forecast_probabilities, num_forecast_bins)

    mean_forecast_prob_by_bin = numpy.full(num_forecast_bins, numpy.nan)
    mean_observed_label_by_bin = numpy.full(num_forecast_bins, numpy.nan)
    num_examples_by_bin = numpy.full(num_forecast_bins, -1, dtype=int)

    for i in range(num_forecast_bins):
        these_example_indices = numpy.where(bin_index_by_example == i)[0]

        num_examples_by_bin[i] = len(these_example_indices)
        mean_forecast_prob_by_bin[i] = numpy.mean(
            forecast_probabilities[these_example_indices])
        mean_observed_label_by_bin[i] = numpy.mean(
            observed_labels[these_example_indices].astype(float))

    return (mean_forecast_prob_by_bin, mean_observed_label_by_bin,
            num_examples_by_bin)


def bootstrap_reliability_curve(
        forecast_probabilities=None, observed_labels=None,
        num_forecast_bins=DEFAULT_NUM_BINS_FOR_RELIABILITY_CURVE,
        num_bootstrap_iters=DEFAULT_NUM_BOOTSTRAP_ITERS,
        confidence_level=DEFAULT_BOOTSTRAP_CONFIDENCE_LEVEL):
    """Bootstrapped version of get_points_in_reliability_curve.

    B = number of forecast bins (same for top, middle, and bottom of confidence
        interval).

    :param forecast_probabilities: See documentation for
        _check_forecast_probs_and_observed_labels.
    :param observed_labels: See doc for
        _check_forecast_probs_and_observed_labels.
    :param num_forecast_bins: Number of bins in which to discretize forecast
        probabilities.
    :param num_bootstrap_iters: Number of bootstrapping iterations (number of
        samples to draw from full set of forecast-observation pairs).
    :param confidence_level: Confidence level.  Will be used to create
        confidence interval ("envelope") for reliability curve.
    :return: reliability_dict_bottom: Dictionary with the following keys.
    reliability_dict_bottom['mean_forecast_prob_by_bin']: length-B numpy array
        of mean forecast probabilities for bottom of envelope (confidence
        interval).
    reliability_dict_bottom['mean_observed_label_by_bin']: Same but for observed
        labels (conditional event frequencies).
    reliability_dict_bottom['brier_skill_score']: Brier skill score.
    reliability_dict_bottom['brier_score']: Brier score.
    reliability_dict_bottom['reliability']: Reliability.
    reliability_dict_bottom['resolution']: Resolution.

    :return: reliability_dict_mean: Same as reliability_dict_bottom, but for
        middle of envelope (confidence interval).
    :return: reliability_dict_top: Same as reliability_dict_bottom, but for top
        of envelope (confidence interval).
    :return: num_examples_by_bin: length-B numpy array with number of examples
        in each bin.
    """

    _check_forecast_probs_and_observed_labels(
        forecast_probabilities, observed_labels)
    bin_index_by_example = _split_forecast_probs_into_bins(
        forecast_probabilities, num_forecast_bins)

    num_examples_by_bin = numpy.full(num_forecast_bins, -1, dtype=int)
    for i in range(num_forecast_bins):
        num_examples_by_bin[i] = len(numpy.where(bin_index_by_example == i)[0])

    mean_forecast_prob_matrix = numpy.full(
        (num_forecast_bins, num_bootstrap_iters), numpy.nan)
    mean_observed_label_matrix = numpy.full(
        (num_forecast_bins, num_bootstrap_iters), numpy.nan)
    brier_skill_scores = numpy.full(num_bootstrap_iters, numpy.nan)
    brier_scores = numpy.full(num_bootstrap_iters, numpy.nan)
    reliabilities = numpy.full(num_bootstrap_iters, numpy.nan)
    resolutions = numpy.full(num_bootstrap_iters, numpy.nan)

    for j in range(num_bootstrap_iters):
        _, these_sample_indices = bootstrapping.draw_sample(
            forecast_probabilities)
        these_num_examples_by_bin = numpy.full(num_forecast_bins, -1, dtype=int)

        for i in range(num_forecast_bins):
            these_example_indices = numpy.where(
                bin_index_by_example[these_sample_indices] == i)[0]
            these_example_indices = these_sample_indices[these_example_indices]

            mean_forecast_prob_matrix[i, j] = numpy.mean(
                forecast_probabilities[these_example_indices])
            mean_observed_label_matrix[i, j] = numpy.mean(
                observed_labels[these_example_indices].astype(float))
            these_num_examples_by_bin[i] = len(these_example_indices)

        this_bss_dictionary = get_brier_skill_score(
            mean_forecast_prob_by_bin=mean_forecast_prob_matrix[:, j],
            mean_observed_label_by_bin=mean_observed_label_matrix[:, j],
            num_examples_by_bin=these_num_examples_by_bin,
            climatology=numpy.mean(
                observed_labels[these_sample_indices].astype(float)))

        brier_skill_scores[j] = this_bss_dictionary[BRIER_SKILL_SCORE_KEY]
        brier_scores[j] = this_bss_dictionary[BRIER_SCORE_KEY]
        reliabilities[j] = this_bss_dictionary[RELIABILITY_KEY]
        resolutions[j] = this_bss_dictionary[RESOLUTION_KEY]

    reliability_dict_bottom = {
        MEAN_FORECAST_PROB_BY_BIN_KEY: numpy.full(num_forecast_bins, numpy.nan),
        MEAN_OBSERVED_LABEL_BY_BIN_KEY: numpy.full(num_forecast_bins, numpy.nan)
    }
    reliability_dict_top = copy.deepcopy(reliability_dict_bottom)
    reliability_dict_mean = copy.deepcopy(reliability_dict_bottom)

    for i in range(num_forecast_bins):
        (reliability_dict_top[MEAN_FORECAST_PROB_BY_BIN_KEY][i],
         reliability_dict_bottom[MEAN_FORECAST_PROB_BY_BIN_KEY][i]) = (
             bootstrapping.get_confidence_interval(
                 mean_forecast_prob_matrix[i, :], confidence_level))

        (reliability_dict_bottom[MEAN_OBSERVED_LABEL_BY_BIN_KEY][i],
         reliability_dict_top[MEAN_OBSERVED_LABEL_BY_BIN_KEY][i]) = (
             bootstrapping.get_confidence_interval(
                 mean_observed_label_matrix[i, :], confidence_level))

    reliability_dict_mean[MEAN_FORECAST_PROB_BY_BIN_KEY] = numpy.nanmean(
        mean_forecast_prob_matrix, axis=1)
    reliability_dict_mean[MEAN_OBSERVED_LABEL_BY_BIN_KEY] = numpy.nanmean(
        mean_observed_label_matrix, axis=1)

    (reliability_dict_bottom[BRIER_SKILL_SCORE_KEY],
     reliability_dict_top[BRIER_SKILL_SCORE_KEY]) = (
         bootstrapping.get_confidence_interval(
             brier_skill_scores, confidence_level))
    (reliability_dict_bottom[BRIER_SCORE_KEY],
     reliability_dict_top[BRIER_SCORE_KEY]) = (
         bootstrapping.get_confidence_interval(brier_scores, confidence_level))
    (reliability_dict_bottom[RELIABILITY_KEY],
     reliability_dict_top[RELIABILITY_KEY]) = (
         bootstrapping.get_confidence_interval(reliabilities, confidence_level))
    (reliability_dict_bottom[RESOLUTION_KEY],
     reliability_dict_top[RESOLUTION_KEY]) = (
         bootstrapping.get_confidence_interval(resolutions, confidence_level))

    reliability_dict_mean[BRIER_SKILL_SCORE_KEY] = numpy.nanmean(
        brier_skill_scores)
    reliability_dict_mean[BRIER_SCORE_KEY] = numpy.nanmean(brier_scores)
    reliability_dict_mean[RELIABILITY_KEY] = numpy.nanmean(reliabilities)
    reliability_dict_mean[RESOLUTION_KEY] = numpy.nanmean(resolutions)

    return (reliability_dict_bottom,
            reliability_dict_mean,
            reliability_dict_top,
            num_examples_by_bin)


def get_brier_skill_score(
        mean_forecast_prob_by_bin=None, mean_observed_label_by_bin=None,
        num_examples_by_bin=None, climatology=None):
    """Computes Brier skill score.

    B = number of forecast bins

    All output variables are defined in Lagerquist et al. (2017).

    :param mean_forecast_prob_by_bin: length-B numpy array of mean forecast
        probabilities.
    :param mean_observed_label_by_bin: length-B numpy array of mean observed
        labels (conditional event frequencies).
    :param num_examples_by_bin: length-B numpy array with number of examples
        in each bin.
    :param climatology: Climatology, or overall frequency of event (label = 1).
    :return: bss_dict: Dictionary with the following keys.
    bss_dict['brier_skill_score']: Brier skill score.
    bss_dict['brier_score']: Brier score.
    bss_dict['reliability']: Reliability.
    bss_dict['resolution']: Resolution.
    bss_dict['uncertainty']: Uncertainty.
    """

    error_checking.assert_is_numpy_array(
        mean_forecast_prob_by_bin, num_dimensions=1)
    error_checking.assert_is_geq_numpy_array(
        mean_forecast_prob_by_bin, 0., allow_nan=True)
    error_checking.assert_is_leq_numpy_array(
        mean_forecast_prob_by_bin, 1., allow_nan=True)

    num_forecast_bins = len(mean_forecast_prob_by_bin)
    error_checking.assert_is_numpy_array(
        mean_observed_label_by_bin,
        exact_dimensions=numpy.array([num_forecast_bins]))
    error_checking.assert_is_geq_numpy_array(
        mean_observed_label_by_bin, 0., allow_nan=True)
    error_checking.assert_is_leq_numpy_array(
        mean_observed_label_by_bin, 1., allow_nan=True)

    error_checking.assert_is_numpy_array(
        num_examples_by_bin, exact_dimensions=numpy.array([num_forecast_bins]))
    error_checking.assert_is_integer_numpy_array(num_examples_by_bin)
    error_checking.assert_is_geq_numpy_array(num_examples_by_bin, 0)

    error_checking.assert_is_geq(climatology, 0.)
    error_checking.assert_is_leq(climatology, 1.)

    uncertainty = climatology * (1. - climatology)
    reliability = (numpy.nansum(num_examples_by_bin * (
        mean_forecast_prob_by_bin - mean_observed_label_by_bin) ** 2) /
                   numpy.sum(num_examples_by_bin))
    resolution = (numpy.nansum(num_examples_by_bin * (
        mean_observed_label_by_bin - climatology) ** 2) /
                  numpy.sum(num_examples_by_bin))
    brier_score = uncertainty + reliability - resolution

    try:
        brier_skill_score = (resolution - reliability) / uncertainty
    except ZeroDivisionError:
        brier_skill_score = numpy.nan

    return {BRIER_SKILL_SCORE_KEY: brier_skill_score,
            BRIER_SCORE_KEY: brier_score,
            RELIABILITY_KEY: reliability, RESOLUTION_KEY: resolution,
            UNCERTAINTY_KEY: uncertainty}


def get_perfect_reliability_curve():
    """Returns points in perfect reliability curve.

    :return: mean_forecast_prob_by_bin: length-2 numpy array of mean forecast
        probabilities.
    :return: mean_observed_label_by_bin: length-2 numpy array of mean observed
        labels (conditional event frequencies).
    """

    return numpy.array([0., 1.]), numpy.array([0., 1.])


def get_no_skill_reliability_curve(mean_observed_label):
    """Returns points in no-skill reliability curve.

    This is a reliability curve with Brier skill score (BSS) = 0.

    :param mean_observed_label: Mean observed label (event frequency) for the
        full dataset (not just for one forecast bin).
    :return: x_values: length-2 numpy array of x-values in no-skill line.
    :return: y_values: length-2 numpy array of y-values in no-skill line.
    """

    error_checking.assert_is_geq(mean_observed_label, 0.)
    error_checking.assert_is_leq(mean_observed_label, 1.)

    y_values = numpy.array(
        [mean_observed_label, 1 + mean_observed_label]) / 2
    return numpy.array([0., 1.]), y_values


def get_skill_areas_in_reliability_curve(mean_observed_label):
    """Returns positive-skill areas (polygons) for reliability curve.

    BSS (Brier skill score) > 0 inside these polygons.

    :param mean_observed_label: Mean observed label (event frequency) for the
        full dataset (not just for one forecast bin).
    :return: x_vertices_for_left_skill_area: length-5 numpy array with x-
        coordinates of vertices in left-skill area (where x <=
        mean_observed_label).
    :return: y_vertices_for_left_skill_area: Same but for y-coordinates.
    :return: x_vertices_for_right_skill_area: length-5 numpy array with x-
        coordinates of vertices in right-skill area (where x >=
        mean_observed_label).
    :return: y_vertices_for_right_skill_area: Same but for y-coordinates.
    """

    x_vertices_for_left_skill_area = numpy.array(
        [0., mean_observed_label, mean_observed_label, 0., 0.])
    y_vertices_for_left_skill_area = numpy.array(
        [0., 0., mean_observed_label, mean_observed_label / 2, 0.])

    x_vertices_for_right_skill_area = numpy.array(
        [mean_observed_label, 1., 1., mean_observed_label, mean_observed_label])
    y_vertices_for_right_skill_area = numpy.array(
        [mean_observed_label, (1 + mean_observed_label) / 2,
         1., 1., mean_observed_label])

    return (x_vertices_for_left_skill_area, y_vertices_for_left_skill_area,
            x_vertices_for_right_skill_area, y_vertices_for_right_skill_area)


def get_climatology_line_for_reliability_curve(mean_observed_label):
    """Returns climatology line for reliability curve.

    "Climatology" is another term for mean observed label.  The "climatology
    line" is a vertical line at x = climatology.

    :param mean_observed_label: Mean observed label (event frequency) for the
        full dataset (not just for one forecast bin).
    :return: x_values: length-2 numpy array of x-values in climatology line.
    :return: y_values: length-2 numpy array of y-values in climatology line.
    """

    return numpy.full(2, mean_observed_label), numpy.array([0., 1.])


def get_no_resolution_line_for_reliability_curve(mean_observed_label):
    """Returns no-resolution line for reliability curve.

    This is a horizontal line at y = mean observed label.

    :param mean_observed_label: Mean observed label (event frequency) for the
        full dataset (not just for one forecast bin).
    :return: x_values: length-2 numpy array of x-values in no-resolution line.
    :return: y_values: length-2 numpy array of y-values in no-resolution line.
    """

    return numpy.array([0., 1.]), numpy.full(2, mean_observed_label)
