"""
Test the CLI tool for finding query markers
"""
import pytest

import anndata
import h5py
import itertools
import json
import numpy as np
import pandas as pd
import scipy.sparse

from cell_type_mapper.utils.utils import (
    mkstemp_clean)

from cell_type_mapper.utils.csc_to_csr_parallel import (
    transpose_sparse_matrix_on_disk_v2)

from cell_type_mapper.cli.query_markers import (
    QueryMarkerRunner)



@pytest.mark.parametrize(
    "n_per_utility,drop_level,downsample_genes",
    itertools.product(
        (5, 3, 7, 11),
        (None, 'subclass'),
        (True, False)))
def test_query_marker_cli_tool(
        query_gene_names,
        ref_marker_path_fixture,
        precomputed_path_fixture,
        full_marker_name_fixture,
        taxonomy_tree_dict,
        tmp_dir_fixture,
        n_per_utility,
        drop_level,
        downsample_genes):

    if downsample_genes:
        rng = np.random.default_rng(76123)
        valid_gene_names = rng.choice(
            query_gene_names,
            len(query_gene_names)*3//4,
            replace=False)

        query_path = mkstemp_clean(
            dir=tmp_dir_fixture,
            prefix='h5ad_for_finding_query_markers_',
            suffix='.h5ad')

        var = pd.DataFrame(
            [{'gene_name': g}
             for g in valid_gene_names]).set_index('gene_name')
        adata = anndata.AnnData(var=var)
        adata.write_h5ad(query_path)
    else:
        valid_gene_names = query_gene_names
        query_path = None

    output_path = mkstemp_clean(
        dir=tmp_dir_fixture,
        prefix='query_markers_',
        suffix='.json')

    config = {
        'query_path': query_path,
        'reference_marker_path_list': [ref_marker_path_fixture],
        'n_processors': 3,
        'n_per_utility': n_per_utility,
        'drop_level': drop_level,
        'output_path': output_path,
        'tmp_dir': str(tmp_dir_fixture.resolve().absolute())}

    runner = QueryMarkerRunner(
        args=[],
        input_data=config)
    runner.run()

    with open(output_path, 'rb') as src:
        actual = json.load(src)

    assert 'log' in actual
    n_skipped = 0
    n_dur = 0
    log = actual['log']
    for level in taxonomy_tree_dict['hierarchy'][:-1]:
        for node in taxonomy_tree_dict[level]:
            log_key = f'{level}/{node}'
            if level == drop_level:
                assert log_key not in log
            else:
                assert log_key in log
                is_skipped = False
                if 'msg' in log[log_key]:
                    if 'Skipping; no leaf' in log[log_key]['msg']:
                        is_skipped = True
                if is_skipped:
                    n_skip += 1
                else:
                    assert 'duration' in log[log_key]
                    n_dur += 1

    assert n_dur > 0

    gene_ct = 0
    levels_found = set()
    actual_genes = set()
    for k in actual:
        if k == 'metadata':
            continue
        if k == 'log':
            continue
        if drop_level is not None:
            assert drop_level not in k
        levels_found.add(k.split('/')[0])
        for g in actual[k]:
            actual_genes.add(g)
            assert g in valid_gene_names
            gene_ct += 1
    assert gene_ct > 0

    expected_levels = set(['None'])
    for level in taxonomy_tree_dict['hierarchy'][:-1]:
        if level != drop_level:
            expected_levels.add(level)
    assert expected_levels == levels_found

    if not downsample_genes and n_per_utility == 7 and drop_level is None:
        assert actual_genes == set(full_marker_name_fixture)
    elif downsample_genes:
        assert actual_genes != set(full_marker_name_fixture)

    assert 'metadata' in actual
    assert 'timestamp' in actual['metadata']
    assert 'config' in actual['metadata']
    for k in config:
        assert k in actual['metadata']['config']
        assert actual['metadata']['config'][k] == config[k]


def test_transposing_markers(
        ref_marker_path_fixture,
        tmp_dir_fixture):
    """
    Test transposition of sparse array using 'realistic'
    reference marker data.
    """

    src_path = mkstemp_clean(
        dir=tmp_dir_fixture,
        suffix='.h5')

    with h5py.File(ref_marker_path_fixture, 'r') as src:
        n_rows = src['n_pairs'][()]
        n_cols = len(json.loads(src['gene_names'][()].decode('utf-8')))
        indices = src['sparse_by_pair/up_gene_idx'][()]
        indptr = src['sparse_by_pair/up_pair_idx'][()]

    data = (indices+1)**2
    csr = scipy.sparse.csr_array(
        (data, indices, indptr),
        shape=(n_rows, n_cols))

    expected_csc = scipy.sparse.csc_array(
        csr.toarray())

    with h5py.File(src_path, 'w') as dst:
        dst.create_dataset('data', data=data, chunks=(1000,))
        dst.create_dataset('indices', data=indices, chunks=(1000,))
        dst.create_dataset('indptr', data=indptr)

    dst_path = mkstemp_clean(
        dir=tmp_dir_fixture,
        suffix='.h5')

    transpose_sparse_matrix_on_disk_v2(
        h5_path=src_path,
        indices_tag='indices',
        indptr_tag='indptr',
        data_tag='data',
        indices_max=n_cols,
        max_gb=1,
        n_processors=3,
        output_path=dst_path,
        verbose=False,
        tmp_dir=tmp_dir_fixture)

    with h5py.File(dst_path, 'r') as src:
        actual_data = src['data'][()]
        actual_indices = src['indices'][()]
        actual_indptr = src['indptr'][()]

    assert actual_indices.shape == expected_csc.indices.shape

    np.testing.assert_array_equal(
        actual_indptr,
        expected_csc.indptr)

    np.testing.assert_array_equal(
        actual_indices[-10:],
        expected_csc.indices[-10:])

    actual_csc = scipy.sparse.csc_matrix(
        (actual_data, actual_indices, actual_indptr),
        shape=(n_rows,n_cols))

    np.testing.assert_array_equal(
        csr.toarray(), actual_csc.toarray())
