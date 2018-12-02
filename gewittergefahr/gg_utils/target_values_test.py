"""Unit tests for target_values.py."""

import unittest
import numpy
import pandas
from gewittergefahr.gg_utils import linkage
from gewittergefahr.gg_utils import target_values
from gewittergefahr.gg_utils import storm_tracking_utils as tracking_utils

TOLERANCE = 1e-6

# The following constants are used to test _find_storms_near_end_of_period.
MAX_LEAD_TIME_SEC = 3600

THESE_END_TIMES_UNIX_SEC = numpy.array(
    [10000, 10000, 10000, 10000, 20000, 20000, 20000, 20000], dtype=int)
THESE_VALID_TIMES_UNIX_SEC = numpy.array(
    [2500, 5000, 7500, 10000, 12500, 15000, 16400, 17500], dtype=int)

THIS_DICT = {
    tracking_utils.TRACKING_END_TIME_COLUMN: THESE_END_TIMES_UNIX_SEC,
    tracking_utils.TIME_COLUMN: THESE_VALID_TIMES_UNIX_SEC
}
STORM_TO_EVENTS_TABLE_END_OF_PERIOD = pandas.DataFrame.from_dict(THIS_DICT)

END_OF_PERIOD_INDICES = numpy.array([2, 3, 7], dtype=int)

# The following constants are used to test _find_dead_storms.
MIN_LEAD_TIME_FOR_DEAD_SEC = 3600

THIS_DICT = {
    tracking_utils.CELL_END_TIME_COLUMN: THESE_END_TIMES_UNIX_SEC,
    tracking_utils.TIME_COLUMN: THESE_VALID_TIMES_UNIX_SEC
}
STORM_TO_EVENTS_TABLE_WITH_DEAD = pandas.DataFrame.from_dict(THIS_DICT)

DEAD_STORM_INDICES = numpy.array([2, 3, 7], dtype=int)

# The following constants are used to test target_params_to_name.
MIN_LEAD_TIME_SEC = 900
MIN_LINK_DISTANCE_METRES = 1.
MAX_LINK_DISTANCE_METRES = 5000.
WIND_SPEED_PERCENTILE_LEVEL = 97.5
WIND_SPEED_CUTOFFS_KT = numpy.array([10, 20, 30, 40, 50], dtype=float)

WIND_REGRESSION_NAME = (
    'wind-speed-m-s01_percentile=097.5_lead-time=0900-3600sec_'
    'distance=00001-05000m')
WIND_CLASSIFICATION_NAME = (
    'wind-speed_percentile=097.5_lead-time=0900-3600sec_distance=00001-05000m'
    '_cutoffs=10-20-30-40-50kt')
TORNADO_TARGET_NAME = (
    'tornado_lead-time=0900-3600sec_distance=00001-05000m')

WIND_CLASSIFICATION_NAME_0LEAD = (
    'wind-speed_percentile=097.5_lead-time=0000-3600sec_distance=00001-05000m'
    '_cutoffs=10-20-30-40-50kt')

# The following constants are used to test target_name_to_params.
WIND_REGRESSION_PARAM_DICT = {
    target_values.MIN_LEAD_TIME_KEY: MIN_LEAD_TIME_SEC,
    target_values.MAX_LEAD_TIME_KEY: MAX_LEAD_TIME_SEC,
    target_values.MIN_LINKAGE_DISTANCE_KEY: MIN_LINK_DISTANCE_METRES,
    target_values.MAX_LINKAGE_DISTANCE_KEY: MAX_LINK_DISTANCE_METRES,
    target_values.PERCENTILE_LEVEL_KEY: WIND_SPEED_PERCENTILE_LEVEL,
    target_values.WIND_SPEED_CUTOFFS_KEY: None,
    target_values.EVENT_TYPE_KEY: linkage.WIND_EVENT_STRING
}

WIND_CLASSIFICATION_PARAM_DICT = {
    target_values.MIN_LEAD_TIME_KEY: MIN_LEAD_TIME_SEC,
    target_values.MAX_LEAD_TIME_KEY: MAX_LEAD_TIME_SEC,
    target_values.MIN_LINKAGE_DISTANCE_KEY: MIN_LINK_DISTANCE_METRES,
    target_values.MAX_LINKAGE_DISTANCE_KEY: MAX_LINK_DISTANCE_METRES,
    target_values.PERCENTILE_LEVEL_KEY: WIND_SPEED_PERCENTILE_LEVEL,
    target_values.WIND_SPEED_CUTOFFS_KEY: WIND_SPEED_CUTOFFS_KT,
    target_values.EVENT_TYPE_KEY: linkage.WIND_EVENT_STRING
}

TORNADO_PARAM_DICT = {
    target_values.MIN_LEAD_TIME_KEY: MIN_LEAD_TIME_SEC,
    target_values.MAX_LEAD_TIME_KEY: MAX_LEAD_TIME_SEC,
    target_values.MIN_LINKAGE_DISTANCE_KEY: MIN_LINK_DISTANCE_METRES,
    target_values.MAX_LINKAGE_DISTANCE_KEY: MAX_LINK_DISTANCE_METRES,
    target_values.PERCENTILE_LEVEL_KEY: None,
    target_values.WIND_SPEED_CUTOFFS_KEY: None,
    target_values.EVENT_TYPE_KEY: linkage.TORNADO_EVENT_STRING
}

WIND_CLASSIFICATION_PARAM_DICT_0LEAD = {
    target_values.MIN_LEAD_TIME_KEY: 0,
    target_values.MAX_LEAD_TIME_KEY: MAX_LEAD_TIME_SEC,
    target_values.MIN_LINKAGE_DISTANCE_KEY: MIN_LINK_DISTANCE_METRES,
    target_values.MAX_LINKAGE_DISTANCE_KEY: MAX_LINK_DISTANCE_METRES,
    target_values.PERCENTILE_LEVEL_KEY: WIND_SPEED_PERCENTILE_LEVEL,
    target_values.WIND_SPEED_CUTOFFS_KEY: WIND_SPEED_CUTOFFS_KT,
    target_values.EVENT_TYPE_KEY: linkage.WIND_EVENT_STRING
}

# The following constants are used to test find_target_file.
TOP_DIRECTORY_NAME = 'target_values'
FILE_TIME_UNIX_SEC = 1517523991  # 222631 1 Feb 2018
FILE_SPC_DATE_STRING = '20180201'

WIND_FILE_NAME_ONE_TIME = (
    'target_values/2018/20180201/wind_labels_2018-02-01-222631.nc')
WIND_FILE_NAME_ONE_DAY = 'target_values/2018/wind_labels_20180201.nc'
TORNADO_FILE_NAME_ONE_TIME = (
    'target_values/2018/20180201/tornado_labels_2018-02-01-222631.nc')
TORNADO_FILE_NAME_ONE_DAY = 'target_values/2018/tornado_labels_20180201.nc'


def _compare_target_param_dicts(first_dict, second_dict):
    """Compares two dictionaries with target-variable params.

    :param first_dict: First dictionary.
    :param second_dict: Second dictionary.
    :return: are_dicts_equal: Boolean flag.
    """

    exact_keys = [
        target_values.MIN_LEAD_TIME_KEY, target_values.MAX_LEAD_TIME_KEY,
        target_values.EVENT_TYPE_KEY
    ]
    float_keys = [
        target_values.MIN_LINKAGE_DISTANCE_KEY,
        target_values.MAX_LINKAGE_DISTANCE_KEY
    ]

    first_keys = first_dict.keys()
    second_keys = second_dict.keys()
    if set(first_keys) != set(second_keys):
        return False

    for this_key in first_keys:
        if this_key in exact_keys:
            if first_dict[this_key] != second_dict[this_key]:
                return False

        elif this_key in float_keys:
            if not numpy.allclose(first_dict[this_key], second_dict[this_key],
                                  atol=TOLERANCE):
                return False

        else:
            if first_dict[this_key] is None:
                if second_dict[this_key] is not None:
                    return False
            else:
                if not numpy.allclose(first_dict[this_key],
                                      second_dict[this_key], atol=TOLERANCE):
                    return False

    return True


class TargetValuesTests(unittest.TestCase):
    """Each method is a unit test for target_values.py."""

    def test_find_storms_near_end_of_period(self):
        """Ensures correct output from _find_storms_near_end_of_period."""

        these_indices = target_values._find_storms_near_end_of_period(
            storm_to_events_table=STORM_TO_EVENTS_TABLE_END_OF_PERIOD,
            max_lead_time_sec=MAX_LEAD_TIME_SEC)

        self.assertTrue(numpy.array_equal(these_indices, END_OF_PERIOD_INDICES))

    def test_find_dead_storms(self):
        """Ensures correct output from _find_dead_storms."""

        these_indices = target_values._find_dead_storms(
            storm_to_events_table=STORM_TO_EVENTS_TABLE_WITH_DEAD,
            min_lead_time_sec=MIN_LEAD_TIME_FOR_DEAD_SEC)

        self.assertTrue(numpy.array_equal(these_indices, DEAD_STORM_INDICES))

    def test_target_params_to_name_wind_regression(self):
        """Ensures correct output from target_params_to_name.

        In this case, target variable is based on wind-speed regression.
        """

        this_target_name = target_values.target_params_to_name(
            min_lead_time_sec=MIN_LEAD_TIME_SEC,
            max_lead_time_sec=MAX_LEAD_TIME_SEC,
            min_link_distance_metres=MIN_LINK_DISTANCE_METRES,
            max_link_distance_metres=MAX_LINK_DISTANCE_METRES,
            wind_speed_percentile_level=WIND_SPEED_PERCENTILE_LEVEL)

        self.assertTrue(this_target_name == WIND_REGRESSION_NAME)

    def test_target_params_to_name_wind_classifn(self):
        """Ensures correct output from target_params_to_name.

        In this case, target variable is based on wind-speed classification.
        """

        this_target_name = target_values.target_params_to_name(
            min_lead_time_sec=MIN_LEAD_TIME_SEC,
            max_lead_time_sec=MAX_LEAD_TIME_SEC,
            min_link_distance_metres=MIN_LINK_DISTANCE_METRES,
            max_link_distance_metres=MAX_LINK_DISTANCE_METRES,
            wind_speed_percentile_level=WIND_SPEED_PERCENTILE_LEVEL,
            wind_speed_cutoffs_kt=WIND_SPEED_CUTOFFS_KT)

        self.assertTrue(this_target_name == WIND_CLASSIFICATION_NAME)

    def test_target_params_to_name_wind_classifn_0lead(self):
        """Ensures correct output from target_params_to_name.

        In this case, target variable is based on wind-speed classification and
        minimum lead time is zero.
        """

        this_target_name = target_values.target_params_to_name(
            min_lead_time_sec=0,
            max_lead_time_sec=MAX_LEAD_TIME_SEC,
            min_link_distance_metres=MIN_LINK_DISTANCE_METRES,
            max_link_distance_metres=MAX_LINK_DISTANCE_METRES,
            wind_speed_percentile_level=WIND_SPEED_PERCENTILE_LEVEL,
            wind_speed_cutoffs_kt=WIND_SPEED_CUTOFFS_KT)

        self.assertTrue(this_target_name == WIND_CLASSIFICATION_NAME_0LEAD)

    def test_target_params_to_name_tornado(self):
        """Ensures correct output from target_params_to_name.

        In this case, target variable is based on tornado occurrence.
        """

        this_target_name = target_values.target_params_to_name(
            min_lead_time_sec=MIN_LEAD_TIME_SEC,
            max_lead_time_sec=MAX_LEAD_TIME_SEC,
            min_link_distance_metres=MIN_LINK_DISTANCE_METRES,
            max_link_distance_metres=MAX_LINK_DISTANCE_METRES)

        self.assertTrue(this_target_name == TORNADO_TARGET_NAME)

    def test_target_name_to_params_wind_regression(self):
        """Ensures correct output from target_name_to_params.

        In this case, target variable is based on wind-speed regression.
        """

        this_dict = target_values.target_name_to_params(WIND_REGRESSION_NAME)
        self.assertTrue(_compare_target_param_dicts(
            this_dict, WIND_REGRESSION_PARAM_DICT))

    def test_target_name_to_params_wind_classifn(self):
        """Ensures correct output from target_name_to_params.

        In this case, target variable is based on wind-speed classification.
        """

        this_dict = target_values.target_name_to_params(
            WIND_CLASSIFICATION_NAME)
        self.assertTrue(_compare_target_param_dicts(
            this_dict, WIND_CLASSIFICATION_PARAM_DICT))

    def test_target_name_to_params_wind_classifn_0lead(self):
        """Ensures correct output from target_name_to_params.

        In this case, target variable is based on wind-speed classification and
        minimum lead time is zero.
        """

        this_dict = target_values.target_name_to_params(
            WIND_CLASSIFICATION_NAME_0LEAD)
        self.assertTrue(_compare_target_param_dicts(
            this_dict, WIND_CLASSIFICATION_PARAM_DICT_0LEAD))

    def test_target_name_to_params_tornado(self):
        """Ensures correct output from target_name_to_params.

        In this case, target variable is based on tornado occurrence.
        """

        this_dict = target_values.target_name_to_params(TORNADO_TARGET_NAME)
        self.assertTrue(_compare_target_param_dicts(
            this_dict, TORNADO_PARAM_DICT))

    def test_find_target_file_wind_one_time(self):
        """Ensures correct output from find_target_file.

        In this case, target variable is based on wind speed and file contains
        one time step.
        """

        this_file_name = target_values.find_target_file(
            top_directory_name=TOP_DIRECTORY_NAME,
            event_type_string=linkage.WIND_EVENT_STRING,
            spc_date_string=FILE_SPC_DATE_STRING,
            unix_time_sec=FILE_TIME_UNIX_SEC, raise_error_if_missing=False)

        self.assertTrue(this_file_name == WIND_FILE_NAME_ONE_TIME)

    def test_find_target_file_wind_one_day(self):
        """Ensures correct output from find_target_file.

        In this case, target variable is based on wind speed and file contains
        one SPC date.
        """

        this_file_name = target_values.find_target_file(
            top_directory_name=TOP_DIRECTORY_NAME,
            event_type_string=linkage.WIND_EVENT_STRING,
            spc_date_string=FILE_SPC_DATE_STRING,
            unix_time_sec=None, raise_error_if_missing=False)

        self.assertTrue(this_file_name == WIND_FILE_NAME_ONE_DAY)

    def test_find_target_file_tornado_one_time(self):
        """Ensures correct output from find_target_file.

        In this case, target variable is based on tornado occurrence and file
        contains one time step.
        """

        this_file_name = target_values.find_target_file(
            top_directory_name=TOP_DIRECTORY_NAME,
            event_type_string=linkage.TORNADO_EVENT_STRING,
            spc_date_string=FILE_SPC_DATE_STRING,
            unix_time_sec=FILE_TIME_UNIX_SEC, raise_error_if_missing=False)

        self.assertTrue(this_file_name == TORNADO_FILE_NAME_ONE_TIME)

    def test_find_target_file_tornado_one_day(self):
        """Ensures correct output from find_target_file.

        In this case, target variable is based on tornado occurrence and file
        contains one SPC date.
        """

        this_file_name = target_values.find_target_file(
            top_directory_name=TOP_DIRECTORY_NAME,
            event_type_string=linkage.TORNADO_EVENT_STRING,
            spc_date_string=FILE_SPC_DATE_STRING,
            unix_time_sec=None, raise_error_if_missing=False)

        self.assertTrue(this_file_name == TORNADO_FILE_NAME_ONE_DAY)


if __name__ == '__main__':
    unittest.main()