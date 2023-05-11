import h5py
import json
import numpy as np
import time

from hierarchical_mapping.marker_selection.selection_pipeline import (
    select_all_markers)


def create_marker_cache_from_reference_markers(
        output_cache_path,
        input_cache_path,
        query_gene_names,
        taxonomy_tree,
        n_per_utility=15,
        n_processors=6,
        behemoth_cutoff=10000000):
    """
    Populate the temporary HDF5 file with the lists of marker
    genes for each parent node.

    Parameters
    ----------
    output_cache_path:
        The file to be written
    input_cache_path:
        Path to the cache of marker gene data from the
        reference dataset
    query_gene_names:
        list of gene names in the query dataset
    taxonomy_tree:
        Dict encoding the cell type taxonomy
    n_per_utility:
        How many genes to select per (taxon_pair, sign)
        combination
    n_processors:
        Number of independent workers to spin up.
    behemoth_cutoff:
        Number of leaf nodes for a parent to be considered
        a behemoth
    """
    print(f"creating marker gene cache in {output_cache_path}")
    t0 = time.time()

    # create a dict mapping from parent_node to
    # lists of marker gene names
    marker_lookup = select_all_markers(
        marker_cache_path=input_cache_path,
        query_gene_names=query_gene_names,
        taxonomy_tree=taxonomy_tree,
        n_per_utility=n_per_utility,
        n_processors=n_processors,
        behemoth_cutoff=behemoth_cutoff)

    parent_node_list = list(marker_lookup.keys())
    with h5py.File(output_cache_path, 'w') as out_file:
        out_file.create_dataset(
            'parent_node_list',
            data=json.dumps(parent_node_list).encode('utf-8'))

    with h5py.File(input_cache_path, 'r') as in_file:
        reference_gene_names = json.loads(
            in_file['full_gene_names'][()].decode('utf-8'))

    query_name_to_int = {
        n: ii for ii, n in enumerate(query_gene_names)}
    reference_name_to_int = {
        n: ii for ii, n in enumerate(reference_gene_names)}

    # all of the indexes of genes that get used as markers
    query_genes = set()
    reference_genes = set()
    for parent in marker_lookup:
        for gene in marker_lookup[parent]:
            query_genes.add(query_name_to_int[gene])
            reference_genes.add(reference_name_to_int[gene])
    query_genes = np.sort(np.array(list(query_genes)))
    reference_genes = np.sort(np.array(list(reference_genes)))

    created_groups = set()
    with h5py.File(output_cache_path, "a") as cache_file:
        cache_file.create_dataset(
            "all_query_markers",
            data=query_genes)
        cache_file.create_dataset(
            "all_reference_markers",
            data=reference_genes)
        cache_file.create_dataset(
            "query_gene_names",
            data=json.dumps(query_gene_names).encode("utf-8"))
        cache_file.create_dataset(
            "reference_gene_names",
            data=json.dumps(reference_gene_names).encode('utf-8'))

        for parent in marker_lookup:
            if parent is None:
                level = None
                node = 'None'
                parent_grp = 'None'
            else:
                level = parent[0]
                node = parent[1]
                parent_grp = f'{parent[0]}/{parent[1]}'

            if parent_grp in created_groups:
                raise RuntimeError(
                    "tried to create query marker group\n"
                    f"{parent_grp}\n"
                    "more than once")

            created_groups.add(parent_grp)

            if level is not None:
                if level not in cache_file:
                    level_grp = cache_file.create_group(level)
                else:
                    level_grp = cache_file[level]
                out_grp = level_grp.create_group(node)
            else:
                out_grp = cache_file.create_group(node)

            these_reference = []
            these_query = []
            for gene in marker_lookup[parent]:
                these_reference.append(reference_name_to_int[gene])
                these_query.append(query_name_to_int[gene])
            out_grp.create_dataset(
                'reference',
                data=np.array(these_reference))
            out_grp.create_dataset(
                'query',
                data=np.array(these_query))
    duration = (time.time()-t0)/3600.0
    print(f"created {output_cache_path} in {duration:.2e} hours")
