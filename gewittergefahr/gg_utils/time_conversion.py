"""Methods for time conversion.

--- DEFINITIONS ---

SPC = Storm Prediction Center

SPC date = a 24-hour period running from 1200-1200 UTC.  If time is discretized
in seconds, the period runs from 120000-115959 UTC.  This is unlike a human
date, which runs from 0000-0000 UTC (or 000000-235959 UTC).
"""

import time
import calendar
import numpy
from gewittergefahr.gg_utils import number_rounding as rounder
from gewittergefahr.gg_utils import time_periods
from gewittergefahr.gg_utils import error_checking

MONTH_FORMAT = '%Y%m'
SPC_DATE_FORMAT = '%Y%m%d'
HOURS_TO_SECONDS = 3600
DAYS_TO_SECONDS = 86400
SECONDS_INTO_SPC_DATE_DEFAULT = 18 * HOURS_TO_SECONDS

MIN_SECONDS_INTO_SPC_DATE = 12 * HOURS_TO_SECONDS
MAX_SECONDS_INTO_SPC_DATE = (36 * HOURS_TO_SECONDS) - 1


def string_to_unix_sec(time_string, time_directive):
    """Converts time from string to Unix format.

    Unix format = seconds since 0000 UTC 1 Jan 1970.

    :param time_string: Time string.
    :param time_directive: Format of time string (examples: "%Y%m%d" if string
        is "yyyymmdd", "%Y-%m-%d-%H%M%S" if string is "yyyy-mm-dd-HHMMSS",
        etc.).
    :return: unix_time_sec: Time in Unix format.
    """

    error_checking.assert_is_string(time_string)
    error_checking.assert_is_string(time_directive)
    return calendar.timegm(time.strptime(time_string, time_directive))


def unix_sec_to_string(unix_time_sec, time_directive):
    """Converts time from Unix format to string.

    Unix format = seconds since 0000 UTC 1 Jan 1970.

    :param unix_time_sec: Time in Unix format.
    :param time_directive: Format of time string (examples: "%Y%m%d" if string
        is "yyyymmdd", "%Y-%m-%d-%H%M%S" if string is "yyyy-mm-dd-HHMMSS",
        etc.).
    :return: time_string: Time string.
    """

    error_checking.assert_is_integer(unix_time_sec)
    error_checking.assert_is_string(time_directive)
    return time.strftime(time_directive, time.gmtime(unix_time_sec))


def time_to_spc_date_unix_sec(unix_time_sec):
    """Converts time to SPC date (both in Unix format).

    :param unix_time_sec: Time in Unix format.
    :return: spc_date_unix_sec: SPC date in Unix format.  If the SPC date is
        "Oct 28 2017" (120000 UTC 28 Oct - 115959 UTC 29 Oct 2017),
        spc_date_unix_sec will be 180000 UTC 28 Oct 2017.  In general,
        spc_date_unix_sec will be 6 hours into the SPC date.
    """

    error_checking.assert_is_integer(unix_time_sec)
    return int(SECONDS_INTO_SPC_DATE_DEFAULT + rounder.floor_to_nearest(
        unix_time_sec - DAYS_TO_SECONDS // 2, DAYS_TO_SECONDS))


def time_to_spc_date_string(unix_time_sec):
    """Converts time in Unix format to SPC date in string format.

    :param unix_time_sec: Time in Unix format.
    :return: spc_date_string: SPC date in format "yyyymmdd".
    """

    error_checking.assert_is_integer(unix_time_sec)
    return unix_sec_to_string(
        unix_time_sec - DAYS_TO_SECONDS // 2, SPC_DATE_FORMAT)


def spc_date_string_to_unix_sec(spc_date_string):
    """Converts SPC date from string to Unix format.

    :param spc_date_string: SPC date in format "yyyymmdd".
    :return: spc_date_unix_sec: SPC date in Unix format.  If the SPC date is
        "Oct 28 2017" (120000 UTC 28 Oct - 115959 UTC 29 Oct 2017),
        spc_date_unix_sec will be 180000 UTC 28 Oct 2017.  In general,
        spc_date_unix_sec will be 6 hours into the SPC date.
    """

    return SECONDS_INTO_SPC_DATE_DEFAULT + string_to_unix_sec(
        spc_date_string, SPC_DATE_FORMAT)


def get_spc_dates_in_range(first_spc_date_string, last_spc_date_string):
    """Returns list of SPC dates in range.

    :param first_spc_date_string: First SPC date in range (format "yyyymmdd").
    :param last_spc_date_string: Last SPC date in range (format "yyyymmdd").
    :return: spc_date_strings: 1-D list of SPC dates (format "yyyymmdd").
    """

    first_spc_date_unix_sec = string_to_unix_sec(
        first_spc_date_string, SPC_DATE_FORMAT)
    last_spc_date_unix_sec = string_to_unix_sec(
        last_spc_date_string, SPC_DATE_FORMAT)
    error_checking.assert_is_geq(
        last_spc_date_unix_sec, first_spc_date_unix_sec)

    spc_dates_unix_sec = time_periods.range_and_interval_to_list(
        start_time_unix_sec=first_spc_date_unix_sec,
        end_time_unix_sec=last_spc_date_unix_sec,
        time_interval_sec=DAYS_TO_SECONDS, include_endpoint=True)

    return [unix_sec_to_string(t, SPC_DATE_FORMAT) for t in spc_dates_unix_sec]


def get_start_of_spc_date(spc_date_string):
    """Returns time at beginning of SPC date.

    :param spc_date_string: SPC date in format "yyyymmdd".
    :return: start_time_unix_sec: Start time.
    """

    return MIN_SECONDS_INTO_SPC_DATE + string_to_unix_sec(
        spc_date_string, SPC_DATE_FORMAT)


def get_end_of_spc_date(spc_date_string):
    """Returns time at end of SPC date.

    :param spc_date_string: SPC date in format "yyyymmdd".
    :return: end_time_unix_sec: End time.
    """

    return MAX_SECONDS_INTO_SPC_DATE + string_to_unix_sec(
        spc_date_string, SPC_DATE_FORMAT)


def is_time_in_spc_date(unix_time_sec, spc_date_string):
    """Determines whether or not time is in SPC date.

    :param unix_time_sec: Time in Unix format.
    :param spc_date_string: SPC date in format "yyyymmdd".
    :return: time_in_spc_date_flag: Boolean flag.
    """

    min_time_unix_sec = get_start_of_spc_date(spc_date_string)
    max_time_unix_sec = get_end_of_spc_date(spc_date_string)

    error_checking.assert_is_integer(unix_time_sec)
    error_checking.assert_is_not_nan(unix_time_sec)

    return numpy.logical_and(unix_time_sec >= min_time_unix_sec,
                             unix_time_sec <= max_time_unix_sec)


def first_and_last_times_in_month(month_unix_sec):
    """Returns first and last times in month (discretized in seconds).

    For example, first/last times in December 2017 are 2017-12-01-000000 and
    2017-12-31-235959.

    :param month_unix_sec: Any Unix time in month.
    :return: start_time_unix_sec: First time in month.
    :return: end_time_unix_sec: Last time in month.
    """

    month_string = unix_sec_to_string(month_unix_sec, MONTH_FORMAT)
    start_time_unix_sec = string_to_unix_sec(month_string, MONTH_FORMAT)

    num_days_in_month = calendar.monthrange(
        int(month_string[:4]), int(month_string[4:]))[1]
    end_time_unix_sec = (
        start_time_unix_sec + (num_days_in_month * DAYS_TO_SECONDS) - 1)

    return start_time_unix_sec, end_time_unix_sec


def first_and_last_times_in_year(year):
    """Returns first and last times in year (discretized in seconds).

    For example, first/last times in 2017 are 2017-01-01-000000 and
    2017-12-31-235959.

    :param year: Integer.
    :return: start_time_unix_sec: First time in year.
    :return: end_time_unix_sec: Last time in year.
    """

    error_checking.assert_is_integer(year)

    time_format = '%Y-%m-%d-%H%M%S'
    start_time_string = '{0:d}-01-01-000000'.format(year)
    end_time_string = '{0:d}-12-31-235959'.format(year)

    return (string_to_unix_sec(start_time_string, time_format),
            string_to_unix_sec(end_time_string, time_format))
