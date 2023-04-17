import pytest

import copy
import h5py
import json
import numpy as np
import pathlib

from hierarchical_mapping.utils.utils import (
    _clean_up)

from hierarchical_mapping.utils.taxonomy_utils import (
    convert_tree_to_leaves)

from hierarchical_mapping.type_assignment.matching import (
    assemble_query_data)

from hierarchical_mapping.cell_by_gene.cell_by_gene import (
    CellByGeneMatrix)


@pytest.fixture
def n_genes():
    return 35

@pytest.fixture
def n_markers():
    return 17

@pytest.fixture
def tree_fixture():
    return {
        'hierarchy': ['class', 'subclass', 'cluster'],
        'class': {
            'A': set(['bb', 'cc']),
            'B': set(['aa', 'dd', 'ee']),
            'C': set(['ff'])
        },
        'subclass': {
            'aa': set(['1', '3', '4']),
            'bb': set(['2',]),
            'cc': set(['0', '5', '6']),
            'dd': set(['8']),
            'ee': set(['7', '9']),
            'ff': set(['10', '11', '12'])
        },
        'cluster': {
            '0': [0, 1, 2],
            '1': [3, 5],
            '2': [4, 6, 7],
            '3': [8, 11],
            '4': [9, 12],
            '5': [10, 13],
            '6': [14,],
            '7': [15, 16, 18],
            '8': [17, 20],
            '9': [19, 21, 22],
            '10': [23, 24],
            '11': [25,],
            '12': [26, 27]
        }
    }


@pytest.fixture
def marker_fixture(n_genes, n_markers):
    rng = np.random.default_rng(22310)
    ref = rng.choice(np.arange(n_genes), n_markers, replace=False)
    query = rng.choice(np.arange(n_genes), n_markers, replace=False)
    assert not np.array_equal(ref, query)

    ref_names = [f'dummy_{ii}' for ii in range(n_genes)]
    query_names = [f'other_dummy_{ii}' for ii in range(n_genes)]
    for ii, (r, q) in enumerate(zip(ref, query)):
        n = f'marker_{ii}'
        ref_names[r] = n
        query_names[q] = n

    return {'reference': ref,
            'query': query,
            'reference_names': ref_names,
            'query_names': query_names}


@pytest.fixture
def mean_lookup_fixture(tree_fixture, n_genes):
    rng = np.random.default_rng(16623)
    result = dict()
    for k in tree_fixture['cluster'].keys():
        result[k] = rng.random(n_genes)
    return result



@pytest.mark.parametrize(
    "parent_node, expected_n_reference, expected_types, expected_clusters",
    [(None, 13, ['A', 'B', 'C', 'C', 'C', 'A', 'B', 'B', 'A', 'A', 'B', 'B', 'B'],
     [str(ii) for ii in range(13)]),
     (('subclass', 'cc'), 3, ['0', '5', '6'], ['0', '5', '6']),
     (('class', 'B'), 6, ['aa', 'aa', 'aa', 'ee', 'dd', 'ee'], ['1', '3', '4', '8', '7', '9'])
    ])
def test_assemble_query_data(
        tree_fixture,
        marker_fixture,
        mean_lookup_fixture,
        n_genes,
        n_markers,
        parent_node,
        expected_n_reference,
        expected_types,
        expected_clusters,
        tmp_path_factory):

    tmp_dir = pathlib.Path(tmp_path_factory.mktemp('for_reference'))
    marker_cache_path = tmp_dir / 'marker_cache.h5'

    if parent_node is None:
        parent_grp = 'None'
    else:
        parent_grp = f"{parent_node[0]}/{parent_node[1]}"

    with h5py.File(marker_cache_path, 'w') as out_file:
        out_file.create_dataset(f"{parent_grp}/reference",
            data=marker_fixture['reference'])
        out_file.create_dataset(f"{parent_grp}/query",
            data=marker_fixture['query'])
        out_file.create_dataset(
            'reference_gene_names',
            data=json.dumps(marker_fixture['reference_names']).encode('utf-8')),
        out_file.create_dataset(
            'query_gene_names',
            data=json.dumps(marker_fixture['query_names']).encode('utf-8'))
        all_query_markers = np.sort(np.array(marker_fixture['query']))
        out_file.create_dataset('all_query_markers',
                                data=all_query_markers)

    rng = np.random.default_rng(44553)
    n_query = 17
    full_query_data = rng.random((n_query, n_genes))

    with h5py.File(marker_cache_path, 'r') as in_file:
        query_gene_id = json.loads(
                             in_file["query_gene_names"][()].decode("utf-8"))
        query_markers = [query_gene_id[ii]
                         for ii in in_file['all_query_markers'][()]]

    assert len(query_markers) < n_genes

    query_cell_by_gene = CellByGeneMatrix(
        data=full_query_data,
        gene_identifiers=query_gene_id,
        normalization="log2CPM")

    query_cell_by_gene.downsample_genes_in_place(
        selected_genes=query_markers)

    actual = assemble_query_data(
            full_query_data=query_cell_by_gene,
            mean_profile_lookup=mean_lookup_fixture,
            taxonomy_tree=tree_fixture,
            marker_cache_path=marker_cache_path,
            parent_node=parent_node)

    assert actual['query_data'].n_cells == n_query
    assert actual['query_data'].n_genes == n_markers

    for ii in range(n_query):
        for jj in range(n_markers):
            jj_o = marker_fixture['query'][jj]
            assert actual['query_data'].data[ii, jj] == full_query_data[ii, jj_o]

    assert actual['reference_types'] == expected_types
    assert actual['reference_data'].shape == (expected_n_reference, n_markers)

    cluster_list = copy.deepcopy(expected_clusters)
    cluster_list.sort()
    for ii, ref in enumerate(cluster_list):
        for jj in range(n_markers):
            jj_o = marker_fixture['reference'][jj]
            assert actual['reference_data'][ii, jj] == mean_lookup_fixture[ref][jj_o]

    _clean_up(tmp_dir)
