"""

Some simple logging functionality, inspired by rllab's logging.

Logs to a tab-separated-values file (path/to/output_directory/progress.txt)

"""
import json
import joblib
import shutil
import numpy as np
import os.path as osp, time, atexit, os
import warnings
from optimx.utils.serialization_utils import convert_json
from optimx.config import def_logs_fnames, base_logs_path

import os
import time
import logging
from logging.handlers import TimedRotatingFileHandler


LOG_BASE_PATH = "/root/log"
LOG_PREDICT_PATH = "/root/log/predict_log"


color2num = dict(
    gray=30,
    red=31,
    green=32,
    yellow=33,
    blue=34,
    magenta=35,
    cyan=36,
    white=37,
    crimson=38,
)


def colorize(string, color, bold=False, highlight=False):
    """
    Colorize a string.

    This function was originally written by John Schulman.
    """
    attr = []
    num = color2num[color]
    if highlight:
        num += 10
    attr.append(str(num))
    if bold:
        attr.append("1")
    return "\x1b[%sm%s\x1b[0m" % (";".join(attr), string)


def init():
    logging.basicConfig(level=logging.DEBUG)
    all_log_name = def_logs_fnames

    for log_name in all_log_name:
        formatter_logger = logging.Formatter(
            "%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        handler_logger = TimedRotatingFileHandler(
            "%s/%s" % (base_logs_path, log_name), when="midnight", backupCount=7
        )
        handler_logger.setFormatter(formatter_logger)
        logger_logger = logging.getLogger(log_name)
        logger_logger.addHandler(handler_logger)

    log_content = [["status", "finish_logger_init"]]
    log_server(log_content)

    # import traceback
    # try:
    #     a = 1/0
    # except:
    #     err = traceback.format_exc()
    #     log_content = [
    #         ['error', err]
    #     ]
    #     log_promotion_predict(log_content)


def do_format(msg):
    ret = ""
    msg.append(["_ts", int(time.time())])
    for i in msg:
        ret += "%s=%s," % (i[0], str(i[1]))
    return ret[:-1]


def csv_format(msg):
    msg.insert(0, int(time.time()))
    msg = [str(i) for i in msg]
    return ",".join(msg)


def log_recom_error(msg):
    login_logger = logging.getLogger("recom_errors.log")
    login_logger.info(do_format(msg))


def log_reward_error(msg):
    login_logger = logging.getLogger("reward_errors.log")
    login_logger.info(do_format(msg))


def log_recom_debug(msg):
    login_logger = logging.getLogger("recom_debugs.log")
    login_logger.info(do_format(msg))


def log_reward_debug(msg):
    login_logger = logging.getLogger("reward_debugs.log")
    login_logger.info(do_format(msg))


def info(msg):
    net_logger = logging.getLogger("net")
    net_logger.info(msg)


def log_server(msg):
    login_logger = logging.getLogger("server")
    login_logger.info(do_format(msg))


init()


class Logger:
    """
    A general-purpose logger.

    Makes it easy to save diagnostics, hyperparameter configurations, the
    state of a training run, and the trained model.
    """

    def __init__(
        self, output_dir=None, output_fname="progress.txt", exp_name=None, proc_id=1
    ):
        """
        Initialize a Logger.

        Args:
            output_dir (string): A directory for saving results to. If
                ``None``, defaults to a temp directory of the form
                ``/tmp/experiments/somerandomnumber``.

            output_fname (string): Name for the tab-separated-value file
                containing metrics logged throughout a training run.
                Defaults to ``progress.txt``.

            exp_name (string): Experiment name. If you run multiple training
                runs and give them all the same ``exp_name``, the plotter
                will know to group them. (Use case: if you run the same
                hyperparameter configuration with multiple random seeds, you
                should give them all the same ``exp_name``.)
        """
        if proc_id == 0:
            self.output_dir = output_dir or "/tmp/experiments/%i" % int(time.time())
            if osp.exists(self.output_dir):
                print(
                    "Warning: Log dir %s already exists! Storing info there anyway."
                    % self.output_dir
                )
            else:
                os.makedirs(self.output_dir)
            self.output_file = open(osp.join(self.output_dir, output_fname), "w")
            atexit.register(self.output_file.close)
            print(
                colorize(
                    "Logging data to %s" % self.output_file.name, "green", bold=True
                )
            )
        else:
            self.output_dir = None
            self.output_file = None
        self.first_row = True
        self.log_headers = []
        self.log_current_row = {}
        self.exp_name = exp_name

    def log(self, msg, color="green"):
        """Print a colorized message to stdout."""
        print(colorize(msg, color, bold=True))

    def log_tabular(self, key, val):
        """
        Log a value of some diagnostic.

        Call this only once for each diagnostic quantity, each iteration.
        After using ``log_tabular`` to store values for each diagnostic,
        make sure to call ``dump_tabular`` to write them out to file and
        stdout (otherwise they will not get saved anywhere).
        """
        if self.first_row:
            self.log_headers.append(key)
        else:
            assert key in self.log_headers, (
                "Trying to introduce a new key %s that you didn't include in the first iteration"
                % key
            )
        assert key not in self.log_current_row, (
            "You already set %s this iteration. Maybe you forgot to call dump_tabular()"
            % key
        )
        self.log_current_row[key] = val

    def save_config(self, config):
        """
        Log an experiment configuration.

        Call this once at the top of your experiment, passing in all important
        config vars as a dict. This will serialize the config to JSON, while
        handling anything which can't be serialized in a graceful way (writing
        as informative a string as possible).

        Example use:

        .. code-block:: python

            logger = EpochLogger(**logger_kwargs)
            logger.save_config(locals())
        """
        config_json = convert_json(config)
        if self.exp_name is not None:
            config_json["exp_name"] = self.exp_name
        output = json.dumps(
            config_json, separators=(",", ":\t"), indent=4, sort_keys=True
        )
        print(colorize("Saving config:\n", color="cyan", bold=True))
        print(output)
        with open(osp.join(self.output_dir, "config.json"), "w") as out:
            out.write(output)

    def setup_pytorch_saver(self, what_to_save):
        """
        Set up easy model saving for a single PyTorch model.

        Because PyTorch saving and loading is especially painless, this is
        very minimal; we just need references to whatever we would like to
        pickle. This is integrated into the logger because the logger
        knows where the user would like to save information about this
        training run.

        Args:
            what_to_save: Any PyTorch model or serializable object containing
                PyTorch models.
        """
        self.pytorch_saver_elements = what_to_save


class EpochLogger(Logger):
    """
    A variant of Logger tailored for tracking average values over epochs.

    Typical use case: there is some quantity which is calculated many times
    throughout an epoch, and at the end of the epoch, you would like to
    report the average / std / min / max value of that quantity.

    With an EpochLogger, each time the quantity is calculated, you would
    use

    .. code-block:: python

        epoch_logger.store(NameOfQuantity=quantity_value)

    to load it into the EpochLogger's state. Then at the end of the epoch, you
    would use

    .. code-block:: python

        epoch_logger.log_tabular(NameOfQuantity, **options)

    to record the desired values.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.epoch_dict = dict()

    def store(self, **kwargs):
        """
        Save something into the epoch_logger's current state.

        Provide an arbitrary number of keyword arguments with numerical
        values.
        """
        for k, v in kwargs.items():
            if not (k in self.epoch_dict.keys()):
                self.epoch_dict[k] = []
            self.epoch_dict[k].append(v)

    def log_tabular(self, key, val=None, with_min_and_max=False, average_only=False):
        """
        Log a value or possibly the mean/std/min/max values of a diagnostic.

        Args:
            key (string): The name of the diagnostic. If you are logging a
                diagnostic whose state has previously been saved with
                ``store``, the key here has to match the key you used there.

            val: A value for the diagnostic. If you have previously saved
                values for this key via ``store``, do *not* provide a ``val``
                here.

            with_min_and_max (bool): If true, log min and max values of the
                diagnostic over the epoch.

            average_only (bool): If true, do not log the standard deviation
                of the diagnostic over the epoch.
        """
        if val is not None:
            super().log_tabular(key, val)
        else:
            v = self.epoch_dict[key]
            vals = (
                np.concatenate(v)
                if isinstance(v[0], np.ndarray) and len(v[0].shape) > 0
                else v
            )
            stats = [1, 2, 3, 4]
            super().log_tabular(key if average_only else "Average" + key, stats[0])
            if not (average_only):
                super().log_tabular("Std" + key, stats[1])
            if with_min_and_max:
                super().log_tabular("Max" + key, stats[3])
                super().log_tabular("Min" + key, stats[2])
        self.epoch_dict[key] = []
