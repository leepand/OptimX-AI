from optimx.utils.file_utils import data_dir
import optimx.ext.shellkit as sh
import os

SERVER_PORT_CONFIG = {
    "ops_servers": ["recomserver", "rewardserver"],
    "recomserver": {
        "host": "0.0.0.0",
        "ports": [5001],
        "prebuild_path": "src",
        "server_name": "recomserver",
        "serving": True,
        "workers": 4,
    },
    "rewardserver": {
        "host": "0.0.0.0",
        "ports": [5002],
        "prebuild_path": "src",
        "server_name": "rewardserver",
        "serving": True,
        "workers": 4,
    },
}

MODEL_BASE_PATH = data_dir()
MODEL_SERVER_HOST = {"host": "0.0.0.0", "port": 5005}
MAIN_SERVER_PORT = 8911
base_logs_path = os.path.join(MODEL_BASE_PATH, "model_logs")
sh.mkdir(base_logs_path)

def_logs_fnames = [
    "recom_errors.log",
    "reward_errors.log",
    "recom_debugs.log",
    "reward_debugs.log",
]
for fname in def_logs_fnames:
    log_file = os.path.join(base_logs_path, fname)
    # Open the file in write mode
    if not os.path.exists(log_file):
        with open(log_file, "w") as file:
            pass

logs_path = os.path.join(base_logs_path, "*.log")
LOGS_FILES = [logs_path]
REMOTE_PREDEPLOY_PATH_DF = "/home/ec2-user/models_deploy/local_models_optimx"
REMOTE_PREDEPLOY_PATH_CF = "/home/ec2-user/models_deploy/local_models"
REMOTE_PREDEPLOY_PATH_DICT = {
    "cf": REMOTE_PREDEPLOY_PATH_CF,
    "df": REMOTE_PREDEPLOY_PATH_DF,
}

REMOTE_MODEL_SERVER = {
    "cf": "http://34.210.82.189:5006",
    "df": "http://54.214.110.168:5006",
}
