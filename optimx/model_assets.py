import os
import glob
from math import log2
import traceback
import warnings
from pathlib import Path, PurePosixPath
from datetime import datetime
import hashlib
import re

from optimx.assets.remote import StorageProvider
from optimx.utils.file_utils import data_dir
from optimx.utils.addict import Dict
from optimx.ext import YAMLDataSet

DEFAULT_WORKING_DIR = data_dir()
ALLOWED_ENV = ["dev", "prod", "preprod"]


def get_size(dir_path):
    if os.path.isfile(dir_path):
        return os.stat(dir_path).st_size
    return sum(
        os.stat(f).st_size
        for f in glob.iglob(os.path.join(dir_path, "**/*"), recursive=True)
        if os.path.isfile(f)
    )


def filemd5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(int(1e7)), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def human_readable_file_size(size):
    # Taken from Dipen Panchasara
    # https://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    _suffixes = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    order = int(log2(size) / 10) if size else 0
    return "{:.4g} {}".format(size / (1 << (order * 10)), _suffixes[order])


def getattrib(fname, dir_path):
    on_not_exist = "warn"
    p = Path(dir_path) / fname
    if not p.exists():
        if on_not_exist == "warn":
            warnings.warn("Local file {} does not exist".format(fname))
            return None
    dtmod = datetime.fromtimestamp(p.stat().st_mtime)
    crc = filemd5(p)
    return {
        "file_path": str(p),
        "filename": fname,
        "modified_at": dtmod,
        "size": human_readable_file_size(get_size(str(p))),
        "crc": crc,
    }


def get_file_info(env, name, version, filenames, working_dir=DEFAULT_WORKING_DIR):
    env_base_path = os.path.join(working_dir, env, name, version)
    filesall = [getattrib(fname, env_base_path) for fname in filenames]
    filesall_real = [finfo for finfo in filesall if finfo]
    return filesall_real


def get_models_meta(env, working_dir=DEFAULT_WORKING_DIR, provider="local"):
    storage_provider = StorageProvider(
        provider=provider,
        bucket=f"{working_dir}",
        prefix=env,
    )
    model_infos = Dict()
    try:
        env_base_path = os.path.join(working_dir, env)
        for model_asset_name, versions_list in storage_provider.iterate_assets():
            # print(asset_name, versions_list,storage_provider.get_versions_info(asset_name))
            model_infos[model_asset_name]["version_list"] = sorted(
                list(set(versions_list)), key=str, reverse=True
            )
            max_version = "0.0"
            if len(versions_list) > 0:
                max_version = max(
                    versions_list, key=lambda x: float(re.findall(r"(\d+.\d+)", x)[0])
                )
            for version in versions_list:
                try:
                    model_version_info = storage_provider.get_asset_meta(
                        model_asset_name, version
                    )
                    ori_contents = model_version_info.get("contents", [])
                    version_files_path = os.path.join(
                        env_base_path, model_asset_name, version
                    )
                    model_infos[model_asset_name][version][
                        "version_files_path"
                    ] = version_files_path
                    # asset_path="/Users/leepand/.optimx/dev/persional_model/0.1"
                    # asset_path += "/" if not asset_path.endswith("/") else ""
                    version_files_path += (
                        "/" if not version_files_path.endswith("/") else ""
                    )

                    ori_contents = sorted(
                        f[len(version_files_path) :]
                        for f in glob.iglob(
                            os.path.join(version_files_path, "**/*"), recursive=True
                        )
                        if os.path.isfile(f) and not f.endswith("pyc")
                    )
                    model_version_info["contents"] = ori_contents

                    model_infos[model_asset_name][version] = model_version_info

                    model_infos[model_asset_name][version]["size"] = "0 KB"
                    if os.path.exists(version_files_path):
                        model_infos[model_asset_name][version][
                            "size"
                        ] = human_readable_file_size(get_size(version_files_path))

                    if f"config/server_{env}.yml" in model_version_info.get(
                        "contents", []
                    ):
                        file_path = os.path.join(
                            env_base_path,
                            model_asset_name,
                            version,
                            f"config/server_{env}.yml",
                        )
                        if os.path.exists(file_path):
                            config = YAMLDataSet(str(file_path)).load()
                            recom_ports = config.get("recomserver", {}).get("ports", [])
                            reward_ports = config.get("rewardserver", {}).get(
                                "ports", []
                            )
                            if max_version == version:
                                model_infos[model_asset_name][
                                    "recom_ports"
                                ] = recom_ports
                                model_infos[model_asset_name][
                                    "reward_ports"
                                ] = reward_ports
                except:
                    print(traceback.format_exc())
                    continue
    except:
        print(traceback.format_exc())
        pass

    return model_infos
