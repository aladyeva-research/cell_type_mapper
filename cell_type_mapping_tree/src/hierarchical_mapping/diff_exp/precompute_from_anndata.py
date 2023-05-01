from typing import Union, List
import anndata
import numpy as np
import h5py
import pathlib
import time

from hierarchical_mapping.utils.utils import (
    print_timing)

from hierarchical_mapping.utils.taxonomy_utils import (
    get_taxonomy_tree)

from hierarchical_mapping.utils.stats_utils import (
    summary_stats_for_chunk)

from hierarchical_mapping.diff_exp.precompute import (
    _create_empty_stats_file)

from hierarchical_mapping.cell_by_gene.cell_by_gene import (
    CellByGeneMatrix)


def precompute_summary_stats_from_h5ad(
        data_path: Union[str, pathlib.Path],
        column_hierarchy: List[str],
        output_path: Union[str, pathlib.Path],
        rows_at_a_time: int = 10000,
        normalization="log2CPM"):
    """
    Precompute the summary stats used to identify marker genes

    Parameters
    ----------
    data_path:
        Path to the h5ad file containing the cell x gene matrix

    column_hierarcy:
        The list of columns denoting taxonomic classes,
        ordered from highest (parent) to lowest (child).

    output_path:
        Path to the HDF5 file that will contain the lookup
        information for the clusters

    col_names:
        Optional list of names associated with the columns
        in the data matrix

    rows_at_a_time:
        Number of rows to load at once from the cell x gene
        matrix

    normalization:
        The normalization of the cell by gene matrix in
        the input file; either 'raw' or 'log2CPM'
    """
    taxonomy_tree = get_taxonomy_tree_from_h5ad(
        h5ad_path=data_path,
        column_hierarchy=column_hierarchy)

    precompute_summary_stats_from_h5ad_and_tree(
        data_path=data_path,
        taxonomy_tree=taxonomy_tree,
        output_path=output_path,
        rows_at_a_time=rows_at_a_time,
        normalization=normalization)


def get_taxonomy_tree_from_h5ad(
        h5ad_path,
        column_hierarchy):
    """
    Get taxonomy tree from an h5ad file
    """
    a_data = anndata.read_h5ad(h5ad_path, backed='r')
    taxonomy_tree = get_taxonomy_tree(
        obs_records=a_data.obs.to_dict(orient='records'),
        column_hierarchy=column_hierarchy)
    return taxonomy_tree


def precompute_summary_stats_from_h5ad_and_tree(
        data_path: Union[str, pathlib.Path],
        taxonomy_tree: dict,
        output_path: Union[str, pathlib.Path],
        rows_at_a_time: int = 10000,
        normalization='log2CPM'):
    """
    Precompute the summary stats used to identify marker genes

    Parameters
    ----------
    data_path:
        Path to the h5ad file containing the cell x gene matrix

    taxonomy_tree: dict
        dict encoding the cell type taxonomy

    output_path:
        Path to the HDF5 file that will contain the lookup
        information for the clusters

    col_names:
        Optional list of names associated with the columns
        in the data matrix

    rows_at_a_time:
        Number of rows to load at once from the cell x gene
        matrix

    normalization:
        The normalization of the cell by gene matrix in
        the input file; either 'raw' or 'log2CPM'
    """
    a_data = anndata.read_h5ad(data_path, backed='r')
    gene_names = a_data.var_names

    column_hierarchy = taxonomy_tree['hierarchy']
    cluster_to_input_row = taxonomy_tree[column_hierarchy[-1]]

    cluster_list = list(cluster_to_input_row)
    cluster_to_output_row = {c: int(ii)
                             for ii, c in enumerate(cluster_list)}
    n_clusters = len(cluster_list)

    n_cells = a_data.X.shape[0]
    n_genes = a_data.X.shape[1]

    col_names = list(a_data.var_names)
    if len(col_names) == 0:
        col_names = None

    # create a numpy array mapping rows (cells) in the h5ad
    # file to rows (clusters) in the output summary file.

    anndata_row_to_output_row = np.zeros(
            n_cells, dtype=int)

    for cluster in cluster_to_input_row:
        these_rows = np.array(cluster_to_input_row[cluster])
        output_idx = cluster_to_output_row[cluster]
        anndata_row_to_output_row[these_rows] = output_idx

    chunk_iterator = a_data.chunked_X(
        chunk_size=rows_at_a_time)

    buffer_dict = dict()
    buffer_dict['n_cells'] = np.zeros(n_clusters, dtype=int)
    buffer_dict['sum'] = np.zeros((n_clusters, n_genes), dtype=float)
    buffer_dict['sumsq'] = np.zeros((n_clusters, n_genes), dtype=float)
    buffer_dict['gt0'] = np.zeros((n_clusters, n_genes), dtype=int)
    buffer_dict['gt1'] = np.zeros((n_clusters, n_genes), dtype=int)

    t0 = time.time()
    print(f"chunking through {data_path}")
    processed_cells = 0
    for chunk in chunk_iterator:
        r0 = chunk[1]
        r1 = chunk[2]
        cluster_chunk = anndata_row_to_output_row[r0:r1]
        for unq_cluster in np.unique(cluster_chunk):
            valid = np.where(cluster_chunk == unq_cluster)[0]
            valid = np.sort(valid)
            this_cluster = chunk[0][valid, :].toarray()
            this_cluster = CellByGeneMatrix(
                data=this_cluster,
                gene_identifiers=gene_names,
                normalization=normalization)

            if this_cluster.normalization != 'log2CPM':
                this_cluster.to_log2CPM_in_place()

            summary_chunk = summary_stats_for_chunk(this_cluster)

            for k in summary_chunk.keys():
                if len(buffer_dict[k].shape) == 1:
                    buffer_dict[k][unq_cluster] += summary_chunk[k]
                else:
                    buffer_dict[k][unq_cluster, :] += summary_chunk[k]

        processed_cells += (r1-r0)
        print_timing(
            t0=t0,
            i_chunk=processed_cells,
            tot_chunks=n_cells,
            unit='hr')

    _create_empty_stats_file(
        output_path=output_path,
        cluster_to_output_row=cluster_to_output_row,
        n_clusters=n_clusters,
        n_genes=n_genes,
        col_names=col_names)

    with h5py.File(output_path, 'a') as out_file:
        for k in buffer_dict.keys():
            if k == 'n_cells':
                out_file[k][:] = buffer_dict[k]
            else:
                out_file[k][:, :] = buffer_dict[k]
