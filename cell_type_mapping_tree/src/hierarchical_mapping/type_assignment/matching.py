import h5py
import numpy as np

from hierarchical_mapping.diff_exp.scores import (
    aggregate_stats,
    read_precomputed_stats)

from hierarchical_mapping.utils.taxonomy_utils import (
    convert_tree_to_leaves)


def assemble_query_data(
        full_query_data,
        mean_profile_lookup,
        taxonomy_tree,
        marker_cache_path,
        parent_node):
    """
    Returns
    --------
    query_data
        (n_query_cells, n_markers)
    reference_data
        (n_reference_cells, n_markers)
    reference_types
        At the level of this query (i.e. the direct
        children of parent_node)
    """

    tree_as_leaves = convert_tree_to_leaves(taxonomy_tree)
    hierarchy = taxonomy_tree['hierarchy']
    level_to_idx = {level: idx for idx, level in enumerate(hierarchy)}

    if parent_node is None:
        parent_grp = 'None'
        immediate_children = list(taxonomy_tree[hierarchy[0]].keys())
        child_level = hierarchy[0]

    else:
        parent_grp = f"{parent_node[0]}/{parent_node[1]}"

        immediate_children = list(
            taxonomy_tree[parent_node[0]][parent_node[1]])

        child_level = hierarchy[level_to_idx[parent_node[0]]+1]

    immediate_children.sort()

    leaf_to_type = dict()
    for child in immediate_children:
        for leaf in tree_as_leaves[child_level][child]:
            leaf_to_type[leaf] = child

    with h5py.File(marker_cache_path, 'r', swmr=True) as in_file:
        reference_markers = in_file[parent_grp]['reference'][()]
        query_markers = in_file[parent_grp]['query'][()]

    query_data = full_query_data[:, query_markers]

    n_reference = len(leaf_to_type)
    reference_data = np.zeros((n_reference, len(reference_markers)),
                              dtype=float)
    reference_types = []
    children = list(leaf_to_type.keys())
    children.sort()
    for ii, child in enumerate(children):
        reference_types.append(leaf_to_type[child])
        this_mu = mean_profile_lookup[child]
        reference_data[ii, :] = this_mu[reference_markers]

    return {'query_data': query_data,
            'reference_data': reference_data,
            'reference_types': reference_types}


def get_leaf_means(
        taxonomy_tree,
        precompute_path):
    """
    Returns a lookup from leaf node name to mean
    gene expression array
    """
    precomputed_stats = read_precomputed_stats(precompute_path)
    hierarchy = taxonomy_tree['hierarchy']
    leaf_level = hierarchy[-1]
    leaf_names = list(taxonomy_tree[leaf_level].keys())
    result = dict()
    for leaf in leaf_names:

        # gt1/0 threshold do not actually matter here
        stats = aggregate_stats(
                    leaf_population=[leaf,],
                    precomputed_stats=precomputed_stats['cluster_stats'],
                    gt0_threshold=1,
                    gt1_threshold=0)
        result[leaf] = stats['mean']
    return result