"""Unit tests for echo_top_tracking.py."""

import copy
import unittest
import numpy
from gewittergefahr.gg_utils import echo_top_tracking
from gewittergefahr.gg_utils import temporal_tracking
from gewittergefahr.gg_utils import radar_utils
from gewittergefahr.gg_utils import projections

TOLERANCE = 1e-6
RELATIVE_DISTANCE_TOLERANCE = 0.015

# The following constants are used to test _find_local_maxima.
RADAR_MATRIX = numpy.array([
    [0, numpy.nan, 3, 4, numpy.nan, 6],
    [7, 8, 9, 10, numpy.nan, numpy.nan],
    [13, 14, numpy.nan, numpy.nan, 17, 18],
    [19, 20, numpy.nan, numpy.nan, numpy.nan, 24],
    [numpy.nan, numpy.nan, 27, 28, 29, 30]
])

RADAR_METADATA_DICT = {
    radar_utils.NW_GRID_POINT_LAT_COLUMN: 35.,
    radar_utils.NW_GRID_POINT_LNG_COLUMN: 95.,
    radar_utils.LAT_SPACING_COLUMN: 0.01,
    radar_utils.LNG_SPACING_COLUMN: 0.02
}

NEIGH_HALF_WIDTH_PIXELS = 1

LOCAL_MAX_ROWS = numpy.array([0, 4], dtype=int)
LOCAL_MAX_COLUMNS = numpy.array([5, 5], dtype=int)
LOCAL_MAX_LATITUDES_DEG = numpy.array([34.96, 35])
LOCAL_MAX_LONGITUDES_DEG = numpy.array([95.1, 95.1])
LOCAL_MAX_VALUES = numpy.array([30, 6], dtype=float)

LOCAL_MAX_DICT_LATLNG = {
    temporal_tracking.LATITUDES_KEY: LOCAL_MAX_LATITUDES_DEG,
    temporal_tracking.LONGITUDES_KEY: LOCAL_MAX_LONGITUDES_DEG,
    echo_top_tracking.MAX_VALUES_KEY: LOCAL_MAX_VALUES
}

# The following constants are used to test _remove_redundant_local_maxima.
SMALL_INTERMAX_DISTANCE_METRES = 1000.
LARGE_INTERMAX_DISTANCE_METRES = 10000.

PROJECTION_OBJECT = projections.init_azimuthal_equidistant_projection(
    central_latitude_deg=35., central_longitude_deg=95.)

LOCAL_MAX_X_COORDS_METRES, LOCAL_MAX_Y_COORDS_METRES = (
    projections.project_latlng_to_xy(
        LOCAL_MAX_LATITUDES_DEG, LOCAL_MAX_LONGITUDES_DEG,
        projection_object=PROJECTION_OBJECT,
        false_easting_metres=0., false_northing_metres=0.)
)

LOCAL_MAX_DICT_SMALL_DISTANCE = {
    temporal_tracking.LATITUDES_KEY: LOCAL_MAX_LATITUDES_DEG,
    temporal_tracking.LONGITUDES_KEY: LOCAL_MAX_LONGITUDES_DEG,
    echo_top_tracking.MAX_VALUES_KEY: LOCAL_MAX_VALUES,
    temporal_tracking.X_COORDS_KEY: LOCAL_MAX_X_COORDS_METRES,
    temporal_tracking.Y_COORDS_KEY: LOCAL_MAX_Y_COORDS_METRES
}

LOCAL_MAX_DICT_LARGE_DISTANCE = {
    temporal_tracking.LATITUDES_KEY: LOCAL_MAX_LATITUDES_DEG[:-1],
    temporal_tracking.LONGITUDES_KEY: LOCAL_MAX_LONGITUDES_DEG[:-1],
    echo_top_tracking.MAX_VALUES_KEY: LOCAL_MAX_VALUES[:-1],
    temporal_tracking.X_COORDS_KEY: LOCAL_MAX_X_COORDS_METRES[:-1],
    temporal_tracking.Y_COORDS_KEY: LOCAL_MAX_Y_COORDS_METRES[:-1]
}

# The following constants are used to test _local_maxima_to_regions.
MIN_ECHO_TOP_KM = 5.

TOY_ECHO_TOP_MATRIX_KM = numpy.array([
    [6, 6, 6, 0, 0, 0, 6, 0, 6, 0, 0, 0],
    [0, 6, 6, 6, 6, 0, 0, 0, 0, 0, 0, 0],
    [0, 6, 6, 6, 6, 6, 0, 0, 0, 0, 0, 0],
    [0, 0, 6, 6, 6, 6, 0, 6, 6, 6, 6, 0],
    [0, 0, 0, 0, 6, 6, 6, 6, 0, 6, 6, 6],
    [0, 0, 0, 6, 6, 6, 6, 0, 6, 6, 6, 6],
    [0, 0, 0, 0, 0, 6, 6, 0, 0, 0, 6, 6],
    [0, 0, 0, 0, 0, 0, 0, 6, 0, 6, 6, 0]
], dtype=float)

TOY_RADAR_LATITUDES_DEG = numpy.array([
    53.5, 53.49, 53.48, 53.47, 53.46, 53.45, 53.44, 53.43
])
TOY_RADAR_LONGITUDES_DEG = numpy.array([
    246.5, 246.52, 246.54, 246.56, 246.58, 246.6, 246.62, 246.64, 246.66,
    246.68, 246.7, 246.72
])

TOY_LOCAL_MAX_DICT = {
    temporal_tracking.LATITUDES_KEY:
        numpy.array([53.479, 53.461, 53.45, 53.5, 53.501]),
    temporal_tracking.LONGITUDES_KEY:
        numpy.array([246.541, 246.619, 246.681, 246.62, 246.659])
}

TOY_RADAR_TO_REGION_MATRIX = numpy.array([
    [1, 1, 1, 0, 0, 0, 4, 0, 5, 0, 0, 0],
    [0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 2, 0, 0, 0, 0, 0, 0],
    [0, 0, 1, 1, 1, 2, 0, 2, 3, 3, 3, 0],
    [0, 0, 0, 0, 2, 2, 2, 2, 0, 3, 3, 3],
    [0, 0, 0, 2, 2, 2, 2, 0, 3, 3, 3, 3],
    [0, 0, 0, 0, 0, 2, 2, 0, 0, 0, 3, 3],
    [0, 0, 0, 0, 0, 0, 0, 2, 0, 3, 3, 0]
], dtype=int)

TOY_RADAR_TO_REGION_MATRIX -= 1

# The following constants are used to test _remove_small_polygons.
THIS_LIST_OF_ROW_ARRAYS = [
    numpy.array([0, 0, 0, 0, 1, 1, 2, 2, 2], dtype=int),
    numpy.array([-5, -4, -3], dtype=int),
    numpy.array([0, 1, 1, 2, 3, 5, 8, 13, 6, 6, 6], dtype=int)
]

LOCAL_MAX_DICT_WITH_SMALL = {
    temporal_tracking.GRID_POINT_ROWS_KEY: THIS_LIST_OF_ROW_ARRAYS,
    temporal_tracking.LATITUDES_KEY: numpy.array([51.1, 53.5, 60]),
    temporal_tracking.LONGITUDES_KEY: numpy.array([246, 246.5, 250])
}

MIN_POLYGON_SIZE_PIXELS = 5
THIS_LIST_OF_ROW_ARRAYS = [
    numpy.array([0, 0, 0, 0, 1, 1, 2, 2, 2], dtype=int),
    numpy.array([0, 1, 1, 2, 3, 5, 8, 13, 6, 6, 6], dtype=int)
]

LOCAL_MAX_DICT_WITHOUT_SMALL = {
    temporal_tracking.GRID_POINT_ROWS_KEY: THIS_LIST_OF_ROW_ARRAYS,
    temporal_tracking.LATITUDES_KEY: numpy.array([51.1, 60]),
    temporal_tracking.LONGITUDES_KEY: numpy.array([246, 250])
}

# The following constants are used to test _velocities_latlng_to_xy.
START_LATITUDES_DEG = numpy.array([
    49.5, 58.3, 42.4, 58.5, 39.3, 46.4, 44.9, 58, 47.4, 32.5, 54.7, 53.1
])
START_LONGITUDES_DEG = numpy.array([
    259.6, 258.7, 249.8, 241.1, 241, 250.3, 248.2, 239.7, 236.7, 249.2, 234.1,
    235.5
])
EAST_VELOCITIES_M_S01 = numpy.array([
    -7.9, -7.9, -10.4, -11.6, -5.1, -1.3, -9.6, -6.6, 13.4, -7.7, -4.7, 1
])
NORTH_VELOCITIES_M_S01 = numpy.array([
    -11.3, 12.8, -1, 2.7, -13.7, 8.5, -8.3, 2.2, -8.1, -2.6, 13.5, -12.1
])

# The following constants are used to test _radar_times_to_tracking_periods.
FIRST_MAX_TIME_INTERVAL_SEC = 10
SECOND_MAX_TIME_INTERVAL_SEC = 5
RADAR_TIMES_UNIX_SEC = numpy.array([0, 10, 15], dtype=int)

FIRST_TRACKING_START_TIMES_UNIX_SEC = numpy.array([0], dtype=int)
FIRST_TRACKING_END_TIMES_UNIX_SEC = numpy.array([15], dtype=int)
SECOND_TRACKING_START_TIMES_UNIX_SEC = numpy.array([0, 10], dtype=int)
SECOND_TRACKING_END_TIMES_UNIX_SEC = numpy.array([0, 15], dtype=int)

# The following constants are used to test _old_to_new_tracking_periods.
OLD_TRACKING_START_TIMES_UNIX_SEC = numpy.array(
    [-10, 0, 20, 50, 100], dtype=int
)
OLD_TRACKING_END_TIMES_UNIX_SEC = numpy.array([-5, 10, 35, 80, 200], dtype=int)

THIRD_MAX_TIME_INTERVAL_SEC = 15
FOURTH_MAX_TIME_INTERVAL_SEC = 20

FIRST_NEW_START_TIMES_UNIX_SEC = numpy.array([-10, 50, 100], dtype=int)
FIRST_NEW_END_TIMES_UNIX_SEC = numpy.array([35, 80, 200], dtype=int)

SECOND_NEW_START_TIMES_UNIX_SEC = numpy.array([-10, 20, 50, 100], dtype=int)
SECOND_NEW_END_TIMES_UNIX_SEC = numpy.array([10, 35, 80, 200], dtype=int)

THIRD_NEW_START_TIMES_UNIX_SEC = numpy.array([-10, 100], dtype=int)
THIRD_NEW_END_TIMES_UNIX_SEC = numpy.array([80, 200], dtype=int)

FOURTH_NEW_START_TIMES_UNIX_SEC = numpy.array([-10], dtype=int)
FOURTH_NEW_END_TIMES_UNIX_SEC = numpy.array([200], dtype=int)


def _compare_local_max_dicts(first_local_max_dict, second_local_max_dict):
    """Compares two dictionaries with local maxima.

    :param first_local_max_dict: First dictionary.
    :param second_local_max_dict: Second dictionary.
    :return: are_dicts_equal: Boolean flag.
    """

    first_keys = list(first_local_max_dict.keys())
    second_keys = list(second_local_max_dict.keys())
    if set(first_keys) != set(second_keys):
        return False

    for this_key in first_keys:
        if this_key == temporal_tracking.GRID_POINT_ROWS_KEY:
            first_length = len(first_local_max_dict[this_key])
            second_length = len(second_local_max_dict[this_key])
            if first_length != second_length:
                return False

            for i in range(first_length):
                if not numpy.array_equal(first_local_max_dict[this_key][i],
                                         second_local_max_dict[this_key][i]):
                    return False

        else:
            if not numpy.allclose(first_local_max_dict[this_key],
                                  second_local_max_dict[this_key],
                                  atol=TOLERANCE):
                return False

    return True


class EchoTopTrackingTests(unittest.TestCase):
    """Each method is a unit test for echo_top_tracking.py."""

    def test_find_local_maxima(self):
        """Ensures correct output from _find_local_maxima."""

        this_local_max_dict = echo_top_tracking._find_local_maxima(
            radar_matrix=RADAR_MATRIX, radar_metadata_dict=RADAR_METADATA_DICT,
            neigh_half_width_pixels=NEIGH_HALF_WIDTH_PIXELS)

        these_keys = set(list(this_local_max_dict))
        expected_keys = set(list(LOCAL_MAX_DICT_LATLNG))
        self.assertTrue(these_keys == expected_keys)

        for this_key in these_keys:
            self.assertTrue(numpy.allclose(
                this_local_max_dict[this_key], LOCAL_MAX_DICT_LATLNG[this_key],
                atol=TOLERANCE
            ))

    def test_remove_redundant_local_maxima_small_distance(self):
        """Ensures correct output from _remove_redundant_local_maxima.

        In this case, minimum distance between two maxima is small.
        """

        this_local_max_dict = echo_top_tracking._remove_redundant_local_maxima(
            local_max_dict=copy.deepcopy(LOCAL_MAX_DICT_LATLNG),
            projection_object=PROJECTION_OBJECT,
            min_intermax_distance_metres=SMALL_INTERMAX_DISTANCE_METRES)

        these_keys = set(list(this_local_max_dict))
        expected_keys = set(list(LOCAL_MAX_DICT_SMALL_DISTANCE))
        self.assertTrue(these_keys == expected_keys)

        for this_key in these_keys:
            self.assertTrue(numpy.allclose(
                this_local_max_dict[this_key],
                LOCAL_MAX_DICT_SMALL_DISTANCE[this_key], atol=TOLERANCE
            ))

    def test_remove_redundant_local_maxima_large_distance(self):
        """Ensures correct output from _remove_redundant_local_maxima.

        In this case, minimum distance between two maxima is large.
        """

        this_local_max_dict = echo_top_tracking._remove_redundant_local_maxima(
            local_max_dict=copy.deepcopy(LOCAL_MAX_DICT_LATLNG),
            projection_object=PROJECTION_OBJECT,
            min_intermax_distance_metres=LARGE_INTERMAX_DISTANCE_METRES)

        these_keys = set(list(this_local_max_dict))
        expected_keys = set(list(LOCAL_MAX_DICT_LARGE_DISTANCE))
        self.assertTrue(these_keys == expected_keys)

        for this_key in these_keys:
            self.assertTrue(numpy.allclose(
                this_local_max_dict[this_key],
                LOCAL_MAX_DICT_LARGE_DISTANCE[this_key], atol=TOLERANCE
            ))

    def test_local_maxima_to_regions(self):
        """Ensures correct output from _local_maxima_to_regions."""

        this_region_matrix = echo_top_tracking._local_maxima_to_regions(
            local_max_dict=TOY_LOCAL_MAX_DICT,
            echo_top_matrix_km=TOY_ECHO_TOP_MATRIX_KM,
            min_echo_top_km=MIN_ECHO_TOP_KM,
            radar_latitudes_deg=TOY_RADAR_LATITUDES_DEG,
            radar_longitudes_deg=TOY_RADAR_LONGITUDES_DEG)

        self.assertTrue(numpy.array_equal(
            this_region_matrix, TOY_RADAR_TO_REGION_MATRIX
        ))

    def test_remove_small_polygons_min0(self):
        """Ensures correct output from _remove_small_polygons.

        In this case polygons with >= 0 grid cells should be kept.
        """

        this_local_max_dict = echo_top_tracking._remove_small_polygons(
            local_max_dict=copy.deepcopy(LOCAL_MAX_DICT_WITH_SMALL),
            min_size_pixels=0)

        self.assertTrue(_compare_local_max_dicts(
            this_local_max_dict, LOCAL_MAX_DICT_WITH_SMALL
        ))

    def test_remove_small_polygons_min5(self):
        """Ensures correct output from _remove_small_polygons.

        In this case polygons with >= 5 grid cells should be kept.
        """

        this_local_max_dict = echo_top_tracking._remove_small_polygons(
            local_max_dict=copy.deepcopy(LOCAL_MAX_DICT_WITH_SMALL),
            min_size_pixels=MIN_POLYGON_SIZE_PIXELS)

        self.assertTrue(_compare_local_max_dicts(
            this_local_max_dict, LOCAL_MAX_DICT_WITHOUT_SMALL
        ))

    def test_velocities_latlng_to_xy(self):
        """Ensures correct output from _velocities_latlng_to_xy."""

        these_x_velocities_m_s01, these_y_velocities_m_s01 = (
            echo_top_tracking._velocities_latlng_to_xy(
                east_velocities_m_s01=EAST_VELOCITIES_M_S01,
                north_velocities_m_s01=NORTH_VELOCITIES_M_S01,
                latitudes_deg=START_LATITUDES_DEG,
                longitudes_deg=START_LONGITUDES_DEG)
        )

        speeds_m_s01 = numpy.sqrt(
            EAST_VELOCITIES_M_S01 ** 2 + NORTH_VELOCITIES_M_S01 ** 2
        )

        for i in range(len(speeds_m_s01)):
            self.assertTrue(numpy.isclose(
                these_x_velocities_m_s01[i], EAST_VELOCITIES_M_S01[i],
                atol=0.5 * speeds_m_s01[i]
            ))

            self.assertTrue(numpy.isclose(
                these_y_velocities_m_s01[i], NORTH_VELOCITIES_M_S01[i],
                atol=0.5 * speeds_m_s01[i]
            ))

    def test_radar_times_to_tracking_periods_first(self):
        """Ensures correct output from _radar_times_to_tracking_periods.

        In this case, using first max time interval.
        """

        these_start_times_unix_sec, these_end_times_unix_sec = (
            echo_top_tracking._radar_times_to_tracking_periods(
                radar_times_unix_sec=RADAR_TIMES_UNIX_SEC,
                max_time_interval_sec=FIRST_MAX_TIME_INTERVAL_SEC)
        )

        self.assertTrue(numpy.array_equal(
            these_start_times_unix_sec, FIRST_TRACKING_START_TIMES_UNIX_SEC
        ))
        self.assertTrue(numpy.array_equal(
            these_end_times_unix_sec, FIRST_TRACKING_END_TIMES_UNIX_SEC
        ))

    def test_radar_times_to_tracking_periods_second(self):
        """Ensures correct output from _radar_times_to_tracking_periods.

        In this case, using second max time interval.
        """

        these_start_times_unix_sec, these_end_times_unix_sec = (
            echo_top_tracking._radar_times_to_tracking_periods(
                radar_times_unix_sec=RADAR_TIMES_UNIX_SEC,
                max_time_interval_sec=SECOND_MAX_TIME_INTERVAL_SEC)
        )

        self.assertTrue(numpy.array_equal(
            these_start_times_unix_sec, SECOND_TRACKING_START_TIMES_UNIX_SEC
        ))
        self.assertTrue(numpy.array_equal(
            these_end_times_unix_sec, SECOND_TRACKING_END_TIMES_UNIX_SEC
        ))

    def test_old_to_new_tracking_periods_first(self):
        """Ensures correct output from _old_to_new_tracking_periods.

        In this case, using first max time interval.
        """

        these_start_times_unix_sec, these_end_times_unix_sec = (
            echo_top_tracking._old_to_new_tracking_periods(
                tracking_start_times_unix_sec=
                OLD_TRACKING_START_TIMES_UNIX_SEC + 0,
                tracking_end_times_unix_sec=OLD_TRACKING_END_TIMES_UNIX_SEC + 0,
                max_time_interval_sec=FIRST_MAX_TIME_INTERVAL_SEC)
        )

        self.assertTrue(numpy.array_equal(
            these_start_times_unix_sec, FIRST_NEW_START_TIMES_UNIX_SEC
        ))
        self.assertTrue(numpy.array_equal(
            these_end_times_unix_sec, FIRST_NEW_END_TIMES_UNIX_SEC
        ))

    def test_old_to_new_tracking_periods_second(self):
        """Ensures correct output from _old_to_new_tracking_periods.

        In this case, using second max time interval.
        """

        these_start_times_unix_sec, these_end_times_unix_sec = (
            echo_top_tracking._old_to_new_tracking_periods(
                tracking_start_times_unix_sec=
                OLD_TRACKING_START_TIMES_UNIX_SEC + 0,
                tracking_end_times_unix_sec=OLD_TRACKING_END_TIMES_UNIX_SEC + 0,
                max_time_interval_sec=SECOND_MAX_TIME_INTERVAL_SEC)
        )

        self.assertTrue(numpy.array_equal(
            these_start_times_unix_sec, SECOND_NEW_START_TIMES_UNIX_SEC
        ))
        self.assertTrue(numpy.array_equal(
            these_end_times_unix_sec, SECOND_NEW_END_TIMES_UNIX_SEC
        ))

    def test_old_to_new_tracking_periods_third(self):
        """Ensures correct output from _old_to_new_tracking_periods.

        In this case, using third max time interval.
        """

        these_start_times_unix_sec, these_end_times_unix_sec = (
            echo_top_tracking._old_to_new_tracking_periods(
                tracking_start_times_unix_sec=
                OLD_TRACKING_START_TIMES_UNIX_SEC + 0,
                tracking_end_times_unix_sec=OLD_TRACKING_END_TIMES_UNIX_SEC + 0,
                max_time_interval_sec=THIRD_MAX_TIME_INTERVAL_SEC)
        )

        self.assertTrue(numpy.array_equal(
            these_start_times_unix_sec, THIRD_NEW_START_TIMES_UNIX_SEC
        ))
        self.assertTrue(numpy.array_equal(
            these_end_times_unix_sec, THIRD_NEW_END_TIMES_UNIX_SEC
        ))

    def test_old_to_new_tracking_periods_fourth(self):
        """Ensures correct output from _old_to_new_tracking_periods.

        In this case, using fourth max time interval.
        """

        these_start_times_unix_sec, these_end_times_unix_sec = (
            echo_top_tracking._old_to_new_tracking_periods(
                tracking_start_times_unix_sec=
                OLD_TRACKING_START_TIMES_UNIX_SEC + 0,
                tracking_end_times_unix_sec=OLD_TRACKING_END_TIMES_UNIX_SEC + 0,
                max_time_interval_sec=FOURTH_MAX_TIME_INTERVAL_SEC)
        )

        self.assertTrue(numpy.array_equal(
            these_start_times_unix_sec, FOURTH_NEW_START_TIMES_UNIX_SEC
        ))
        self.assertTrue(numpy.array_equal(
            these_end_times_unix_sec, FOURTH_NEW_END_TIMES_UNIX_SEC
        ))


if __name__ == '__main__':
    unittest.main()
