import pytest

import h5py
import numpy as np
import pathlib

from hierarchical_mapping.utils.utils import(
    _clean_up,
    mkstemp_clean)

from hierarchical_mapping.binary_array.binary_array import (
    n_int_from_n_cols,
    BinarizedBooleanArray)

from hierarchical_mapping.binary_array.backed_binary_array import (
    BackedBinarizedBooleanArray)


@pytest.fixture
def tmp_dir_fixture(
        tmp_path_factory):
    tmp_dir = pathlib.Path(tmp_path_factory.mktemp('backed_binary'))
    yield tmp_dir
    _clean_up(tmp_dir)


@pytest.fixture
def n_rows():
    return 312

@pytest.fixture
def n_cols():
    return 406

@pytest.fixture
def baseline_data_fixture(
        n_rows,
        n_cols):
    n_int = n_int_from_n_cols(n_cols)
    rng = np.random.default_rng(65123)
    data = BinarizedBooleanArray.from_data_array(
        data_array=rng.integers(0, 255, (n_rows, n_int), dtype=np.uint8),
        n_cols=n_cols)
    return data


def test_backed_get_row_col(
        n_rows,
        n_cols,
        baseline_data_fixture,
        tmp_dir_fixture):
    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()

    with h5py.File(h5_path, 'a') as out_file:
        out_file.create_dataset(
            'test/data',
            data=baseline_data_fixture.data,
            chunks=(50,50))

    backed_array = BackedBinarizedBooleanArray(
        h5_path=h5_path,
        h5_group='test',
        n_rows=n_rows,
        n_cols=n_cols)

    # force loading
    backed_array._load_row_size = 50
    backed_array._load_col_size = 50

    for i_row in range(n_rows):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_row(i_row),
            backed_array.get_row(i_row))

    for i_col in range(n_cols):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_col(i_col),
            backed_array.get_col(i_col))


def test_backed_changing_columns(
        n_rows,
        n_cols,
        baseline_data_fixture,
        tmp_dir_fixture):
    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()

    with h5py.File(h5_path, 'a') as out_file:
        out_file.create_dataset(
            'test/data',
            data=baseline_data_fixture.data,
            chunks=(50,50))

    backed_array = BackedBinarizedBooleanArray(
        h5_path=h5_path,
        h5_group='test',
        n_rows=n_rows,
        n_cols=n_cols)

    # force loading
    backed_array._load_row_size = 50
    backed_array._load_col_size = 50

    for i_col in (116, n_cols-1):
        baseline_data_fixture.set_col_true(i_col)
        backed_array.set_col_true(i_col)

    for i_col in (0, 99):
        baseline_data_fixture.set_col_false(i_col)
        backed_array.set_col_false(i_col)

    for i_col in range(n_cols):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_col(i_col),
            backed_array.get_col(i_col))

    for i_row in range(n_rows):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_row(i_row),
            backed_array.get_row(i_row))

def test_backed_changing_rows(
        n_rows,
        n_cols,
        baseline_data_fixture,
        tmp_dir_fixture):

    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()

    with h5py.File(h5_path, 'a') as out_file:
        out_file.create_dataset(
            'test/data',
            data=baseline_data_fixture.data,
            chunks=(50,50))

    backed_array = BackedBinarizedBooleanArray(
        h5_path=h5_path,
        h5_group='test',
        n_rows=n_rows,
        n_cols=n_cols)

    # force loading
    backed_array._load_row_size = 50
    backed_array._load_col_size = 50

    for i_row in (116, n_rows-1):
        baseline_data_fixture.set_row_true(i_row)
        backed_array.set_row_true(i_row)

    for i_row in (0, 99):
        baseline_data_fixture.set_row_false(i_row)
        backed_array.set_row_false(i_row)

    for i_col in range(n_cols):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_col(i_col),
            backed_array.get_col(i_col))

    for i_row in range(n_rows):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_row(i_row),
            backed_array.get_row(i_row))


def test_backed_set_col(
        n_rows,
        n_cols,
        baseline_data_fixture,
        tmp_dir_fixture):

    rng = np.random.default_rng(765543)

    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()

    with h5py.File(h5_path, 'a') as out_file:
        out_file.create_dataset(
            'test/data',
            data=baseline_data_fixture.data,
            chunks=(50,50))

    backed_array = BackedBinarizedBooleanArray(
        h5_path=h5_path,
        h5_group='test',
        n_rows=n_rows,
        n_cols=n_cols)

    # force loading
    backed_array._load_row_size = 50
    backed_array._load_col_size = 50

    to_change = (0, 22, 117, n_cols-1)
    expected_lookup = dict()
    for i_col in to_change:
        new_col = rng.integers(0, 2, n_rows, dtype=bool)
        expected_lookup[i_col] = new_col
        assert not np.array_equal(
            new_col,
            baseline_data_fixture.get_col(i_col))
        backed_array.set_col(i_col, new_col)

    ct = 0
    for i_col in range(n_cols):
        if i_col in to_change:
            expected = expected_lookup[i_col]
            ct += 1
        else:
            expected = baseline_data_fixture.get_col(i_col)
        np.testing.assert_array_equal(
            backed_array.get_col(i_col),
            expected)
    assert ct ==len(to_change)


def test_backed_copy_as_columns(
        n_rows,
        n_cols,
        baseline_data_fixture,
        tmp_dir_fixture):

    rng = np.random.default_rng(765543)

    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()

    backed_array = BackedBinarizedBooleanArray(
        h5_path=h5_path,
        h5_group='test',
        n_rows=n_rows,
        n_cols=n_cols)

    # force loading
    backed_array._load_row_size = 50
    backed_array._load_col_size = 50

    backed_array.copy_other_as_columns(
        other=baseline_data_fixture,
        col0=0)

    for i_row in range(n_rows):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_row(i_row),
            backed_array.get_row(i_row))

    for i_col in range(n_cols):
        np.testing.assert_array_equal(
            baseline_data_fixture.get_col(i_col),
            backed_array.get_col(i_col))

    col0 = 320
    n_other_cols = 13
    other = BinarizedBooleanArray(
        n_rows=n_rows,
        n_cols=n_other_cols)
    for i_col in range(13):
        this = rng.integers(0, 2, n_rows, dtype=bool)
        other.set_col(i_col, this)

    backed_array.copy_other_as_columns(
        other=other,
        col0=col0)

    for i_col in range(n_cols):
        actual = backed_array.get_col(i_col)
        if i_col >= col0 and i_col < col0+n_other_cols:
            expected = other.get_col(i_col-col0)
        else:
            expected = baseline_data_fixture.get_col(i_col)

        np.testing.assert_array_equal(
            actual,
            expected)


def test_storing_two_backed_arrays(
        tmp_dir_fixture):
    """
    Make sure we can store 2 arrays in the same HDF5 file
    """
    rng = np.random.default_rng(61234)
    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()
    nr0 = 193
    nr1 = 271

    nc0 = 312
    nc1 = 149

    arr0 = BinarizedBooleanArray.from_data_array(
        data_array=rng.integers(0, 255,
                                (nr0, n_int_from_n_cols(nc0)),
                                dtype=np.uint8),
        n_cols=nc0)

    arr1 = BinarizedBooleanArray.from_data_array(
        data_array=rng.integers(0, 255,
                                (nr1, n_int_from_n_cols(nc1)),
                                dtype=np.uint8),
        n_cols=nc1)

    b_arr0 = BackedBinarizedBooleanArray(
       h5_path=h5_path,
       h5_group='arr0',
       n_rows=nr0,
       n_cols=nc0)
    b_arr0.copy_other_as_columns(arr0, col0=0)
    del b_arr0

    b_arr1 = BackedBinarizedBooleanArray(
       h5_path=h5_path,
       h5_group='arr1',
       n_rows=nr1,
       n_cols=nc1)
    b_arr1.copy_other_as_columns(arr1, col0=0)
    del b_arr1

    actual0 = BackedBinarizedBooleanArray(
       h5_path=h5_path,
       h5_group='arr0',
       n_rows=nr0,
       n_cols=nc0)

    actual1 = BackedBinarizedBooleanArray(
       h5_path=h5_path,
       h5_group='arr1',
       n_rows=nr1,
       n_cols=nc1)

    for actual, expected in zip((actual1, actual0), (arr1, arr0)):
        assert actual.n_rows == expected.n_rows
        assert actual.n_cols == expected.n_cols
        print(f'test {actual.data_key}')
        for i_row in range(actual.n_rows):
            print(i_row)
            np.testing.assert_array_equal(
                actual.get_row(i_row),
                expected.get_row(i_row))
        for i_col in range(actual.n_cols):
            np.testing.assert_array_equal(
                actual.get_col(i_col),
                expected.get_col(i_col))


@pytest.mark.parametrize(
        "row0, row1", [(0, 250), (100, 222), (199, 312)])
def test_backed_get_row_batch(
        n_rows,
        n_cols,
        baseline_data_fixture,
        tmp_dir_fixture,
        row0,
        row1):
    h5_path = pathlib.Path(mkstemp_clean(dir=tmp_dir_fixture, suffix='.h5'))
    h5_path.unlink()

    with h5py.File(h5_path, 'a') as out_file:
        out_file.create_dataset(
            'test/data',
            data=baseline_data_fixture.data,
            chunks=(50,50))

    backed_array = BackedBinarizedBooleanArray(
        h5_path=h5_path,
        h5_group='test',
        n_rows=n_rows,
        n_cols=n_cols)

    batch = backed_array.get_row_batch(row0=row0, row1=row1)
    for i_row in range(row0, row1, 1):
        expected = baseline_data_fixture.get_row(i_row)
        np.testing.assert_array_equal(
            batch[i_row-row0, :],
            expected)
