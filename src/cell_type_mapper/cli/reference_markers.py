import argschema
import copy
import h5py
import json
import pathlib
import time

from cell_type_mapper.utils.utils import get_timestamp

from cell_type_mapper.utils.anndata_utils import (
    read_df_from_h5ad)

from cell_type_mapper.diff_exp.markers import (
    find_markers_for_all_taxonomy_pairs)

from cell_type_mapper.taxonomy.taxonomy_tree import (
    TaxonomyTree)


class ReferenceMarkerSchema(argschema.ArgSchema):

    precomputed_path_list = argschema.fields.List(
        argschema.fields.InputFile,
        required=True,
        default=None,
        allow_none=False,
        cli_as_single_argument=True,
        description=(
            "List of paths to precomputed stats files "
            "for which reference markers will be computed"))

    query_path = argschema.fields.InputFile(
        required=False,
        default=None,
        allow_none=True,
        description=(
            "Optional path to h5ad file containing query data. Used "
            "to assemble list of genes that are acceptable "
            "as markers."
        ))

    output_dir = argschema.fields.OutputDir(
        required=True,
        default=None,
        allow_none=False,
        description=(
            "Path to directory where refernce marker files "
            "will be written. Specific file names will be inferred "
            "from precomputed stats files."))

    clobber = argschema.fields.Boolean(
        required=False,
        default=False,
        allow_none=False,
        description=("If False, do not allow overwrite of existing "
                     "output files."))

    drop_level = argschema.fields.String(
        required=False,
        default=None,
        allow_none=True,
        description=("Optional level to drop from taxonomy"))

    tmp_dir = argschema.fields.OutputDir(
        required=False,
        default=None,
        allow_none=True,
        description=("Temporary directory for writing out "
                     "scratch files"))

    n_processors = argschema.fields.Int(
        required=False,
        default=32,
        allow_none=False,
        description=("Number of independent processors to spin up."))

    exact_penetrance = argschema.fields.Boolean(
        required=False,
        default=False,
        allow_none=False,
        description=("If False, allow genes that technically fail "
                     "penetrance and fold-change thresholds to pass "
                     "through as reference genes."))

    p_th = argschema.fields.Float(
        required=False,
        default=0.01,
        allow_none=False,
        description=("The corrected p-value that a gene's distribution "
                     "differs between two clusters must be less than this "
                     "for that gene to be considered a marker gene."))

    q1_th = argschema.fields.Float(
        required=False,
        default=0.5,
        allow_none=False,
        description=("Threshold on q1 (fraction of cells in at "
                     "least one cluster of a pair that express "
                     "a gene above 1 CPM) for a gene to be considered "
                     "a marker"))

    q1_min_th = argschema.fields.Float(
        required=False,
        default=0.1,
        allow_none=False,
        description=("If q1 less than this value, a gene "
                     "cannot be considered a marker, even if "
                     "exact_penetrance is False"))

    qdiff_th = argschema.fields.Float(
        required=False,
        default=0.7,
        allow_none=False,
        description=("Threshold on qdiff (differential penetrance) "
                     "above which a gene is considered a marker gene"))

    qdiff_min_th = argschema.fields.Float(
        required=False,
        default=0.1,
        allow_none=False,
        description=("If qdiff less than this value, a gene "
                     "cannot be considered a marker, even if "
                     "exact_penetrance is False"))

    log2_fold_th = argschema.fields.Float(
        required=False,
        default=1.0,
        allow_none=False,
        description=("The log2 fold change of a gene between two "
                     "clusters should be above this for that gene "
                     "to be considered a marker gene"))

    log2_fold_min_th = argschema.fields.Float(
        required=False,
        default=0.8,
        allow_none=False,
        description=("If the log2 fold change of a gene between two "
                     "clusters is less than this value, that gene cannot "
                     "be a marker, even if exact_penetrance is False"))

    n_valid = argschema.fields.Int(
        required=False,
        default=30,
        allow_none=False,
        description=("Try to find this many marker genes per pair. "
                     "Used only if exact_penetrance is False."))


class ReferenceMarkerRunner(argschema.ArgSchemaParser):

    default_schema = ReferenceMarkerSchema

    def run(self):

        input_to_output = self.create_input_to_output_map()

        parent_metadata = {
            'config': self.args,
            'timestamp': get_timestamp(),
            'input_to_output_map': input_to_output
        }

        taxonomy_tree = None

        t0 = time.time()

        if self.args['query_path'] is not None:
            gene_list = list(
                read_df_from_h5ad(
                    self.args['query_path'],
                    df_name='var').index.values)
        else:
            gene_list = None

        for precomputed_path in input_to_output:
            output_path = input_to_output[precomputed_path]
            print(f'writing {output_path}')
            taxonomy_tree = TaxonomyTree.from_precomputed_stats(
                stats_path=precomputed_path)

            if self.args['drop_level'] is not None:
                taxonomy_tree = taxonomy_tree.drop_level(
                    self.args['drop_level'])

            find_markers_for_all_taxonomy_pairs(
                precomputed_stats_path=precomputed_path,
                taxonomy_tree=taxonomy_tree,
                output_path=output_path,
                tmp_dir=self.args['tmp_dir'],
                n_processors=self.args['n_processors'],
                exact_penetrance=self.args['exact_penetrance'],
                p_th=self.args['p_th'],
                q1_th=self.args['q1_th'],
                q1_min_th=self.args['q1_min_th'],
                qdiff_th=self.args['qdiff_th'],
                qdiff_min_th=self.args['qdiff_min_th'],
                log2_fold_th=self.args['log2_fold_th'],
                log2_fold_min_th=self.args['log2_fold_min_th'],
                n_valid=self.args['n_valid'],
                gene_list=gene_list)

            metadata = copy.deepcopy(parent_metadata)
            metadata['precomputed_path'] = precomputed_path

            metadata_str = json.dumps(metadata)
            with h5py.File(output_path, 'a') as dst:
                dst.create_dataset(
                    'metadata',
                    data=metadata_str.encode('utf-8'))

        dur = time.time()-t0
        print(f"completed in {dur:.2e} seconds")

    def create_input_to_output_map(self):
        """
        Return dict mapping input paths to output paths
        """

        output_dir = pathlib.Path(self.args['output_dir'])

        input_to_output = dict()
        files_to_write = set()

        # salting of output file names is done in the case where
        # multiple precomputed files would result in the same
        # refrence marker path name
        salt = None
        for input_path in self.args['precomputed_path_list']:
            input_path = pathlib.Path(input_path)
            input_name = input_path.name
            name_params = input_name.split('.')
            old_stem = name_params[0]
            new_path = None
            while True:
                if new_path is not None:
                    if salt is None:
                        salt = 0
                    else:
                        salt += 1
                new_stem = 'reference_markers'
                if salt is not None:
                    new_stem = f'{new_stem}.{salt}'
                new_name = input_name.replace(old_stem, new_stem, 1)
                new_path = str(output_dir/new_name)
                if new_path not in files_to_write:
                    files_to_write.add(new_path)
                    break
            input_to_output[str(input_path)] = new_path

        # check that none of the output files exist (or, if they do, that
        # clobber is True)
        error_msg = ""
        for pth in input_to_output.values():
            pth = pathlib.Path(pth)
            if pth.exists():
                if not pth.is_file():
                    error_msg += f"{pth} exists and is not a file\n"
                elif not self.args['clobber']:
                    error_msg += (
                        f"{pth} already exists; to overwrite, run with "
                        "clobber=True\n")

        if len(error_msg) == 0:
            # make sure we can write to these files
            for pth in input_to_output.values():
                pth = pathlib.Path(pth)
                try:
                    with open(pth, 'wb') as dst:
                        dst.write(b'junk')
                    pth.unlink()
                except FileNotFoundError:
                    error_msg += (
                        f"cannot write to {pth}\n"
                    )

        if len(error_msg) > 0:
            error_msg += (
                 "These file names are automatically generated. "
                 "The quickest solution is to specify a new output_dir.")
            raise RuntimeError(error_msg)

        return input_to_output


if __name__ == "__main__":
    runner = ReferenceMarkerRunner()
    runner.run()
