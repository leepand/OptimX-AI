from typing import (
    Optional,
    Tuple,
    Union,
)
import re
import os
import json
from dataclasses import dataclass, field
import importlib
import traceback

from structlog import get_logger
from optimx.envs import error
from optimx.utils.colorize import colorize
from optimx.ext.store.tracking import file_store
from optimx.utils.file_utils import data_dir
import optimx.ext.shellkit as sh

logger = get_logger(__name__)


ALLOWED_OPS_TYPES = ["cache", "db", "config", "meta"]
ENV_ID_RE = re.compile(
    r"^(?:(?P<namespace>[\w:-]+)\/)?(?:(?P<name>[\w:.-]+?))(?:-v(?P<version>\d+\.\d+))?$"
)


def parse_env_id(id: str) -> Tuple[Optional[str], str, Optional[int]]:
    """Parse environment ID string format.
    This format is true today, but it's *not* an official spec.
    [namespace/](env-name)-v(version)    env-name is group 1, version is group 2
    2016-10-31: We're experimentally expanding the environment ID format
    to include an optional namespace.
    Args:
        id: The environment id to parse
    Returns:
        A tuple of environment namespace, environment name and version number
    Raises:
        Error: If the environment id does not a valid environment regex
    """
    match = ENV_ID_RE.fullmatch(id)
    if not match:
        raise error.Error(
            f"Malformed environment ID: {id}."
            f"(Currently all IDs must be of the form [namespace/](env-name)-v(version). (namespace is optional))"
        )
    namespace, name, version = match.group("namespace", "name", "version")

    return namespace, name, version


def get_env_id(ns: Optional[str], name: str, version: Optional[int]) -> str:
    """Get the full env ID given a name and (optional) version and namespace. Inverse of :meth:`parse_env_id`.
    Args:
        ns: The environment namespace
        name: The environment name
        version: The environment version
    Returns:
        The environment id
    """

    full_name = name
    if version is not None:
        full_name += f"-v{version}"
    if ns is not None:
        full_name = ns + "/" + full_name
    return full_name


@dataclass
class EnvSpec:
    """A specification for creating environments with `optimx.make`.
    * id: The string used to create the environment with `optimx.make`
    * entry_point: The location of the environment to create from
    * reward_threshold: The reward threshold for completing the environment.
    * nondeterministic: If the observation of an environment cannot be repeated with the same initial state, random number generator state and actions.
    * max_episode_steps: The max number of steps that the environment can take before truncation
    * order_enforce: If to enforce the order of `reset` before `step` and `render` functions
    * autoreset: If to automatically reset the environment on episode end
    * disable_env_checker: If to disable the environment checker wrapper in `optimx.make`, by default False (runs the environment checker)
    * kwargs: Additional keyword arguments passed to the environments through `optimx.make`
    """

    id: str

    # Environment arguments
    kwargs: dict = field(default_factory=dict)

    # post-init attributes
    namespace: Optional[str] = field(init=False)
    name: str = field(init=False)
    version: Optional[int] = field(init=False)

    def __post_init__(self):
        # Initialize namespace, name, version
        self.namespace, self.name, self.version = parse_env_id(self.id)


def make(id=None, help: bool = False, **kwargs):
    if id is None:
        msg = (
            f'The correct naming convention is "$ops_type/$model_name-v$version".'
            f"Valid ops_type options are: {ALLOWED_OPS_TYPES}."
            f"If v$version is empty, further instructions will be provided. "
            f"Alternatively, inputting `client` will return the original client."
        )
        logger.warning(msg)
        return

    if isinstance(id, EnvSpec):
        spec_ = id
    else:
        module, id = (None, id) if ":" not in id else id.split(":")
        if module is not None:
            try:
                importlib.import_module(module)
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(
                    f"{e}. Environment registration via importing a module failed. "
                    f"Check whether '{module}' contains env registration and can be imported."
                )
        spec_ = id
        _kwargs = kwargs.copy()
        host = _kwargs.get("host")
        config = _kwargs.get("config")

        ns, name, version = parse_env_id(id)

        if not ns:
            msg = (
                f'The correct naming convention is "$ops_type/$model_name-v$version".'
                f"Valid ops_type options are: {ALLOWED_OPS_TYPES}."
                f"If v$version is empty, further instructions will be provided. "
                f"Alternatively, inputting `client` will return the original client."
            )
            logger.warning(colorize(msg, "yellow", True, False))
            return

        if version:
            version = str(version)
        logger.info(
            "Model Asset APIs of optimx",
            ops_type=ns,
            model_name=name,
            model_version=version,
        )
        if ns in ["db", "cache"]:
            if ns == "cache":
                try:
                    p = {
                        "db_type": "rlite/redis/sfdb/diskcache, default:rlite",
                        "return_type": "dblink/dbobj, default: dbobj",
                        "env": "dev/prod, default:dev",
                        "db_name": "default: rlite_model.cache",
                    }
                    logger.info(
                        "Usage of optimx-cache",
                        Params=colorize(p, "cyan", True, False),
                    )
                    if help:
                        return
                    base_path = data_dir()
                    env = _kwargs.get("env", "dev")
                    db_name = _kwargs.get("db_name", "rlite_model.cache")
                    db_type = _kwargs.get("db_type", "rlite")
                    return_type = _kwargs.get("return_type", "dbobj")
                    db_file = os.path.join(base_path, env, name, version, "db", db_name)
                    meta_file = os.path.join(base_path, env, name, f"{version}.meta")
                    if os.path.exists(meta_file):
                        with open(meta_file) as f:
                            meta_json = json.load(f)
                        meta_json["contents"].append(f"db/{db_name}")
                    else:
                        meta_json = {}
                        meta_json["contents"] = []
                        meta_json["contents"].append(f"db/{db_name}")

                    contents_db = list(set(meta_json["contents"]))
                    meta_json["contents"] = contents_db
                    with open(meta_file, "w", encoding="utf-8") as fmeta:
                        json.dump(meta_json, fmeta)

                    (db_path, filename) = os.path.split(db_file)
                    sh.mkdir(db_path)
                    db_class = file_store.FileStore(
                        db_file=db_file, db_type=db_type, return_type=return_type
                    )
                    return db_class.build_cache_store()
                except:
                    logger.error(str(traceback.format_exc()))
