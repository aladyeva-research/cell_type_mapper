import anndata
import h5py
import numpy as np
import pathlib
import tempfile
import time

from hierarchical_mapping.utils.utils import (
    mkstemp_clean,
    _clean_up)

from hierarchical_mapping.utils.csc_to_csr import (
    csc_to_csr_on_disk)

from hierarchical_mapping.utils.sparse_utils import (
    load_csr)


class AnnDataRowIterator(object):
    """
    A class to efficiently iterate over the rows of an anndata
    file. If the anndata file is CSC, it will, as a first step,
    write the data out to a tempfile in CSR (or dense) format
    for more rapid iteration over rows.

    Parameters
    ----------
    h5ad_path:
        Path to the h5ad file over whose rows we are iterating
    row_chunk_size:
        Number of rows to deliver per chunk
    tmp_dir:
        Optional scratch directory. This is where a hypothetical
        CSC file will be written as a CSR file. If None, the
        CSC file will be iterated over using anndata's infrastructure
        (which can be very slow)
    """

    def __init__(
            self,
            h5ad_path,
            row_chunk_size,
            tmp_dir=None):

        self.tmp_dir = None
        h5ad_path = pathlib.Path(h5ad_path)
        if not h5ad_path.is_file():
            raise RuntimeError(
                f"{h5ad_path} is not a file")

        with h5py.File(h5ad_path, 'r') as in_file:
            attrs = dict(in_file['X'].attrs)
            array_shape = None
            encoding_type = ''
            if 'shape' in attrs:
                array_shape = attrs['shape']
            if 'encoding-type' in attrs:
                encoding_type = attrs['encoding-type']

        if encoding_type.startswith('csr') and array_shape is not None:
            self._iterator_type = 'CSRRow'
            self.n_rows = array_shape[0]
            self._chunk_iterator = CSRRowIterator(
                h5_path=h5ad_path,
                row_chunk_size=row_chunk_size,
                array_shape=array_shape,
                h5_group='X')
        elif encoding_type.startswith('csc'):
            self._initialize_as_csc(
                h5ad_path=h5ad_path,
                row_chunk_size=row_chunk_size,
                tmp_dir=tmp_dir)
        else:
            self._initialize_anndata_iterator(
                h5ad_path=h5ad_path,
                row_chunk_size=row_chunk_size)

    def __del__(self):
        if self.tmp_dir is not None:
            _clean_up(self.tmp_dir)

    def __iter__(self):
        return self

    def __next__(self):
        """
        Return the next chunk of rows.

        Actually return a tuple
        (row_chunk, r0, r1)
        where r0 and r1 are the indices of the slice of rows
        (i.e. row_chunk is data[r0:r1, :])
        """
        result = next(self._chunk_iterator)
        if self._iterator_type == 'anndata':
            r0 = result[1]
            r1 = result[2]
            result = result[0]
            if not isinstance(result, np.ndarray):
                result = result.toarray()
            result = (result, r0, r1)
        return result

    def _initialize_anndata_iterator(
            self,
            h5ad_path,
            row_chunk_size):
        """
        Initialize iterator using anndata.chunked_X
        directly.

        Parameters
        ----------
        h5ad_path:
            Path to h5ad file whose rows we are iterating over
        row_chunk_size:
            Number of rows to return per chunk
        """
        self._iterator_type = 'anndata'
        data = anndata.read_h5ad(h5ad_path, backed='r')
        self.n_rows = data.X.shape[0]
        self._chunk_iterator = data.chunked_X(
            chunk_size=row_chunk_size)

    def _initialize_as_csc(
            self,
            h5ad_path,
            row_chunk_size,
            tmp_dir=None):
        """
        Initialize iterator for CSC data. If possible,
        write out data to scratch space as CSR matrix
        and initialize iterator over that.

        Parameters
        ----------
        h5ad_path:
            Path to h5ad file whose rows we are iterating over
        row_chunk_size:
            Number of rows to deliver per chunk
        tmp_dir:
            scratch dir in which to write the CSR form of the data
            (if None, no CSR data will be written and we will just
            use anndata.chunked_X to iterate over the data)
        """
        write_as_csr = True
        if tmp_dir is None:
            write_as_csr = False

        else:
            with h5py.File(h5ad_path, 'r') as src:
                attrs = dict(src['X'].attrs)

            if 'shape' not in attrs:
                write_as_csr = False

        if not write_as_csr:
            self._initialize_anndata_iterator(
                h5ad_path=h5ad_path,
                row_chunk_size=row_chunk_size)
        else:
            self.tmp_dir = tempfile.mkdtemp(dir=tmp_dir)
            self.tmp_path = pathlib.Path(
                mkstemp_clean(
                    dir=self.tmp_dir,
                    prefix=f"{h5ad_path.name}_as_csr_",
                    suffix=".h5"))

            t0 = time.time()
            print(f"transcribing {h5ad_path} to {self.tmp_path} "
                  "as a csr array")

            array_shape = attrs['shape']
            self.n_rows = array_shape[0]
            with h5py.File(h5ad_path, 'r') as src:
                csc_to_csr_on_disk(
                    csc_group=src['X'],
                    csr_path=self.tmp_path,
                    array_shape=array_shape,
                    load_chunk_size=2*1024**3)

            self._iterator_type = 'CSRRow'
            self._chunk_iterator = CSRRowIterator(
                h5_path=self.tmp_path,
                row_chunk_size=row_chunk_size,
                array_shape=array_shape)

            duration = time.time()-t0
            print(f"transcription took {duration:.2e} seconds")


class CSRRowIterator(object):
    """
    Class to iterate over a CSR matrix using h5py to directly
    access the data (rather than anndata, which can load unnecessary
    data into memory)

    Parameters
    ----------
    h5_path:
        Path to HDF5 file containing CSR matrix data
    row_chunk_size:
        Number of rows to return with each chunk
    array_shape:
        Shape of the array we are iterating over
    h5_group:
        Optional group in the HDF5 file where you will find
        'data', 'indices' and 'indptr'
    """

    def __init__(
            self,
            h5_path,
            row_chunk_size,
            array_shape,
            h5_group=None):

        self.h5_path = h5_path
        self.h5_handle = None
        self.row_chunk_size = row_chunk_size
        self.r0 = 0
        self.n_rows = array_shape[0]
        self.n_cols = array_shape[1]
        self.h5_handle = h5py.File(h5_path, 'r')

        if h5_group is None:
            self.data_key = 'data'
            self.indices_key = 'indices'
            self.indptr_key = 'indptr'
        else:
            self.data_key = f'{h5_group}/data'
            self.indices_key = f'{h5_group}/indices'
            self.indptr_key = f'{h5_group}/indptr'

    def __del__(self):
        if self.h5_handle is not None:
            self.h5_handle.close()
            self.h5_handle = None

    def __next__(self):
        """
        Actually return a tuple

        (row_chunk, r0, r1)

        where r0 and r1 are the indices of the slice of rows
        (i.e. row_chunk is data[r0:r1, :])
        """
        if self.r0 >= self.n_rows:
            if self.h5_handle is not None:
                self.h5_handle.close()
                self.h5_handle = None
            raise StopIteration
        r1 = min(self.n_rows, self.r0+self.row_chunk_size)

        chunk = load_csr(
            row_spec=(self.r0, r1),
            n_cols=self.n_cols,
            data=self.h5_handle[self.data_key],
            indices=self.h5_handle[self.indices_key],
            indptr=self.h5_handle[self.indptr_key])

        old_r0 = self.r0
        self.r0 = r1
        return (chunk, old_r0, r1)