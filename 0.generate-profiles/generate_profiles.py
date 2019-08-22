"""
Generate morphological profiles from cell painting data using pycytominer.

Do not perform feature selection since downstream analysis include feature selection
"""

import os
import numpy as np
import pandas as pd

from pycytominer.aggregate import AggregateProfiles
from pycytominer.annotate import annotate
from pycytominer.normalize import normalize
from pycytominer.feature_select import feature_select
from pycytominer.audit import audit

batch = "CRISPR_PILOT_B1"
bucket_dir = os.path.join(
    "/home",
    "ubuntu",
    "bucket",
    "projects",
    "2015_07_01_Cell_Health_Vazquez_Cancer_Broad",
    "workspace",
)

backend_dir = os.path.join(bucket_dir, "backend", batch)
metadata_dir = os.path.join(bucket_dir, "metadata", batch)

# Load Barcode Platemap
barcode_platemap_file = os.path.join(metadata_dir, "barcode_platemap.csv")
barcode_platemap_df = pd.read_csv(barcode_platemap_file)

# Perform analysis for each plate
for plate in os.listdir(backend_dir):
    print("Processing {}.....".format(plate))
    plate_dir = os.path.join(backend_dir, plate)
    sqlite_file = "sqlite:////{}/{}.sqlite".format(plate_dir, plate)

    # Load specific platemap
    platemap = barcode_platemap_df.query(
        "Assay_Plate_Barcode == @plate"
    ).Plate_Map_Name.values[0]
    platemap_file = os.path.join(metadata_dir, "platemap", "{}.csv".format(platemap))
    platemap_df = pd.read_csv(platemap_file)

    # Prepare sql file for processing
    ap = AggregateProfiles(
        sqlite_file, strata=["Image_Metadata_Plate", "Image_Metadata_Well"]
    )

    # Count cells and output
    cell_count_file = os.path.join("results", "{}_cell_count.tsv".format(plate))
    cell_count_df = ap.count_cells()
    cell_count_df = cell_count_df.merge(
        platemap_df, left_on="Image_Metadata_Well", right_on="well_position"
    ).drop(["WellRow", "WellCol", "well_position"], axis="columns")
    cell_count_df.to_csv(cell_count_file, sep="\t", index=False)

    # Being processing profiles
    output_dir = os.path.join("data", "profiles", batch, plate)
    os.makedirs(output_dir, exist_ok=True)

    # Aggregate single cells into well profiles
    out_file = os.path.join(output_dir, "{}.csv".format(plate))
    ap.aggregate_profiles(output_file=out_file)

    # Annotate Profiles
    anno_file = os.path.join(output_dir, "{}_augmented.csv".format(plate))
    annotate(
        profiles=out_file,
        platemap=platemap_df,
        join_on=["Metadata_well_position", "Image_Metadata_Well"],
        output_file=anno_file,
    )

    # Extract features to normalize
    # currently a bug in inferring cell painting features from metadata, use a workaround for now
    # https://github.com/cytomining/pycytominer/issues/39
    features = pd.read_csv(anno_file).columns.tolist()
    features = [
        x
        for x in features
        if (
            x.startswith("Cells_")
            | x.startswith("Nuclei_")
            | x.startswith("Cytoplasm_")
        )
    ]

    # Normalize Profiles
    norm_file = os.path.join(output_dir, "{}_normalized.csv".format(plate))
    normalize(
        profiles=anno_file, features=features, samples="all", output_file=norm_file
    )

    # Perform feature selection (just drop columns with high number of missingness)
    feat_file = os.path.join(
        output_dir, "{}_normalized_feature_select.csv".format(plate)
    )
    feature_select(
        profiles=norm_file,
        features=features,
        samples="none",
        operation="drop_na_columns",
        output_file=feat_file,
    )

    # Perform audits
    profile_df = pd.read_csv(feat_file).drop(
        ["Image_Metadata_Well", "Image_Metadata_Plate"], axis="columns"
    )

    # Audit guide replicability
    audit_file = os.path.join("results", "{}_audit_guide.csv".format(plate))
    audit(
        profiles=profile_df,
        groups=["Metadata_pert_name", "Metadata_gene_name", "Metadata_cell_line"],
        iterations=10,
        output_file=audit_file,
    )

    # Audit gene replicability
    audit_file = os.path.join("results", "{}_audit_gene.csv".format(plate))
    audit(
        profiles=profile_df,
        groups=["Metadata_gene_name", "Metadata_cell_line"],
        iterations=10,
        output_file=audit_file,
    )
