import json
import copy
import argparse
import itertools
from pathlib import Path
from collections import OrderedDict


def generate_configs(base_config, dest_dir, embeddings, grid, refresh, ckpts_path,
                     target):
    with open(base_config, "r") as f:
        base = json.load(f)

    with open(ckpts_path, "r") as f:
        ckpts = json.load(f)

    model_family = {
        "smallnet": {"preproc": {"crop": 15, "imwidth": 100}, "name": "SmallNet"},
        "hourglass": {"preproc": {"crop": 20, "imwidth": 136}, "name": "HourglassNet"},
    }

    for model_name in embeddings:

        # model naming convention: <dataset-tokens>-<model_type>-<embedding-dim>-<dve>
        tokens = model_name.split("-")
        if tokens[-1] == "dve":
            tokens.pop()  # remove dve flag if present to use relative negative offsets
        model_type, embedding_dim = tokens[-2], int(tokens[-1][:-1])
        preproc_kwargs = model_family[model_type]["preproc"]
        
        hparam_vals = [x for x in grid.values()]
        grid_vals = list(itertools.product(*hparam_vals))
        hparams = list(grid.keys())

        if "-ft-keypoints" in target:
            prefix = target.replace("-keypoints", "")
            prefix = prefix.replace("-limit-annos", "")
            prefix = prefix.replace("-no-aug", "")
            ckpt_name = f"{prefix}-{model_name}"
        else:
            ckpt_name = model_name
        epoch = ckpts[ckpt_name]["epoch"]

        for cfg_vals in grid_vals:
            # dest_name = Path(base_config).stem
            config = copy.deepcopy(base)
            for hparam, val in zip(hparams, cfg_vals):
                if hparam == "smax":
                    config["keypoint_regressor"]["softmaxarg_mul"] = val
                elif hparam == "lr":
                    config["optimizer"]["args"]["lr"] = val
                elif hparam == "bs":
                    val = int(val)
                    config["batch_size"] = val
                elif hparam == "upsample":
                    val = bool(val)
                    config["keypoint_regressor_upsample"] = val
                elif hparam == "annos":
                    config["restrict_annos"] = int(val)
                else:
                    raise ValueError(f"unknown hparam: {hparam}")
            ckpt = f"checkpoint-epoch{epoch}.pth"
            timestamp = ckpts[ckpt_name]["timestamp"]
            ckpt_path = Path("data/saved/models") / ckpt_name / timestamp / ckpt
            config["arch"]["type"] = model_family[model_type]["name"]
            config["arch"]["args"]["num_output_channels"] = embedding_dim
            config["dataset"]["args"].update(preproc_kwargs)
            config["finetune_from"] = str(ckpt_path)
            if "-ft" in str(dest_dir) and "-keypoints" not in str(dest_dir):
                loss = "dense_correlation_loss"
                if "dve" in model_name:
                    loss += "_dve"
                config["loss"] = loss
                # avoid OOM for hourglass
                if "hourglass" in model_name:
                    config["batch_size"] = 16
            if "annos" in grid:
                model_name_ = f"{config['restrict_annos']}-annos-{model_name}"
            else:
                model_name_ = model_name
            if len(grid["lr"]) > 1:
                model_name_ = f"{model_name_}-lr{config['optimizer']['args']['lr']}"
            if len(grid["bs"]) > 1:
                model_name_ = f"{model_name_}-bs{config['batch_size']}"
            
            
            dest_path = Path(dest_dir) / f"{model_name_}.json"
            dest_path.parent.mkdir(exist_ok=True, parents=True)
            if not dest_path.exists() or refresh:
                with open(str(dest_path), "w") as f:
                    json.dump(config, f, indent=4, sort_keys=False)
            else:
                print(f"config file at {str(dest_path)} exists, skipping....")
        print(f"Wrote {len(grid_vals)} configs to disk")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpts_path", default="misc/server-checkpoints.json")
    parser.add_argument('--bs', default="32")
    parser.add_argument('--smax', default="100")
    parser.add_argument('--lr', default="1E-3")
    parser.add_argument('--annos', default="")
    parser.add_argument('--upsample', default="0")
    parser.add_argument('--refresh', action="store_true")
    parser.add_argument(
        '--target',
        required=True,
        choices=[
            "mafl-keypoints",
            "300w-keypoints",
            "aflw-keypoints",
            "aflw-mtfl-keypoints",
            "300w-ft",
            "aflw-ft",
            "aflw-mtfl-ft",
            "300w-ft-keypoints",
            "aflw-ft-keypoints",
            "aflw-mtfl-ft-keypoints",
            "aflw-mtfl-limit-annos-keypoints",
            "aflw-mtfl-limit-annos-ft-keypoints",
            "aflw-mtfl-limit-annos-no-aug-ft-keypoints",
        ])
    args = parser.parse_args()

    grid_args = OrderedDict()
    keys = ["lr", "bs"]
    if "keypoints" in args.target:
        keys += ["smax", "upsample"]
    if args.annos:
        keys += ["annos"]

    for key in keys:
        grid_args[key] = [float(x) for x in getattr(args, key).split(",")]
    dest_config_dir = Path("configs") / args.target
    base_config_path = Path("configs/templates") / f"{args.target}.json"

    # For the semi-supervised experiment, we just use the strongest models
    if "limit-annos" in args.target:
        pretrained_embeddings = [
            "celeba-smallnet-3d",
            "celeba-smallnet-64d-dve",
            "celeba-hourglass-64d-dve",
        ]
    else:
        pretrained_embeddings = [
            "celeba-smallnet-3d",
            "celeba-smallnet-16d",
            "celeba-smallnet-32d",
            "celeba-smallnet-64d",
            "celeba-smallnet-3d-dve",
            "celeba-smallnet-16d-dve",
            "celeba-smallnet-32d-dve",
            "celeba-smallnet-64d-dve",
            "celeba-hourglass-64d-dve",
        ]

    generate_configs(
        base_config=base_config_path,
        embeddings=pretrained_embeddings,
        ckpts_path=args.ckpts_path,
        refresh=args.refresh,
        dest_dir=dest_config_dir,
        grid=grid_args,
        target=args.target,
    )
