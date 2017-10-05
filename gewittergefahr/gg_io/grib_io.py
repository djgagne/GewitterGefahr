"""IO methods for grib (gridded binary) and grib2 files.

These methods use wgrib and wgrib2, which are command-line tools for parsing
grib and grib2 files.  See README_grib (in this directory) for installation
instructions.
"""

import os
import subprocess
import warnings
import numpy
from gewittergefahr.gg_io import downloads
from gewittergefahr.gg_utils import file_system_utils
from gewittergefahr.gg_utils import error_checking

# TODO(thunderhoser): replace main method with named method.

RELATIVE_TOLERANCE = 1e-6
WGRIB_EXE_NAME_DEFAULT = '/usr/bin/wgrib'
WGRIB2_EXE_NAME_DEFAULT = '/usr/bin/wgrib2'

# The following constants are used in the main method only.
NARR_FILE_NAME_ONLINE = (
    'https://nomads.ncdc.noaa.gov/data/narr/201408/20140810/'
    'narr-a_221_20140810_1200_000.grb')
NARR_FILE_NAME_LOCAL = (
    '/localdata/ryan.lagerquist/gewittergefahr_junk/'
    'narr-a_221_20140810_1200_000.grb')
NARR_H500_FILE_NAME = (
    '/localdata/ryan.lagerquist/gewittergefahr_junk/'
    'narr_h500_20140810_1200_000.txt')

RAP_FILE_NAME_ONLINE = (
    'https://nomads.ncdc.noaa.gov/data/rap130/201708/20170822/'
    'rap_130_20170822_0000_006.grb2')
RAP_FILE_NAME_LOCAL = (
    '/localdata/ryan.lagerquist/gewittergefahr_junk/'
    'rap_130_20170822_0000_006.grb2')
RAP_H500_FILE_NAME = (
    '/localdata/ryan.lagerquist/gewittergefahr_junk/'
    'rap_h500_20170822_0000_006.txt')

H500_NAME_GRIB = 'HGT:500 mb'

NUM_ROWS_IN_NARR = 277
NUM_COLUMNS_IN_NARR = 349
NARR_SENTINEL_VALUE = 9.999e20

NUM_ROWS_IN_RAP = 337
NUM_COLUMNS_IN_RAP = 451
RAP_SENTINEL_VALUE = 9.999e20


def _replace_sentinels_with_nan(data_matrix, sentinel_value=None):
    """Replaces all instances of sentinel value with NaN.

    :param data_matrix: numpy array with original data values, which may contain
        sentinels.
    :param sentinel_value: Sentinel value.
    :return: data_matrix: Same as input, except with all sentinels changed to
        NaN.
    """

    if sentinel_value is None:
        return data_matrix

    data_vector = numpy.reshape(data_matrix, data_matrix.size)
    sentinel_flags = numpy.isclose(data_vector, sentinel_value,
                                   rtol=RELATIVE_TOLERANCE)

    sentinel_indices = numpy.where(sentinel_flags)[0]
    data_vector[sentinel_indices] = numpy.nan
    return numpy.reshape(data_vector, data_matrix.shape)


def _extract_variable_grib_to_text(grib_file_name, grib_var_name=None,
                                   text_file_name=None,
                                   wgrib_exe_name=WGRIB_EXE_NAME_DEFAULT,
                                   raise_error_if_fails=True):
    """Extracts one variable, at all grid points, from grib file to text file.

    :param grib_file_name: Path to input file.
    :param grib_var_name: Name of variable to be extracted.  This must be the
        name used in the grib file.  For example, most grib files store 500-mb
        geopotential height as "HGT:500 mb".
    :param text_file_name: Path to output file.
    :param wgrib_exe_name: Path to wgrib executable.
    :param raise_error_if_fails: Boolean flag.  If command fails and
        raise_error_if_fails = True, this method will raise an error.
    :return: success: Boolean flag.  If command succeeded, this is True.  If
        command failed and raise_error_if_fails = False, this is False.
    :raises: OSError: if command fails and raise_error_if_fails = True.
    """

    error_checking.assert_is_boolean(raise_error_if_fails)
    file_system_utils.mkdir_recursive_if_necessary(file_name=text_file_name)

    wgrib_command_string = (
        '"' + wgrib_exe_name + '" "' + grib_file_name + '" -s | grep -w "' +
        grib_var_name + '" | "' + wgrib_exe_name + '" -i "' + grib_file_name +
        '" -text -nh -o "' + text_file_name + '"')

    try:
        subprocess.call(wgrib_command_string, shell=True)
    except OSError as this_exception:
        if raise_error_if_fails:
            raise

        warn_string = (
            '\n' + wgrib_command_string +
            '\nCommand (shown above) failed (details shown below).\n' +
            str(this_exception))
        warnings.warn(warn_string)
        return False

    return True


def _extract_variable_grib2_to_text(grib2_file_name, grib2_var_name=None,
                                    text_file_name=None,
                                    wgrib2_exe_name=WGRIB2_EXE_NAME_DEFAULT,
                                    raise_error_if_fails=True):
    """Extracts one variable, at all grid points, from grib2 file to text file.

    :param grib2_file_name: Path to input file.
    :param grib2_var_name: Name of variable to be extracted.  This must be the
        name used in the grib2 file.  For example, most grib2 files store 500-mb
        geopotential height as "HGT:500 mb".
    :param text_file_name: Path to output file.
    :param wgrib2_exe_name: Path to wgrib2 executable.
    :param raise_error_if_fails: Boolean flag.  If command fails and
        raise_error_if_fails = True, this method will raise an error.
    :return: success: Boolean flag.  If command succeeded, this is True.  If
        command failed and raise_error_if_fails = False, this is False.
    :raises: OSError: if command fails and raise_error_if_fails = True.
    """

    error_checking.assert_is_boolean(raise_error_if_fails)
    file_system_utils.mkdir_recursive_if_necessary(file_name=text_file_name)

    wgrib2_command_string = (
        '"' + wgrib2_exe_name + '" "' + grib2_file_name + '" -s | grep -w "' +
        grib2_var_name + '" | "' + wgrib2_exe_name + '" -i "' +
        grib2_file_name + '" -no_header -text "' + text_file_name + '"')

    try:
        subprocess.call(wgrib2_command_string, shell=True)
    except OSError as this_exception:
        if raise_error_if_fails:
            raise

        warn_string = (
            '\n' + wgrib2_command_string +
            '\nCommand (shown above) failed (details shown below).\n' +
            str(this_exception))
        warnings.warn(warn_string)
        return False

    return True


def _read_variable_from_text(text_file_name, num_grid_rows=None,
                             num_grid_columns=None, sentinel_value=None,
                             raise_error_if_fails=True):
    """Reads one variable, at all grid points, from text file.

    M = number of rows in grid
    N = number of columns in grid

    :param text_file_name: Input file.  Should be created by
        extract_variable_grib_to_text or extract_variable_grib2_to_text.
    :param num_grid_rows: Number of rows in grid.
    :param num_grid_columns: Number of columns in grid.
    :param sentinel_value: Sentinel value.  All instances of this value will be
        replaced with NaN.
    :param raise_error_if_fails: Boolean flag.  If `numpy.reshape` fails (wrong
        number of grid points in file) and raise_error_if_fails = True, this
        method will raise an error.
    :return: data_matrix: If read fails and raise_error_if_fails = False: None.
        Otherwise: M-by-N numpy array with values read from file.  If the grid
        is regular in x-y, x increases while traveling right across the rows and
        y increases while traveling down the columns.  If the grid is regular in
        lat-long, latitude increases while traveling down the columns and
        longitude increases while traveling right across the rows.
    :raises: ValueError: if read fails and raise_error_if_fails = True.
    """

    data_vector = numpy.loadtxt(text_file_name)

    try:
        data_matrix = numpy.reshape(data_vector,
                                    (num_grid_rows, num_grid_columns))
    except ValueError as this_exception:
        if raise_error_if_fails:
            raise

        warn_string = (
            '\n' + str(this_exception) + '\nnumpy.reshape failed (probably ' +
            'wrong number of grid points in file -- details shown above).')
        warnings.warn(warn_string)
        return None

    return _replace_sentinels_with_nan(data_matrix, sentinel_value)


def read_variable_from_grib(grib_file_name, grib_var_name=None,
                            text_file_name=None,
                            wgrib_exe_name=WGRIB_EXE_NAME_DEFAULT,
                            num_grid_rows=None, num_grid_columns=None,
                            sentinel_value=None, delete_text_file=True):
    """Reads one variable, at all grid points, from grib file.

    :param grib_file_name: See documentation for _extract_variable_grib_to_text.
    :param grib_var_name: See documentation for _extract_variable_grib_to_text.
    :param text_file_name: See documentation for _extract_variable_grib_to_text.
    :param wgrib_exe_name: See documentation for _extract_variable_grib_to_text.
    :param num_grid_rows: See documentation for _read_variable_from_text.
    :param num_grid_columns: See documentation for _read_variable_from_text.
    :param sentinel_value: See documentation for _read_variable_from_text.
    :param delete_text_file: Boolean flag.  If True, will delete text file after
        reading from it.  In other words, the text file will exist only while
        executing this method.
    :return: data_matrix: See documentation for _read_variable_from_text.
    """

    error_checking.assert_file_exists(grib_file_name)
    error_checking.assert_is_string(grib_var_name)
    error_checking.assert_file_exists(wgrib_exe_name)
    error_checking.assert_is_integer(num_grid_rows)
    error_checking.assert_is_greater(num_grid_rows, 0)
    error_checking.assert_is_integer(num_grid_columns)
    error_checking.assert_is_greater(num_grid_columns, 0)
    error_checking.assert_is_boolean(delete_text_file)
    if sentinel_value is not None:
        error_checking.assert_is_not_nan(sentinel_value)

    _extract_variable_grib_to_text(grib_file_name, grib_var_name=grib_var_name,
                                   text_file_name=text_file_name,
                                   wgrib_exe_name=wgrib_exe_name)

    data_matrix = _read_variable_from_text(text_file_name,
                                           num_grid_rows=num_grid_rows,
                                           num_grid_columns=num_grid_columns,
                                           sentinel_value=sentinel_value)

    if delete_text_file:
        os.remove(text_file_name)

    return data_matrix


def read_variable_from_grib2(grib2_file_name, grib2_var_name=None,
                             text_file_name=None,
                             wgrib2_exe_name=WGRIB2_EXE_NAME_DEFAULT,
                             num_grid_rows=None, num_grid_columns=None,
                             sentinel_value=None, delete_text_file=True):
    """Reads one variable, at all grid points, from grib2 file.

    :param grib2_file_name: See documentation for
        _extract_variable_grib2_to_text.
    :param grib2_var_name: See documentation for
        _extract_variable_grib2_to_text.
    :param text_file_name: See documentation for
        _extract_variable_grib2_to_text.
    :param wgrib2_exe_name: See documentation for
        _extract_variable_grib2_to_text.
    :param num_grid_rows: See documentation for _read_variable_from_text.
    :param num_grid_columns: See documentation for _read_variable_from_text.
    :param sentinel_value: See documentation for _read_variable_from_text.
    :param delete_text_file: Boolean flag.  If True, will delete text file after
        reading from it.  In other words, the text file will exist only while
        executing this method.
    :return: data_matrix: See documentation for _read_variable_from_text.
    """

    error_checking.assert_file_exists(grib2_file_name)
    error_checking.assert_is_string(grib2_var_name)
    error_checking.assert_file_exists(wgrib2_exe_name)
    error_checking.assert_is_integer(num_grid_rows)
    error_checking.assert_is_greater(num_grid_rows, 0)
    error_checking.assert_is_integer(num_grid_columns)
    error_checking.assert_is_greater(num_grid_columns, 0)
    error_checking.assert_is_boolean(delete_text_file)
    if sentinel_value is not None:
        error_checking.assert_is_not_nan(sentinel_value)

    _extract_variable_grib2_to_text(grib2_file_name,
                                    grib2_var_name=grib2_var_name,
                                    text_file_name=text_file_name,
                                    wgrib2_exe_name=wgrib2_exe_name)

    data_matrix = _read_variable_from_text(text_file_name,
                                           num_grid_rows=num_grid_rows,
                                           num_grid_columns=num_grid_columns,
                                           sentinel_value=sentinel_value)

    if delete_text_file:
        os.remove(text_file_name)

    return data_matrix


if __name__ == '__main__':
    downloads.download_file_via_http(NARR_FILE_NAME_ONLINE,
                                     NARR_FILE_NAME_LOCAL)
    downloads.download_file_via_http(RAP_FILE_NAME_ONLINE, RAP_FILE_NAME_LOCAL)

    NARR_H500_MATRIX_METRES = (
        read_variable_from_grib(NARR_FILE_NAME_LOCAL,
                                grib_var_name=H500_NAME_GRIB,
                                text_file_name=NARR_H500_FILE_NAME,
                                wgrib_exe_name=WGRIB_EXE_NAME_DEFAULT,
                                num_grid_rows=NUM_ROWS_IN_NARR,
                                num_grid_columns=NUM_COLUMNS_IN_NARR,
                                sentinel_value=NARR_SENTINEL_VALUE))
    print NARR_H500_MATRIX_METRES
    print numpy.nanmin(NARR_H500_MATRIX_METRES)
    print numpy.nanmax(NARR_H500_MATRIX_METRES)

    RAP_H500_MATRIX_METRES = (
        read_variable_from_grib2(RAP_FILE_NAME_LOCAL,
                                 grib2_var_name=H500_NAME_GRIB,
                                 text_file_name=RAP_H500_FILE_NAME,
                                 wgrib2_exe_name=WGRIB2_EXE_NAME_DEFAULT,
                                 num_grid_rows=NUM_ROWS_IN_RAP,
                                 num_grid_columns=NUM_COLUMNS_IN_RAP,
                                 sentinel_value=RAP_SENTINEL_VALUE))
    print RAP_H500_MATRIX_METRES
    print numpy.nanmin(RAP_H500_MATRIX_METRES)
    print numpy.nanmax(RAP_H500_MATRIX_METRES)
