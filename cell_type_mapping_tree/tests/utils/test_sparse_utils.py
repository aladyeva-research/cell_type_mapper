import numpy as np
import scipy.sparse as scipy_sparse
import anndata
import os
import tempfile
import pathlib
import zarr

from hierarchical_mapping.utils.sparse_utils import(
    load_csr,
    load_csr_chunk)


def _clean_up(target_path):
    target_path = pathlib.Path(target_path)
    if target_path.is_file():
        target_path.unlink()
    elif target_path.is_dir():
        for sub_path in target_path.iterdir():
            _clean_up(sub_path)
        target_path.rmdir()


def test_load_csr():
    tmp_path = tempfile.mkdtemp(suffix='.zarr')

    rng = np.random.default_rng(88123)

    data = np.zeros(60000, dtype=int)
    chosen_dex = rng.choice(np.arange(len(data)),
                            len(data)//4,
                            replace=False)

    data[chosen_dex] = rng.integers(2, 1000, len(chosen_dex))
    data = data.reshape((200, 300))

    csr = scipy_sparse.csr_matrix(data)
    ann = anndata.AnnData(csr)
    ann.write_zarr(tmp_path)

    with zarr.open(tmp_path, 'r') as written_zarr:
        for r0 in range(0, 150, 47):
            r1 = min(200, r0+47)
            subset = load_csr(
                        row_spec=(r0, r1),
                        n_cols=data.shape[1],
                        data=written_zarr.X.data,
                        indices=written_zarr.X.indices,
                        indptr=written_zarr.X.indptr)
            np.testing.assert_array_equal(
                subset,
                data[r0:r1, :])

        for ii in range(10):
            r0 = rng.integers(3, 50)
            r1 = min(data.shape[0], r0+rng.integers(17, 81))

            subset = load_csr(
                row_spec=(r0, r1),
                n_cols=data.shape[1],
                data=written_zarr.X.data,
                indices=written_zarr.X.indices,
                indptr=written_zarr.X.indptr)

            np.testing.assert_array_equal(
                subset,
                data[r0:r1, :])

    _clean_up(tmp_path)


def test_load_csr_chunk():
    tmp_path = tempfile.mkdtemp(suffix='.zarr')

    rng = np.random.default_rng(88123)

    data = np.zeros(60000, dtype=int)
    chosen_dex = rng.choice(np.arange(len(data)),
                            len(data)//4,
                            replace=False)

    data[chosen_dex] = rng.integers(2, 1000, len(chosen_dex))
    data = data.reshape((200, 300))

    csr = scipy_sparse.csr_matrix(data)
    ann = anndata.AnnData(csr)
    ann.write_zarr(tmp_path)

    with zarr.open(tmp_path, 'r') as written_zarr:
        for r0 in range(0, 150, 47):
            r1 = min(200, r0+47)
            for c0 in range(0, 270, 37):
                c1 = min(300, c0+37)
                subset = load_csr_chunk(
                            row_spec=(r0, r1),
                            col_spec=(c0, c1),
                            data=written_zarr.X.data,
                            indices=written_zarr.X.indices,
                            indptr=written_zarr.X.indptr)

                assert subset.shape == (r1-r0, c1-c0)

                np.testing.assert_array_equal(
                    subset,
                    data[r0:r1, c0:c1])

        for ii in range(10):
            r0 = rng.integers(3, 50)
            r1 = min(data.shape[0], r0+rng.integers(17, 81))
            c0 = rng.integers(70, 220)
            c1 = min(data.shape[1], c0+rng.integers(20, 91))

            subset = load_csr_chunk(
                row_spec=(r0, r1),
                col_spec=(c0, c1),
                data=written_zarr.X.data,
                indices=written_zarr.X.indices,
                indptr=written_zarr.X.indptr)

            assert subset.shape == (r1-r0, c1-c0)

            np.testing.assert_array_equal(
                subset,
                data[r0:r1, c0:c1])

    _clean_up(tmp_path)


def test_load_csr_chunk_very_sparse():
    tmp_path = tempfile.mkdtemp(suffix='.zarr')

    data = np.zeros((20, 20), dtype=int)
    data[7, 11] = 1

    csr = scipy_sparse.csr_matrix(data)
    ann = anndata.AnnData(csr)
    ann.write_zarr(tmp_path)

    with zarr.open(tmp_path, 'r') as written_zarr:
        for subset, expected_sum in zip([((1, 15), (6, 13)),
                                         ((15, 19), (3, 14))],
                                        [1, 0]):

            expected = data[subset[0][0]:subset[0][1],
                            subset[1][0]:subset[1][1]]

            actual = load_csr_chunk(
                    row_spec=(subset[0][0], subset[0][1]),
                    col_spec=(subset[1][0], subset[1][1]),
                    data=written_zarr.X.data,
                    indices=written_zarr.X.indices,
                    indptr=written_zarr.X.indptr)

            assert actual.sum() == expected_sum

            np.testing.assert_array_equal(expected, actual)
