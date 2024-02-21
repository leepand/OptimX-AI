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
from optimx.config import LOCAL_DEPLOY_PATH
from optimx.utils.sys_utils import check_port
import optimx.ext.shellkit as sh
import random

from optimx.utils.file_utils import Page

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


def get_subdirectories(path):
    subdirectories = []
    for entry in os.scandir(path):
        if entry.is_dir() and not entry.name.startswith((".", "__")):
            subdirectories.append(entry.name)
    return subdirectories


def get_subdirectories_sorted_by_time(directory, prefix_to_exclude=""):
    subdirectories = [
        os.path.join(directory, name)
        for name in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, name))
    ]
    subdirectories_sorted = sorted(
        subdirectories, key=lambda d: os.path.getmtime(d), reverse=True
    )
    subdirectory_names = [
        os.path.basename(subdir)
        for subdir in subdirectories_sorted
        if not os.path.basename(subdir).startswith(prefix_to_exclude)
    ]
    return subdirectory_names


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
    crc = "filemd5(p)"
    return {
        "file_path": str(p),
        "filename": fname,
        "modified_at": dtmod,
        "size": human_readable_file_size(get_size(str(p))),
        "crc": crc,
    }


def get_file_info(
    env,
    name,
    version,
    filenames,
    working_dir=DEFAULT_WORKING_DIR,
    deploy_dir=LOCAL_DEPLOY_PATH,
):
    if env == "preprod":
        env_base_path = os.path.join(deploy_dir, name, version)
    else:
        env_base_path = os.path.join(working_dir, env, name, version)
    filesall = [getattrib(fname, env_base_path) for fname in filenames]
    filesall_real = [finfo for finfo in filesall if finfo]
    return filesall_real


def get_models_meta(
    env,
    working_dir=DEFAULT_WORKING_DIR,
    provider="local",
    deploy_dir=LOCAL_DEPLOY_PATH,
    model_names=[],
    page_info=None,
    search_model_name=None,
):
    if env == "preprod":
        model_infos = Dict()
        if len(model_names) < 1:
            if page_info is not None:
                # page_info = {"previous": previous, "next": next, "page_index": page_index}
                ori_model_names = get_subdirectories_sorted_by_time(
                    directory=deploy_dir, prefix_to_exclude=(".", "__")
                )
                model_infos["model_cnt"] = len(ori_model_names)
                if search_model_name is not None:
                    ori_model_names = [
                        item for item in ori_model_names if search_model_name in item
                    ]
                length_of_names = len(ori_model_names)
                previous = page_info.get("previous")
                next = page_info.get("next")
                page_index = page_info.get("page_index")
                pg = Page(
                    item_count=length_of_names, page_index=page_index, page_size=4
                )
                if previous == "1":
                    if pg.has_previous:
                        pg.page_index -= 1
                if next == "1":
                    if pg.has_next:
                        pg.page_index += 1
                pg2 = Page(
                    item_count=length_of_names, page_index=pg.page_index, page_size=7
                )
                model_names = ori_model_names[pg2.offset : pg2.offset + pg2.limit]
                page_count = pg2.page_count
                page_index = pg2.page_index
                has_previous = pg2.has_previous
                has_next = pg2.has_next
                page_list = [i + 1 for i in range(page_count)]
                model_infos["page_info"] = {
                    "page_count": page_count,
                    "pages": page_list,
                    "current_page": page_index,
                    "has_previous": has_previous,
                    "has_next": has_next,
                    # "ori_model_names":ori_model_names,
                    # "pg2.offset":pg2.offset,
                    # "pg2.limit":pg2.limit
                }
            else:
                model_names = get_subdirectories(path=deploy_dir)
                model_infos["model_cnt"] = len(model_names)
        for model_name in model_names:
            model_path = os.path.join(deploy_dir, model_name)
            model_infos[model_name]["dtmod"] = datetime.fromtimestamp(
                Path(model_path).stat().st_mtime
            )
            versions_list = get_subdirectories(path=model_path)
            model_infos[model_name]["version_list"] = sorted(
                list(set(versions_list)), key=str, reverse=True
            )
            for version in versions_list:
                model_version_info = Dict()
                model_infos[model_name][version] = model_version_info
                version_files_path = os.path.join(model_path, version)
                model_infos[model_name][version][
                    "version_files_path"
                ] = version_files_path

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

                model_infos[model_name][version]["size"] = "0 KB"
                model_infos[model_name][version]["push_date"] = datetime.now().strftime(
                    "%Y-%m-%d"
                )
                if os.path.exists(version_files_path):
                    model_infos[model_name][version]["size"] = human_readable_file_size(
                        get_size(version_files_path)
                    )
                    model_infos[model_name][version][
                        "push_date"
                    ] = datetime.fromtimestamp(Path(version_files_path).stat().st_mtime)

        return model_infos
    storage_provider = StorageProvider(
        provider=provider,
        bucket=f"{working_dir}",
        prefix=env,
    )
    model_infos = Dict()
    try:
        env_base_path = os.path.join(working_dir, env)
        if len(model_names) < 1:
            # model_list_for_iter = storage_provider.iterate_assets()
            if page_info is not None:
                # page_info = {"previous": previous, "next": next, "page_index": page_index}
                ori_model_names = get_subdirectories_sorted_by_time(
                    directory=env_base_path, prefix_to_exclude=(".", "__")
                )
                model_infos["model_cnt"] = len(ori_model_names)
                if search_model_name is not None:
                    ori_model_names = [
                        item for item in ori_model_names if search_model_name in item
                    ]
                length_of_names = len(ori_model_names)
                previous = page_info.get("previous")
                next = page_info.get("next")
                page_index = page_info.get("page_index")
                pg = Page(
                    item_count=length_of_names, page_index=page_index, page_size=4
                )
                if previous == "1":
                    if pg.has_previous:
                        pg.page_index -= 1
                if next == "1":
                    if pg.has_next:
                        pg.page_index += 1
                pg2 = Page(
                    item_count=length_of_names, page_index=pg.page_index, page_size=7
                )
                model_names = ori_model_names[pg2.offset : pg2.offset + pg2.limit]
                page_count = pg2.page_count
                page_index = pg2.page_index
                has_previous = pg2.has_previous
                has_next = pg2.has_next
                page_list = [i + 1 for i in range(page_count)]
                model_infos["page_info"] = {
                    "page_count": page_count,
                    "current_page": page_index,
                    "has_previous": has_previous,
                    "has_next": has_next,
                    "pages": page_list
                    # "ori_model_names":ori_model_names,
                    # "model_names":model_names,
                    # "pg2.offset":pg2.offset,
                    # "pg2.limit":pg2.limit
                }
                model_list_for_iter = []
                for name in model_names:
                    versions = list(set(storage_provider.get_versions_info(name)))
                    model_list_for_iter.append((name, versions))
            else:
                model_list_for_iter = storage_provider.iterate_assets()
                # generator_obj = model_list_for_iter
                # list_obj = list(generator_obj)
                model_infos["model_cnt"] = 0
        else:
            model_list_for_iter = []
            for name in model_names:
                versions = list(set(storage_provider.get_versions_info(name)))
                model_list_for_iter.append((name, versions))

        for model_asset_name, versions_list in model_list_for_iter:
            if len(model_names) < 1:
                model_infos["model_cnt"] += 1
            # print(asset_name, versions_list,storage_provider.get_versions_info(asset_name))
            model_infos[model_asset_name]["version_list"] = sorted(
                list(set(versions_list)), key=str, reverse=True
            )
            max_version = "0.0"
            if len(versions_list) > 0:
                max_version = max(
                    versions_list, key=lambda x: float(re.findall(r"(\d+.\d+)", x)[0])
                )

            model_path = os.path.join(env_base_path, model_asset_name)
            model_infos[model_asset_name]["dtmod"] = datetime.fromtimestamp(
                Path(model_path).stat().st_mtime
            )
            model_infos[model_asset_name]["model_size"] = "0 KB"
            model_infos[model_asset_name]["model_size"] = human_readable_file_size(
                get_size(model_path)
            )
            service_ops_file = os.path.join(model_path, ".SUCCESS")
            if os.path.exists(service_ops_file):
                model_infos[model_asset_name]["server_version"] = sh.read(
                    service_ops_file
                )
            else:
                model_infos[model_asset_name]["server_version"] = "-"

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
                                recom_port = random.choice(recom_ports)
                                status = check_port(port=recom_port)
                                if status == 0:
                                    recom_ports_status = "running"
                                else:
                                    recom_ports_status = "failed"

                                reward_port = random.choice(reward_ports)
                                status = check_port(port=reward_port)
                                if status == 0:
                                    reward_ports_status = "running"
                                else:
                                    reward_ports_status = "failed"

                                model_infos[model_asset_name][
                                    "recom_ports_status"
                                ] = recom_ports_status
                                model_infos[model_asset_name][
                                    "reward_ports_status"
                                ] = reward_ports_status
                except:
                    print(traceback.format_exc())
                    continue
    except:
        print(traceback.format_exc())
        pass

    return model_infos
