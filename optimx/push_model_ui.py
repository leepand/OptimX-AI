import os
import tempfile
import re
from datetime import datetime
from datetime import timezone
from datetime import timedelta

from optimx.assets.drivers.rest import RestStorageDriver
from optimx.assets.drivers.abc import StorageDriverSettings
from optimx.assets.errors import ObjectDoesNotExistError

from optimx.assets.remote import DriverNotInstalledError, StorageProvider
from optimx.assets.settings import AssetSpec
from optimx.utils.file_utils import data_dir

import optimx.ext.shellkit as sh


SHA_TZ = timezone(
    timedelta(hours=8),
    name="Asia/Shanghai",
)


storage_url_re = (
    r"(?P<storage_prefix>[\w]*)://(?P<bucket_name>[\w\-]+)/(?P<object_name>.+)"
)


def _utcnow() -> str:
    """string iso format in UTC"""
    return datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")


def get_bj_day_time():
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
    beijing_now = utc_now.astimezone(SHA_TZ)
    _bj = beijing_now.strftime("%Y-%m-%d %H:%M:%S")  # 结果显示：'2017-10-07'

    return _bj


def parse_remote_url(path):
    match = re.match(storage_url_re, path)
    if not match:
        raise ValueError(f"Could not parse path `{path}`")
    return match.groupdict()


def _download_object_or_prefix(driver, object_name, destination_dir):
    asset_path = os.path.join(destination_dir, "myasset")
    try:
        driver.download_object(object_name=object_name, destination_path=asset_path)
    except ObjectDoesNotExistError:
        # maybe prefix containing objects
        paths = [path for path in driver.iterate_objects(prefix=object_name)]
        if not paths:
            raise

        os.mkdir(asset_path)
        for path in paths:
            sub_object_name = path.split("/")[-1]
            driver.download_object(
                object_name=object_name + "/" + sub_object_name,
                destination_path=os.path.join(asset_path, sub_object_name),
            )
    return asset_path


def new_push(name, filename, profile, log_file, dry_run=False):
    bucket_name = data_dir()
    sh.mkdir(bucket_name)
    asset_spec = name
    provider = os.environ.get("OPTIMX_STORAGE_PROVIDER", "local")
    destination_provider = StorageProvider(
        provider=provider, prefix=profile, bucket=bucket_name
    )
    push_script = (
        f"optimx assets push --name {name} --profile\n"
        f" {profile} --filename {filename} --preview"
    )
    sh.write(log_file, "Model Push(publish) Ops Script:\n")
    sh.write(log_file, f" - publish ops script = `{push_script}`\n", "a")
    sh.write(log_file, "Destination assets provider:\n", "a")
    sh.write(log_file, f" - storage driver = `{destination_provider.driver}`\n", "a")
    sh.write(
        log_file, f" - driver bucket = `{destination_provider.driver.bucket}`\n", "a"
    )
    sh.write(log_file, f" - prefix(Environment) = `{profile}`\n", "a")
    sh.write(log_file, f"Current asset: `{asset_spec}`\n", "a")
    sh.write(log_file, f"Current asset path: `{filename}`\n", "a")

    spec = AssetSpec.from_string(asset_spec)
    version = spec.versioning.get_initial_version()

    sh.write(log_file, f" - name = `{spec.name}`\n", "a")
    sh.write(
        log_file,
        f"Push a new asset `{spec.name}` " f"with version `{version}`?\n\n",
        "a",
    )
    asset_path = filename
    with tempfile.TemporaryDirectory() as tmp_dir:
        if not os.path.exists(asset_path):
            parsed_path = parse_remote_url(asset_path)
            driver_settings = StorageDriverSettings(bucket=parsed_path["bucket_name"])
            if parsed_path["storage_prefix"] == "http":
                driver = RestStorageDriver(driver_settings)
            else:
                raise ValueError(
                    f"Unmanaged storage prefix `{parsed_path['storage_prefix']}`"
                )
            asset_path = _download_object_or_prefix(
                driver,
                object_name=parsed_path["object_name"],
                destination_dir=tmp_dir,
            )
        destination_provider.new(asset_path, spec.name, version, dry_run)

    sh.write(log_file, f"Model {name} is pushed to remote {profile} repo! \n", "a")
    sh.write(log_file, f"Last Published Time(Beijing) `{get_bj_day_time()}`\n", "a")
    return version


def update_push(
    name, filename, profile, bump_major, newversion, log_file, dry_run=False
):
    bucket_name = data_dir()
    sh.mkdir(bucket_name)
    asset_spec = name
    provider = os.environ.get("OPTIMX_STORAGE_PROVIDER", "local")
    destination_provider = StorageProvider(
        provider=provider, prefix=profile, bucket=bucket_name
    )
    push_script = (
        f"optimx assets push --name {name}\n"
        f"--profile {profile} --filename {filename}\n"
        f" --preview --update"
    )
    if newversion:
        push_script += " --newversion"
        if bump_major:
            push_script += " --bump"

    sh.write(log_file, "Model Push(publish) Ops Script:\n")
    sh.write(log_file, f" - publish ops script(update) = `{push_script}`\n", "a")

    sh.write(log_file, "Destination assets provider:\n", "a")
    sh.write(log_file, f" - storage driver = `{destination_provider.driver}`\n", "a")
    sh.write(
        log_file, f" - driver bucket = `{destination_provider.driver.bucket}`\n", "a"
    )
    sh.write(log_file, f" - prefix = `{profile}`\n", "a")

    sh.write(log_file, f"Current asset: `{asset_spec}`\n", "a")
    versioning_system = os.environ.get("OPTIMX_ASSETS_VERSIONING_SYSTEM", "major_minor")
    spec = AssetSpec.from_string(asset_spec, versioning=versioning_system)
    sh.write(log_file, f" - versioning system = `{versioning_system}` \n", "a")
    sh.write(log_file, f" - name = `{spec.name}`\n", "a")
    sh.write(log_file, f" - version = `{spec.version}`\n", "a")

    version_list = destination_provider.get_versions_info(spec.name)

    update_params = spec.versioning.get_update_cli_params(
        version=spec.version,
        version_list=version_list,
        bump_major=bump_major,
    )

    sh.write(log_file, update_params["display"] + "\n", "a")

    if not newversion:
        new_version = version_list[0]
        sh.write(
            log_file,
            f"Update a asset version `{new_version}` " f"for `{spec.name}`?\n",
            "a",
        )
    else:
        new_version = spec.versioning.increment_version(
            spec.sort_versions(version_list),
            update_params["params"],
        )
        sh.write(
            log_file,
            f"Push a new asset version `{new_version}` " f"for `{spec.name}`?\n",
            "a",
        )
    asset_path = filename
    with tempfile.TemporaryDirectory() as tmp_dir:
        if not os.path.exists(asset_path):
            parsed_path = parse_remote_url(asset_path)
            driver_settings = StorageDriverSettings(bucket=parsed_path["bucket_name"])
            if parsed_path["storage_prefix"] == "http":
                driver = RestStorageDriver(driver_settings)
            else:
                raise ValueError(
                    f"Unmanaged storage prefix `{parsed_path['storage_prefix']}`"
                )
            asset_path = _download_object_or_prefix(
                driver,
                object_name=parsed_path["object_name"],
                destination_dir=tmp_dir,
            )

        destination_provider.update(
            asset_path,
            name=spec.name,
            version=new_version,
            dry_run=dry_run,
        )
    sh.write(log_file, f"Model {name} is pushed to remote {profile} repo! \n", "a")
    sh.write(
        log_file, f"Last Published-update Time(Beijing) `{get_bj_day_time()}`\n", "a"
    )
    return new_version
