__version__ = "0.0.1"
import warnings

from optimx.core.library import ModelLibrary, load_model  # NOQA
from optimx.core.model import Model  # NOQA
from optimx.api import pull_assets, Client
from optimx.envs import make, ServiceMgr
from optimx.assets.drivers.rest_client import RestClient

# Silence Tensorflow warnings
# https://github.com/tensorflow/tensorflow/issues/30427
warnings.simplefilter(action="ignore", category=FutureWarning)

# 导出初始化函数和log函数

from optimx.tracking.experiment import Experiment
from optimx.tracking.opts import options
from optimx.tracking.run import Run
from optimx.tracking.session import Session as create_session
from optimx.tracking.session import create_experiment
from optimx.tracking.storage.datastore import DataStore, DataStoreIO
from optimx.tracking.utils.bunch import Bunch
from optimx.tracking.utils.sequence import Sequence
from optimx.tracking.version import __version__
from .env import Config

__all__ = (
    "create_session",
    "create_experiment",
    "Experiment",
    "Run",
    "Sequence",
    "Bunch",
    "DataStore",
    "DataStoreIO",
    "options",
    "RestClient",
    "ServiceMgr",
    "make",
    "pull_assets",
    "Client",
    "Model",
    "ModelLibrary",
    "load_model",
    "Config",
    "__version__",
)

__version__ = "0.0.1"
