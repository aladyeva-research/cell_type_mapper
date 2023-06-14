import pytest

import anndata
import copy
import h5py
import json
import numpy as np
import pandas as pd
import pathlib
import tempfile

from hierarchical_mapping.utils.utils import (
    mkstemp_clean,
    _clean_up)

from hierarchical_mapping.taxonomy.taxonomy_tree import (
    TaxonomyTree)

from hierarchical_mapping.diff_exp.precompute_from_anndata import (
    precompute_summary_stats_from_h5ad)

from hierarchical_mapping.diff_exp.markers import (
    find_markers_for_all_taxonomy_pairs)

from hierarchical_mapping.type_assignment.marker_cache_v2 import (
    create_marker_cache_from_reference_markers,
    serialize_markers)

from hierarchical_mapping.type_assignment.election import (
    run_type_assignment_on_h5ad)

from hierarchical_mapping.cli.simple_correlation_mapping import (
    CorrMapSpecifiedMarkersRunner)


@pytest.mark.parametrize('use_csv', [True, False])
def test_corrmapper(
        tmp_dir_fixture,
        raw_reference_h5ad_fixture,
        raw_query_h5ad_fixture,
        raw_query_cell_x_gene_fixture,
        expected_cluster_fixture,
        taxonomy_tree_dict,
        query_gene_names,
        marker_gene_names,
        use_csv):

    this_tmp_dir = pathlib.Path(
        tempfile.mkdtemp(
            dir=tmp_dir_fixture))

    precompute_out = this_tmp_dir / 'precomputed.h5'

    config = dict()
    config['tmp_dir'] = str(this_tmp_dir.resolve().absolute())
    config['query_path'] = str(
        raw_query_h5ad_fixture.resolve().absolute())

    config['precomputed_stats'] = {
        'reference_path': str(raw_reference_h5ad_fixture.resolve().absolute()),
        'path': str(precompute_out),
        'normalization': 'raw'}

    tree_path = mkstemp_clean(dir=tmp_dir_fixture, suffix='.json')
    with open(tree_path, 'w') as out_file:
        out_file.write(json.dumps(taxonomy_tree_dict))
    config['precomputed_stats']['taxonomy_tree'] = tree_path

    marker_path = mkstemp_clean(dir=this_tmp_dir, suffix='.json')
    marker_lookup = dict()
    marker_lookup['a'] = marker_gene_names[:3]
    marker_lookup['b'] = marker_gene_names[3:5]
    marker_lookup['c'] = marker_gene_names[2:]
    with open(marker_path, 'w') as out_file:
        out_file.write(json.dumps(marker_lookup))

    config["query_markers"] = {
        'serialized_lookup': marker_path}

    config["type_assignment"] = {
        'n_processors': 3,
        'chunk_size': 1000,
        'normalization': 'raw'}

    result_path = mkstemp_clean(
        dir=this_tmp_dir,
        suffix='.json')

    if use_csv:
        csv_path = mkstemp_clean(
            dir=this_tmp_dir,
            suffix='.csv')
    else:
        csv_path = None

    config['extended_result_path'] = result_path
    config['csv_result_path'] = csv_path
    config['max_gb'] = 1.0

    runner = CorrMapSpecifiedMarkersRunner(
        args=[],
        input_data=config)

    runner.run()

    actual = json.load(open(result_path, 'rb'))
    expected_markers = copy.deepcopy(marker_gene_names)
    expected_markers.sort()
    assert actual['marker_genes'] == expected_markers
    assert len(actual['results']) == raw_query_cell_x_gene_fixture.shape[0]
    cluster_name_set = set(taxonomy_tree_dict['cluster'])
    for el in actual['results']:
        el['cluster']['assignment'] in cluster_name_set

    # make sure reference file still exists
    assert raw_reference_h5ad_fixture.is_file()

    # check consistency between extended and csv results
    if use_csv:
        result_lookup = {
            cell['cell_id']: cell for cell in actual['results']}
        with open(csv_path, 'r') as in_file:
            assert in_file.readline() == f"# metadata = {pathlib.Path(result_path).name}\n"
            assert in_file.readline() == f'# taxonomy hierarchy = ["cluster"]\n'

            hierarchy = ['cluster']
            header_line = 'cell_id'
            for level in hierarchy:
                header_line += f',{level},{level}_confidence'
            header_line += '\n'
            assert in_file.readline() == header_line
            found_cells = []
            for line in in_file:
                params = line.strip().split(',')
                assert len(params) == 2*len(hierarchy)+1
                this_cell = result_lookup[params[0]]
                found_cells.append(params[0])
                for i_level, level in enumerate(hierarchy):
                    assert params[1+2*i_level] == this_cell[level]['assignment']
                    delta = np.abs(this_cell[level]['confidence']-float(params[2+2*i_level]))
                    assert delta < 0.0001

            assert len(found_cells) == len(result_lookup)
            assert set(found_cells) == set(result_lookup.keys())
