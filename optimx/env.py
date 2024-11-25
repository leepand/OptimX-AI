import os
import json
from dotenv import load_dotenv
import optimx.ext.shellkit as sh


class Config:
    """
    Dynamic configuration class that loads environment variables.
    """

    def __init__(self):
        load_dotenv(override=True)  # Load environment variables from .env file

        self.local_path = os.getcwd()
        # Server configuration
        self.SERVERS = json.loads(
            os.getenv("SERVERS", json.dumps({"DF": ["df", "df2"], "CF": ["cf"]}))
        )
        # Model server for clone/deploy local model/codes
        self.REMOTE_MODEL_SERVER = json.loads(
            os.getenv(
                "REMOTE_MODEL_SERVER",
                json.dumps(
                    {
                        "cf": "http://34.210.82.189:8915",
                        "df": "http://54.214.110.168:5006",
                        "df2": "http://35.165.37.114:5006",
                    }
                ),
            )
        )
        # Workerplace configuration
        self.PREPROD_PATH = os.getenv(
            "PREPROD_PATH", os.path.join(self.local_path, "preprod")
        )
        self.PROD_PATH = os.getenv("PROD_PATH", os.path.join(self.local_path, "prod"))
        self.DEV_PATH = os.getenv("DEV_PATH", os.path.join(self.local_path, "dev"))
        self.BASE_MODEL_PATH = os.getenv(
            "BASE_MODEL_PATH", os.path.join(self.local_path)
        )
        self.base_logs_path = os.path.join(self.BASE_MODEL_PATH, "model_logs")
        sh.mkdir(self.PREPROD_PATH)
        sh.mkdir(self.PROD_PATH)
        sh.mkdir(self.DEV_PATH)
        sh.mkdir(self.BASE_MODEL_PATH)
        sh.mkdir(self.base_logs_path)
        defu_logs_fnames = [
            "recom_errors.log",
            "reward_errors.log",
            "recom_debugs.log",
            "reward_debugs.log",
        ]

        # API configuration
        self.API_KEY = os.getenv("API_KEY", "default_api_key")
        self.API_SECRET = os.getenv("API_SECRET", "default_api_secret")

        # Debugging
        self.DEBUG = os.getenv("DEBUG", "False") == "True"

        # Logs
        # 创建一个空文件
        for fname in defu_logs_fnames:
            log_file = os.path.join(self.base_logs_path, fname)
            # Open the file in write mode
            if not os.path.exists(log_file):
                open(log_file, "a").close()  # 以追加模式打开并立即关闭

        # Model server
        self.SERVER_PORT_CONFIG = json.loads(
            os.getenv(
                "SERVER_PORT_CONFIG",
                json.dumps(
                    {
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
                ),
            )
        )
        self.MAIN_MLOPS_SERVER_PORT = int(os.getenv("MAIN_MLOPS_SERVER_PORT", 8911))
        self.LOCAL_MODEL_SERVER_HOST = os.getenv("LOCAL_MODEL_SERVER_HOST", "0.0.0.0")
        self.LOCAL_MODEL_SERVER_PORT = int(os.getenv("LOCAL_MODEL_SERVER_PORT", 5005))

    def get_logs_path(self):
        """
        Get the logs base path.
        """
        return self.base_logs_path

    def get_log_files(self):
        base_logs_path = self.base_logs_path
        logs_path = os.path.join(base_logs_path, "*.log")
        log_files = [logs_path]
        return log_files

    def get_servers(self):
        return self.SERVERS

    def get_model_server_url(self, server):
        """获取远程模型服务的URL，用于本地cli的设置"""
        return self.REMOTE_MODEL_SERVER.get(server)

    def get_model_path(self, env="dev"):
        if env == "dev":
            _path = self.DEV_PATH
        elif env == "prod":
            _path = self.PROD_PATH
        else:
            _path = self.PREPROD_PATH
        return _path

    def get_base_model_path(self):
        """获取本地模型的部署存储根目录路径的（prod/dev）"""
        return self.BASE_MODEL_PATH

    def get_server_config_template(self):
        """获取模型服务的配置模版"""
        return self.SERVER_PORT_CONFIG

    def get_mlops_port(self):
        """获取MLOPS UI的port"""
        return self.MAIN_MLOPS_SERVER_PORT

    def get_local_model_host(self):
        """获取本地模型服务器的host，用于远程worker的clone/deploy"""
        return self.LOCAL_MODEL_SERVER_HOST

    def get_local_model_port(self):
        """获取本地模型服务器的port，用于远程worker的clone/deploy"""
        return self.LOCAL_MODEL_SERVER_PORT


# Usage example
# config = Config()
# print(config.get_database_url())
