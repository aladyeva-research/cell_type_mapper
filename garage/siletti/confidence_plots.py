from cell_type_mapper.taxonomy.taxonomy_tree import TaxonomyTree
from cell_type_mapper.diff_exp.score_utils import (
    read_precomputed_stats)
from cell_type_mapper.utils.anndata_utils import (
    read_df_from_h5ad)

import copy
import json
import numpy as np
import pandas as pd
import pathlib

import matplotlib.figure as mfig
from matplotlib.backends.backend_pdf import PdfPages



def main():


    bakeoff_dir = pathlib.Path(
        "/allen/aibs/technology/danielsf/knowledge_base/siletti/bakeoff")
    assert bakeoff_dir.is_dir()

    mouse_path_list = [
        bakeoff_dir / "mouse_f0.9.json",
        bakeoff_dir / "mouse_f0.25.json",
    ]

    human_path_list = [
        bakeoff_dir / "human_f0.9.json",
        bakeoff_dir / "human_f0.25.json"
    ]

    output_path = "figures/confidence_distribution.pdf"
    with PdfPages(output_path) as pdf_handle:
        plot_species_comparison(
            mapping_path_list=human_path_list,
            pdf_handle=pdf_handle,
            drop_level=None)

        plot_species_comparison(
            mapping_path_list=mouse_path_list,
            pdf_handle=pdf_handle,
            drop_level='CCN20230722_SUPT')


def plot_species_comparison(
        mapping_path_list,
        pdf_handle,
        drop_level=None,
        fontsize=20):
    """
    Assumes every mapping in mapping_path_list has the same taxonomy
    tree and query path
    """
    config = json.load(open(mapping_path_list[0], 'rb'))['config']
    taxonomy_tree = TaxonomyTree.from_precomputed_stats(
        config['precomputed_stats']['path'])

    if drop_level is not None:
        taxonomy_tree = taxonomy_tree.drop_level(drop_level)

    truth_path= config['query_path']
    truth_obs = read_df_from_h5ad(truth_path, df_name='obs')

    truth = dict()
    for level in taxonomy_tree.hierarchy:
        for cell, val in zip(truth_obs.index.values, truth_obs[level].values):
            if cell not in truth:
                truth[cell] = dict()
            truth[cell][level] = val

    fig = mfig.Figure(
        figsize=(2*20, len(taxonomy_tree.hierarchy)*20))
    axis_lookup = dict()
    for i_level, level in enumerate(taxonomy_tree.hierarchy):
        axis_lookup[level] = dict()
        for i_k, k in enumerate(('cdf', 'pdf')):
            axis_lookup[level][k] = fig.add_subplot(
                len(taxonomy_tree.hierarchy), 2,
                1+i_level*2 + i_k)

    for mapping_path, color in zip(mapping_path_list, ('r', 'g')):
        mapping = json.load(open(mapping_path,'rb'))
        this_config = mapping['config']
        assert this_config['query_path'] == config['query_path']
        assert this_config[
            'precomputed_stats']['path'] == config['precomputed_stats']['path']
        mapping = {c['cell_id']: c for c in mapping['results']}

        legend_label = (
            f'fraction: {this_config["type_assignment"]["bootstrap_factor"]:.2e}'
        )

        for i_level, level in enumerate(taxonomy_tree.hierarchy):
            axis = axis_lookup[level]['cdf']
            plot_cdf_comparison(
                axis=axis,
                taxonomy_tree=taxonomy_tree,
                mapping=mapping,
                truth=truth,
                level=level,
                binsize=0.01,
                color=color,
                legend_label=legend_label)

    for level in taxonomy_tree.hierarchy:
        axis = axis_lookup[level]['cdf']
        axis.set_title(level, fontsize=fontsize)
        axis.set_xlabel('probability', fontsize=fontsize)
        axis.set_ylabel('cumulative distribution', fontsize=fontsize)
        axis.legend(loc=0, fontsize=fontsize)

    fig.tight_layout()

    pdf_handle.savefig(fig)


def plot_cdf_comparison(
        axis,
        taxonomy_tree,
        mapping,
        truth,
        level,
        binsize=0.1,
        color='b',
        legend_label=None):

    (bins,
     expected,
     actual) = get_rate_lookup_cdf(
        taxonomy_tree=taxonomy_tree,
        mapping=mapping,
        truth=truth,
        level=level,
        binsize=binsize)

    axis.plot(bins, actual, label=legend_label, c=color)
    axis.plot(bins, expected, c=color, linestyle='--')



def get_rate_lookup_cdf(
        taxonomy_tree,
        mapping,
        truth,
        level,
        binsize=0.1):

    bins = np.arange(binsize, 1.0+binsize, binsize)

    true_prob = []
    false_prob = []
    all_prob = []

    for cell_id in mapping:
        is_true = (mapping[cell_id][level]['assignment']
                   == truth[cell_id][level])

        prob = 1.0
        for l in taxonomy_tree.hierarchy:
            prob *= mapping[cell_id][l]['bootstrapping_probability']
            if l == level:
                break
        if is_true:
            true_prob.append(prob)
        else:
            false_prob.append(prob)
        all_prob.append(prob)

    true_prob = np.array(true_prob)
    false_prob = np.array(false_prob)
    all_prob = np.array(all_prob)

    expected = []
    actual = []
    used_bins = []
    for b in bins:
        expected_mask = (all_prob<=b)
        this_true = (true_prob<=b).sum()
        this_false = (false_prob<=b).sum()

        if len(expected_mask) == 0:
            continue
        if this_true+this_false == 0:
            continue

        used_bins.append(b)
        expected.append(all_prob[expected_mask].sum()/expected_mask.sum())   
        denom = max(1, this_true+this_false)
        actual.append(this_true/denom)
    return np.array(used_bins), np.array(expected), np.array(actual) 



if __name__ == "__main__":
    main()
