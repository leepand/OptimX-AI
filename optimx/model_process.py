from mlopskit.pipe import ConfigManager, Pipe
from pathlib import Path, PurePosixPath
from mlopskit.utils.file_utils import data_dir, get_first_level_directories
from mlopskit.ext import YAMLDataSet

import warnings
import os
import json
from math import log2
from datetime import datetime

import hashlib
import re


def compare_versions(version1, version2):
    pattern = r"v(\d+)"
    v1 = int(re.findall(pattern, version1)[0])
    v2 = int(re.findall(pattern, version2)[0])
    return v1 - v2


def filemd5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(int(1e7)), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def list_profiles(filecfg="~/mlopskit/cfg.json"):
    if str(filecfg).startswith("~"):
        filecfg = os.path.expanduser(filecfg)
    # print(open(filecfg).read())
    return json.loads(open(filecfg).read())


def human_readable_file_size(size):
    # Taken from Dipen Panchasara
    # https://stackoverflow.com/questions/1094841/reusable-library-to-get-human-readable-version-of-file-size
    _suffixes = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    order = int(log2(size) / 10) if size else 0
    return "{:.4g} {}".format(size / (1 << (order * 10)), _suffixes[order])


filecfg = "~/mlopskit/cfg.json"
envs = list(list_profiles().keys())


def get_models(envs=envs, filters=["dev", "prod", "preprod"]):
    model_dict = {}
    for env in envs:
        if env not in filters:
            continue
        model_dict[env] = {}
        configmgr = ConfigManager(filecfg=filecfg, profile=env)
        filerepo = configmgr.load()["filerepo"]

        dirpath = Path(filerepo)
        models = get_first_level_directories(dirpath)
        model_sub_info = {}

        def getattrib(fname, dir_path):
            on_not_exist = "warn"
            p = Path(dir_path) / fname
            if not p.exists():
                if on_not_exist == "warn":
                    warnings.warn("Local file {} does not exist".format(fname))
                    return None
            dtmod = datetime.fromtimestamp(p.stat().st_mtime)
            # crc = filemd5(p)
            crc = "crc_dir"
            return {
                "filename": fname,
                "modified_at": dtmod,
                "size": human_readable_file_size(p.stat().st_size),
                "crc": crc,
            }

        for model in models:
            model_sub_info[model] = {}
            # 统计子目录数量
            model_dir = dirpath / model
            subdirectories = [
                name
                for name in os.listdir(model_dir)
                if os.path.isdir(os.path.join(model_dir, name))
            ]

            filesall = [getattrib(fname, model_dir) for fname in os.listdir(model_dir)]

            subdirectory_count = len(subdirectories)
            model_sub_info[model]["model_version_cnt"] = subdirectory_count
            model_sub_info[model]["model_version_list"] = subdirectories
            model_sub_info[model]["model_version_list_details"] = filesall
            recom_ports_dev = []
            reward_ports_dev = []
            recom_ports_prod = []
            reward_ports_prod = []
            if len(subdirectories) > 0:
                config_rel_dev_path = "config/server_dev.yml"
                config_rel_prod_path = "config/server_prod.yml"
                config_path_dev = model_dir / subdirectories[0] / config_rel_dev_path
                config_path_prod = model_dir / subdirectories[0] / config_rel_prod_path
                if config_path_dev.exists():
                    recom_ports_dev = (
                        YAMLDataSet(str(config_path_dev))
                        .load()
                        .get("recomserver")["ports"]
                    )
                    reward_ports_dev = (
                        YAMLDataSet(str(config_path_dev))
                        .load()
                        .get("rewardserver")["ports"]
                    )
                if config_path_prod.exists():
                    recom_ports_prod = (
                        YAMLDataSet(str(config_path_prod))
                        .load()
                        .get("recomserver")["ports"]
                    )
                    reward_ports_prod = (
                        YAMLDataSet(str(config_path_prod))
                        .load()
                        .get("rewardserver")["ports"]
                    )

            model_sub_info[model]["server_info"] = {
                "recom_ports_dev": recom_ports_dev,
                "reward_ports_dev": reward_ports_dev,
                "recom_ports_prod": recom_ports_prod,
                "reward_ports_prod": reward_ports_prod,
            }

        model_dict[env]["models"] = models

        model_dict[env]["sub_model_info"] = model_sub_info
        model_dict[env]["base_dir"] = dirpath
    return model_dict


# get_models()


def get_model_version(name, version, env):
    configmgr = ConfigManager(filecfg=filecfg, profile=env)
    filerepo = configmgr.load()["filerepo"]
    dirpath = Path(filerepo)

    model_version_dir = dirpath / name / version
    _dir = str(model_version_dir) + os.sep

    files = [
        str(PurePosixPath(p.relative_to(_dir)))
        for p in model_version_dir.glob("**/*")
        if not p.is_dir()
    ]

    def getattrib(fname, dir_path):
        on_not_exist = "warn"
        p = Path(dir_path) / fname
        if not p.exists():
            if on_not_exist == "warn":
                warnings.warn("Local file {} does not exist".format(fname))
                return None
        dtmod = datetime.fromtimestamp(p.stat().st_mtime)
        # crc = filemd5(p)
        crc = "crc_dir"
        return {
            "file_path": str(p),
            "filename": fname,
            "modified_at": dtmod,
            "size": human_readable_file_size(p.stat().st_size),
            "crc": crc,
        }

    filesall = [getattrib(fname, model_version_dir) for fname in files]
    filesall = [o for o in filesall if o is not None]
    return filesall, files


# get_model_version(name,version,env)
