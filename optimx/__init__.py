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
