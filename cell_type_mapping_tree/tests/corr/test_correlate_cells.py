import pytest

import anndata
import h5py
import json
import numpy as np
import os
import pandas as pd
import pathlib
import scipy.sparse as scipy_sparse
import tempfile

from hierarchical_mapping.corr.utils import (
    match_genes)

from hierarchical_mapping.utils.utils import (
    _clean_up)

from hierarchical_mapping.corr.correlate_cells import (
    correlate_cells,
    flatmap_cells)

@pytest.fixture
def cluster_names_fixture():
    return [f'cluster_{ii}' for ii in range(100)]


@pytest.fixture
def reference_gene_names_fixture():
    return [f'gene_{ii}' for ii in range(12)]


@pytest.fixture
def query_gene_names_fixture():
    result = ['gene_7', 'gene_11', 'gene_8',
              'gene_6', 'gene_3', 'nonsense_1',
              'nonsense_2', 'gene_0']
    return result


@pytest.fixture
def n_cells_fixture(cluster_names_fixture):
    rng = np.random.default_rng(221321)
    return rng.integers(66, 112, size=len(cluster_names_fixture))


@pytest.fixture
def sum_fixture(
        cluster_names_fixture,
        reference_gene_names_fixture):
    rng = np.random.default_rng(55631)
    n_clusters = len(cluster_names_fixture)
    n_genes = len(reference_gene_names_fixture)
    return 100.0*rng.random(size=(n_clusters, n_genes))


@pytest.fixture
def precomputed_fixture(
        cluster_names_fixture,
        reference_gene_names_fixture,
        n_cells_fixture,
        sum_fixture,
        tmp_path_factory):

    tmp_dir = pathlib.Path(
            tmp_path_factory.mktemp('precompute'))
    precompute_path = tempfile.mkstemp(
            dir=tmp_dir,
            suffix='.h5')
    os.close(precompute_path[0])
    precompute_path = pathlib.Path(precompute_path[1])

    n_clusters = len(cluster_names_fixture)
    n_genes = len(reference_gene_names_fixture)

    with h5py.File(precompute_path, 'w') as out_file:
        out_file.create_dataset(
            'col_names',
            data=json.dumps(reference_gene_names_fixture).encode('utf-8'))
        out_file.create_dataset(
            'cluster_to_row',
            data=json.dumps(
                {n:int(ii)
                 for ii, n in
                 enumerate(cluster_names_fixture)}).encode('utf-8'))
        out_file.create_dataset(
            'n_cells',
            data=n_cells_fixture)
        out_file.create_dataset(
            'sum',
            data=sum_fixture)

    yield precompute_path

    _clean_up(tmp_dir)


@pytest.fixture
def x_data_fixture(
        query_gene_names_fixture):

    rng = np.random.default_rng(77665533)

    n_genes = len(query_gene_names_fixture)
    n_cells = 712
    x_data = np.zeros(n_cells*n_genes, dtype=float)
    chosen_dex = rng.choice(np.arange(n_cells*n_genes),
                            n_cells*n_genes//3,
                            replace=False)
    x_data[chosen_dex] = 212.0*rng.random(len(chosen_dex))
    x_data = x_data.reshape((n_cells, n_genes))

    return x_data

@pytest.fixture
def h5ad_fixture(
        query_gene_names_fixture,
        x_data_fixture,
        tmp_path_factory):
    tmp_dir = pathlib.Path(
            tmp_path_factory.mktemp('anndata'))
    h5ad_path = tempfile.mkstemp(
            dir=tmp_dir,
            suffix='.h5ad')
    os.close(h5ad_path[0])
    h5ad_path = pathlib.Path(h5ad_path[1])

    var_data = [
        {'gene_name': g}
        for g in query_gene_names_fixture]

    var = pd.DataFrame(var_data).set_index('gene_name')

    csr = scipy_sparse.csr_matrix(x_data_fixture)

    a_data = anndata.AnnData(X=csr, var=var, dtype=csr.dtype)
    a_data.write_h5ad(h5ad_path)

    yield h5ad_path

    _clean_up(tmp_dir)


@pytest.fixture
def expected_corr_fixture(
        n_cells_fixture,
        sum_fixture,
        x_data_fixture,
        reference_gene_names_fixture,
        query_gene_names_fixture):

    matched_genes = match_genes(
            reference_gene_names=reference_gene_names_fixture,
            query_gene_names=query_gene_names_fixture)

    assert len(matched_genes['reference']) == 6

    n_cells = x_data_fixture.shape[0]
    n_clusters = sum_fixture.shape[0]

    expected = np.zeros(
            (n_cells, n_clusters))

    cell_profiles = x_data_fixture[:, matched_genes['query']]
    cell_means = np.mean(cell_profiles, axis=1)
    cell_std = np.std(cell_profiles, axis=1, ddof=0)

    cluster_profiles = np.array([sum_fixture[ii, :]/n_cells_fixture[ii]
                              for ii in range(n_clusters)])
    cluster_profiles = cluster_profiles[:, matched_genes['reference']]
    cluster_means = np.mean(cluster_profiles, axis=1)
    cluster_std = np.std(cluster_profiles, axis=1, ddof=0)

    valid = 0
    for i_cell in range(n_cells):
        this_cell = cell_profiles[i_cell, :]
        for i_cluster in range(n_clusters):
            this_cluster = cluster_profiles[i_cluster, :]
            corr = np.mean((this_cell-cell_means[i_cell])
                          *(this_cluster-cluster_means[i_cluster]))
            denom = (cluster_std[i_cluster]*cell_std[i_cell])
            if denom > 0.0:
                corr = corr/denom
                valid += 1
            else:
                corr = 0.0
            expected[i_cell, i_cluster] = corr
    assert valid > 0
    return expected

def test_correlate_cells_no_markers(
        h5ad_fixture,
        precomputed_fixture,
        expected_corr_fixture,
        tmp_path_factory):

    with pytest.raises(RuntimeError, match="No marker genes appeared"):
        correlate_cells(
            query_path=h5ad_fixture,
            precomputed_path=precomputed_fixture,
            output_path='junk.h5',
            rows_at_a_time=51,
            n_processors=3,
            marker_gene_list=['nope_1', 'nada_2', 'zilch_9'])


def test_correlate_cells_function(
        h5ad_fixture,
        precomputed_fixture,
        expected_corr_fixture,
        tmp_path_factory):

    tmp_dir = pathlib.Path(
        tmp_path_factory.mktemp('correlate_cells'))

    h5_path = tempfile.mkstemp(dir=tmp_dir, suffix='.h5')
    os.close(h5_path[0])
    h5_path = pathlib.Path(h5_path[1])

    correlate_cells(
        query_path=h5ad_fixture,
        precomputed_path=precomputed_fixture,
        output_path=h5_path,
        rows_at_a_time=51,
        n_processors=3)

    with h5py.File(h5_path, 'r') as in_file:
        actual = in_file['correlation'][()]
        cluster_to_col = in_file['cluster_to_col'][()]

    with h5py.File(precomputed_fixture, 'r') as in_file:
        assert cluster_to_col == in_file['cluster_to_row'][()]

    assert actual.shape == expected_corr_fixture.shape
    np.testing.assert_allclose(
            actual,
            expected_corr_fixture,
            rtol=1.0e-6,
            atol=1.0e-6)

    _clean_up(tmp_dir)


def test_flatmap_cells_function(
        h5ad_fixture,
        precomputed_fixture,
        expected_corr_fixture):

    a_data = anndata.read_h5ad(h5ad_fixture, backed='r')
    cell_id_list = a_data.obs_names

    results = flatmap_cells(
           query_path=h5ad_fixture,
           precomputed_path=precomputed_fixture,
           rows_at_a_time=51,
           n_processors=3)

    with h5py.File(precomputed_fixture, 'r') as in_file:
        cluster_to_row = json.loads(in_file['cluster_to_row'][()].decode('utf-8'))
    row_to_cluster = {cluster_to_row[n]: n for n in cluster_to_row}

    assert len(results) == len(cell_id_list)
    for i_query in range(len(cell_id_list)):
        idx = np.argmax(expected_corr_fixture[i_query, :])
        cluster = row_to_cluster[idx]
        assert results[i_query]['assignment'] == cluster
        corr = expected_corr_fixture[i_query, idx]
        assert np.isclose(
            results[i_query]['confidence'],
            corr,
            atol=0.0,
            rtol=1.0e-6)
        assert results[i_query]['cell_id'] == cell_id_list[i_query]
