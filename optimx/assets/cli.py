import glob
import os
import re
import sys
import tempfile

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn
from rich.table import Table
from rich.tree import Tree

from optimx.assets.drivers.abc import StorageDriverSettings

try:
    from optimx.assets.drivers.gcs import GCSStorageDriver

    has_gcs = True
# except ModuleNotFoundError:
except:
    has_gcs = False
try:
    from optimx.assets.drivers.s3 import S3StorageDriver

    has_s3 = True
except ModuleNotFoundError:
    has_s3 = False

from optimx.assets.drivers.rest import RestStorageDriver
from optimx.assets.drivers.rest_client import RestClient

from optimx.assets.errors import ObjectDoesNotExistError
from optimx.assets.manager import AssetsManager
from optimx.assets.remote import DriverNotInstalledError, StorageProvider
from optimx.assets.settings import AssetSpec
from optimx.utils.file_utils import data_dir
import optimx.ext.shellkit as sh
from optimx.api import pull_assets
from optimx.config import REMOTE_MODEL_SERVER, MODEL_SERVER_HOST


@click.group("assets")
def assets_cli():
    """
    Assets management commands
    """
    pass


storage_url_re = (
    r"(?P<storage_prefix>[\w]*)://(?P<bucket_name>[\w\-]+)/(?P<object_name>.+)"
)


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


def _check_asset_file_number(asset_path):
    n_files = len(
        [f for f in glob.iglob(os.path.join(asset_path, "**/*"), recursive=True)]
    )
    if n_files > 50:
        click.secho(
            "It looks like you are attempting to push an asset with more than 50 files"
            f" in it ({n_files}).\n"
            "This can lead to poor performance when retrieving the asset, and should"
            " be avoided.\n"
            "You should consider archiving and compressing it.",
            fg="red",
        )
        if click.confirm("Proceed anyways ?", abort=True):
            pass


@assets_cli.command("new")
@click.argument("asset_path")
@click.argument("asset_spec")
@click.option("--storage-prefix", envvar="OPTIMX_STORAGE_PREFIX")
@click.option("--dry-run", is_flag=True)
def new(asset_path, asset_spec, storage_prefix, dry_run):
    """
    Create a new asset.

    Create a new asset ASSET_SPEC with ASSET_PATH file.

    Will fail if asset exists (in this case use `update`).

    ASSET_PATH is the path to the file. The file can be local or on GCS
    (starting with gs://)

    ASSET_SPEC is and asset specification of the form
    [asset_name] (Major/minor version information is ignored)

    NB: [asset_name] can contain `/` too.
    """
    new_(asset_path, asset_spec, storage_prefix, dry_run)


def new_(asset_path, asset_spec, storage_prefix, dry_run):
    _check_asset_file_number(asset_path)
    destination_provider = StorageProvider(prefix=storage_prefix)

    print("Destination assets provider:")
    print(f" - storage driver = `{destination_provider.driver}`")
    print(f" - driver bucket = `{destination_provider.driver.bucket}`")
    print(f" - prefix = `{storage_prefix}`")

    print(f"Current asset: `{asset_spec}`")
    spec = AssetSpec.from_string(asset_spec)
    version = spec.versioning.get_initial_version()
    print(f" - name = `{spec.name}`")

    print(f"Push a new asset `{spec.name}` " f"with version `{version}`?")

    response = click.prompt("[y/N]")
    if response == "y":
        with tempfile.TemporaryDirectory() as tmp_dir:
            if not os.path.exists(asset_path):
                parsed_path = parse_remote_url(asset_path)
                driver_settings = StorageDriverSettings(
                    bucket=parsed_path["bucket_name"]
                )
                if parsed_path["storage_prefix"] == "gs":
                    if not has_gcs:
                        raise DriverNotInstalledError(
                            "GCS driver not installed, install optimx[assets-gcs]"
                        )
                    driver = GCSStorageDriver(driver_settings)
                elif parsed_path["storage_prefix"] == "s3":
                    if not has_s3:
                        raise DriverNotInstalledError(
                            "S3 driver not installed, install optimx[assets-s3]"
                        )
                    driver = S3StorageDriver(driver_settings)
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
        return version
    print("Aborting.")


@assets_cli.command("update")
@click.argument("asset_path")
@click.argument("asset_spec")
@click.option(
    "--bump-major",
    is_flag=True,
    help="[minor-major] Push a new major version (1.0, 2.0, etc.)",
)
@click.option("--storage-prefix", envvar="OPTIMX_STORAGE_PREFIX")
@click.option("--dry-run", is_flag=True)
def update(asset_path, asset_spec, storage_prefix, bump_major, dry_run):
    """
    Update an existing asset using versioning system
    set in OPTIMX_ASSETS_VERSIONING_SYSTEM (major/minor by default)

    Update an existing asset ASSET_SPEC with ASSET_PATH file.


    By default will upload a new minor version.

    ASSET_PATH is the path to the file. The file can be local remote (AWS or GCS)
    (starting with gs:// or s3://)

    ASSET_SPEC is and asset specification of the form
    [asset_name]:[version]

    Specific documentation depends on the choosen model
    """
    try:
        update_(asset_path, asset_spec, storage_prefix, bump_major, dry_run)
    except ObjectDoesNotExistError:
        print("Remote asset not found. Create it first using `new`")
        sys.exit(1)


def update_(asset_path, asset_spec, storage_prefix, bump_major, dry_run):
    _check_asset_file_number(asset_path)
    destination_provider = StorageProvider(prefix=storage_prefix)

    print("Destination assets provider:")
    print(f" - storage driver = `{destination_provider.driver}`")
    print(f" - driver bucket = `{destination_provider.driver.bucket}`")
    print(f" - prefix = `{storage_prefix}`")

    print(f"Current asset: `{asset_spec}`")
    versioning_system = os.environ.get("OPTIMX_ASSETS_VERSIONING_SYSTEM", "major_minor")
    spec = AssetSpec.from_string(asset_spec, versioning=versioning_system)
    print(f" - versioning system = `{versioning_system}` ")
    print(f" - name = `{spec.name}`")
    print(f" - version = `{spec.version}`")

    version_list = destination_provider.get_versions_info(spec.name)

    update_params = spec.versioning.get_update_cli_params(
        version=spec.version,
        version_list=version_list,
        bump_major=bump_major,
    )

    print(update_params["display"])
    new_version = spec.versioning.increment_version(
        spec.sort_versions(version_list),
        update_params["params"],
    )
    print(f"Push a new asset version `{new_version}` " f"for `{spec.name}`?")

    response = click.prompt("[y/N]")
    if response == "y":
        with tempfile.TemporaryDirectory() as tmp_dir:
            if not os.path.exists(asset_path):
                parsed_path = parse_remote_url(asset_path)
                driver_settings = StorageDriverSettings(
                    bucket=parsed_path["bucket_name"]
                )
                if parsed_path["storage_prefix"] == "gs":
                    if not has_gcs:
                        raise DriverNotInstalledError(
                            "GCS driver not installed, install optimx[assets-gcs]"
                        )
                    driver = GCSStorageDriver(driver_settings)
                elif parsed_path["storage_prefix"] == "s3":
                    if not has_s3:
                        raise DriverNotInstalledError(
                            "S3 driver not installed, install optimx[assets-s3]"
                        )
                    driver = S3StorageDriver(driver_settings)
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
        return new_version
    print("Aborting.")


@assets_cli.command("list")
@click.option("--storage-prefix", envvar="OPTIMX_STORAGE_PREFIX")
def list(storage_prefix):
    """lists all available assets and their versions."""
    manager = StorageProvider(
        prefix=storage_prefix,
    )

    console = Console()
    tree = Tree("[bold]Assets store[/bold]")
    tree.add(f"[dim]storage provider[/dim] {manager.driver.__class__.__name__}")
    tree.add(f"[dim]prefix[/dim] {storage_prefix}")
    console.print(tree)

    table = Table(show_header=True, header_style="bold")
    table.add_column("Asset name")
    table.add_column("Versions", style="dim")

    n = 0
    n_versions = 0
    with Progress(
        SpinnerColumn(), "[progress.description]{task.description}", transient=True
    ) as progress:
        progress.add_task("Listing remote assets", start=False)
        for asset_name, versions_list in manager.iterate_assets():
            table.add_row(asset_name, " ".join(versions_list))
            n += 1
            n_versions += len(versions_list)

    console.print(table)
    console.print(f"Found {n} assets ({n_versions} different versions)")


@assets_cli.command("fetch")
@click.argument("asset")
@click.option("--download", is_flag=True)
def fetch_asset(asset, download):
    """Fetch an asset and download if necessary"""
    manager = AssetsManager()

    info = manager.fetch_asset(asset, return_info=True, force_download=download)

    console = Console()
    console.print(info)


@assets_cli.command("push", no_args_is_help=True)
@click.option("--name", help="model name", required=True)
@click.option(
    "--profile", help="env name", required=True, default="dev", show_default=True
)
@click.option("--filename", help="file/dir name to push", required=True)
@click.option(
    "--update",
    help="Update an existing asset using versioning system",
    is_flag=True,
    default=False,
    required=True,
)
@click.option(
    "--bump",
    help="[minor-major] Push a new major version (1.0, 2.0, etc.)",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.option(
    "--newversion",
    help="[minor-major+1?] Push a new major version (1.0, 2.0, etc.)",
    is_flag=True,
    default=False,
    show_default=True,
)
@click.option(
    "--toremote", help="to_remote", is_flag=True, default=False, show_default=True
)
@click.option(
    "--preview", help="Preview", is_flag=True, default=True, show_default=True
)
def push(name, filename, update, bump, toremote, profile, preview, newversion):
    """
    Push model/version and code from local repo to remote repo.
    Create/Update a new asset.

    Create a new asset ASSET_SPEC with ASSET_PATH file.

    Will fail if asset exists (in this case use `update`).

    ASSET_PATH is the path to the file. The file can be local or on GCS
    (starting with gs://)

    ASSET_SPEC is and asset specification of the form
    [asset_name] (Major/minor version information is ignored)

    when Update an existing asset using versioning system
    set in OPTIMX_ASSETS_VERSIONING_SYSTEM (major/minor by default)

    NB: [asset_name] can contain `/` too.
    """
    if not update:
        new_push(
            asset_path=filename,
            asset_spec=f"{name}",
            storage_prefix=profile,
            dry_run=preview,
        )
    else:
        update_push(
            asset_path=filename,
            asset_spec=f"{name}",
            storage_prefix=profile,
            bump_major=bump,
            dry_run=preview,
            newversion=newversion,
        )


def new_push(asset_path, asset_spec, storage_prefix, dry_run):
    _check_asset_file_number(asset_path)
    bucket_name = data_dir()
    sh.mkdir(bucket_name)
    provider = os.environ.get("OPTIMX_STORAGE_PROVIDER", "local")
    destination_provider = StorageProvider(
        provider=provider, prefix=storage_prefix, bucket=bucket_name
    )

    print("Destination assets provider:")
    print(f" - storage driver = `{destination_provider.driver}`")
    print(f" - driver bucket = `{destination_provider.driver.bucket}`")
    print(f" - prefix = `{storage_prefix}`")

    print(f"Current asset: `{asset_spec}`")
    spec = AssetSpec.from_string(asset_spec)
    version = spec.versioning.get_initial_version()
    print(f" - name = `{spec.name}`")

    print(f"Push a new asset `{spec.name}` " f"with version `{version}`?")

    response = click.prompt("[y/N]")
    if response == "y":
        with tempfile.TemporaryDirectory() as tmp_dir:
            if not os.path.exists(asset_path):
                parsed_path = parse_remote_url(asset_path)
                driver_settings = StorageDriverSettings(
                    bucket=parsed_path["bucket_name"]
                )
                if parsed_path["storage_prefix"] == "gs":
                    if not has_gcs:
                        raise DriverNotInstalledError(
                            "GCS driver not installed, install optimx[assets-gcs]"
                        )
                    driver = GCSStorageDriver(driver_settings)
                elif parsed_path["storage_prefix"] == "s3":
                    if not has_s3:
                        raise DriverNotInstalledError(
                            "S3 driver not installed, install optimx[assets-s3]"
                        )
                    driver = S3StorageDriver(driver_settings)
                elif parsed_path["storage_prefix"] == "http":
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
        return version
    print("Aborting.")


def update_push(
    asset_path, asset_spec, storage_prefix, bump_major, dry_run, newversion
):
    _check_asset_file_number(asset_path)
    bucket_name = data_dir()
    sh.mkdir(bucket_name)
    provider = os.environ.get("OPTIMX_STORAGE_PROVIDER", "local")
    destination_provider = StorageProvider(
        provider=provider, prefix=storage_prefix, bucket=bucket_name
    )

    print("Destination assets provider:")
    print(f" - storage driver = `{destination_provider.driver}`")
    print(f" - driver bucket = `{destination_provider.driver.bucket}`")
    print(f" - prefix = `{storage_prefix}`")

    print(f"Current asset: `{asset_spec}`")
    versioning_system = os.environ.get("OPTIMX_ASSETS_VERSIONING_SYSTEM", "major_minor")
    spec = AssetSpec.from_string(asset_spec, versioning=versioning_system)
    print(f" - versioning system = `{versioning_system}` ")
    print(f" - name = `{spec.name}`")
    print(f" - version = `{spec.version}`")

    version_list = destination_provider.get_versions_info(spec.name)

    update_params = spec.versioning.get_update_cli_params(
        version=spec.version,
        version_list=version_list,
        bump_major=bump_major,
    )

    print(update_params["display"])

    if not newversion:
        new_version = version_list[0]
        print(f"Update a asset version `{new_version}` " f"for `{spec.name}`?")
    else:
        new_version = spec.versioning.increment_version(
            spec.sort_versions(version_list),
            update_params["params"],
        )
        print(f"Push a new asset version `{new_version}` " f"for `{spec.name}`?")

    response = click.prompt("[y/N]")
    if response == "y":
        with tempfile.TemporaryDirectory() as tmp_dir:
            if not os.path.exists(asset_path):
                parsed_path = parse_remote_url(asset_path)
                driver_settings = StorageDriverSettings(
                    bucket=parsed_path["bucket_name"]
                )
                if parsed_path["storage_prefix"] == "gs":
                    if not has_gcs:
                        raise DriverNotInstalledError(
                            "GCS driver not installed, install optimx[assets-gcs]"
                        )
                    driver = GCSStorageDriver(driver_settings)
                elif parsed_path["storage_prefix"] == "s3":
                    if not has_s3:
                        raise DriverNotInstalledError(
                            "S3 driver not installed, install optimx[assets-s3]"
                        )
                    driver = S3StorageDriver(driver_settings)

                elif parsed_path["storage_prefix"] == "http":
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
        return new_version
    print("Aborting.")


@assets_cli.command("clone", no_args_is_help=True)
@click.option("--name", help="model name", required=True)
@click.option(
    "--profile", help="env name", required=True, default="preprod", show_default=True
)
@click.option(
    "--version",
    help="model version to pull",
    required=True,
    default="0.0",
    show_default=True,
)
@click.option(
    "--localdir",
    help="local repo to save code",
    required=True,
    default=os.getcwd(),
    show_default=True,
)
@click.option(
    "--provider",
    help="driver, support local and rest",
    required=True,
    default="local",
    show_default=True,
)
@click.option(
    "--bucket",
    help="model repo base path",
    required=True,
    default=data_dir(),
    show_default=True,
)
@click.option(
    "--team-repo-path",
    help="remote diff team base model repo(code) for clone",
    is_flag=False,
    default="df",
    show_default=True,
)
def pull_code(name, profile, version, localdir, provider, bucket, team_repo_path):
    """
    Pull model/version and code from remote repo to local repo.
    """
    if provider == "local":
        pull_assets(
            name=name,
            env=profile,
            version=version,
            assets_dir=localdir,
            provider=provider,
            bucket=bucket,
            force_download=False,
        )
    else:
        if team_repo_path in ["cf", "df"]:
            host = REMOTE_MODEL_SERVER[team_repo_path]
            rest_client = RestClient(host=host)
        else:
            model_host = MODEL_SERVER_HOST["host"]
            model_port = MODEL_SERVER_HOST["port"]
            host_defualt = f"http://{model_host}:{model_port}"
            rest_client = RestClient()
            host = host_defualt

        print("Destination assets provider:")
        print(f" - storage driver = `REST API`")
        print(f" - remote model name = `{name}`")
        print(f" - remote model version = `{version}`")

        print(f"Current asset: `{localdir}`")

        if team_repo_path == "cf":
            clone_from = "CF models repo"
        elif team_repo_path == "df":
            clone_from = "DAFU models repo"

        print(f" - clone assets from = `{clone_from}` ")
        print(f" - remote host = `{host}`")
        response = click.prompt("[y/N]")
        if response == "y":
            rest_client.clone(
                name=name,
                version=version,
                env=profile,
                save_path=localdir,
                rm_zipfile=True,
            )


@assets_cli.command("deploy", no_args_is_help=True)
@click.option("--name", help="model name", required=True)
@click.option(
    "--version",
    help="model version to push",
    required=True,
    default="0.0",
    show_default=True,
)
@click.option(
    "--local-path",
    help="local base path",
    is_flag=False,
    default=os.getcwd(),
    show_default=True,
)
@click.option(
    "--filename", help="filename/dirname to upload", is_flag=False, show_default=True
)
@click.option(
    "--team-repo-path",
    help="remote diff team base model repo(code) for push",
    is_flag=False,
    default="df",
    show_default=True,
)
def deploy(name, version, local_path, filename, team_repo_path):
    host = None
    if team_repo_path in ["cf", "df", "df2"]:
        host = REMOTE_MODEL_SERVER[team_repo_path]
        rest_client = RestClient(host=host)
    else:
        model_host = MODEL_SERVER_HOST["host"]
        model_port = MODEL_SERVER_HOST["port"]
        host_defualt = f"http://{model_host}:{model_port}"
        rest_client = RestClient()
        host = host_defualt

    print("Destination assets provider:")
    print(f" - storage driver = `REST API`")
    print(f" - remote model name = `{name}`")
    print(f" - remote model version = `{version}`")
    asset_path = os.path.join(local_path, filename)
    print(f"Current asset: `{asset_path}`")

    if team_repo_path == "cf":
        push_dest = "Model will send to CF models repo"
    elif team_repo_path == "df":
        push_dest = "Model will send to DAFU models repo"
    elif team_repo_path == "df2":
        push_dest = "Model will send to DAFU models repo2"

    print(f" - deploy destination = `{push_dest}` ")
    print(f" - remote host = `{host}`")
    response = click.prompt("[y/N]")
    if response == "y":
        resp = rest_client.deploy(
            name=name,
            version=version,
            local_path=local_path,
            filename=filename,
            server_base_path=team_repo_path,
        )
        print(resp)
        return resp
    print("Aborting.")
