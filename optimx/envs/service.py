import os
import re
from pathlib import Path, PurePosixPath
from structlog import get_logger

from optimx.utils.addict import Dict
from optimx.envs.build_context import prebuild_server
from optimx.ext import YAMLDataSet
from optimx.assets.remote import StorageProvider
import traceback
import optimx.ext.shellkit as sh
from ..env import Config

logger = get_logger(__name__)


class ServiceMgr:
    def __init__(self, models, env="dev", provider="local", bucket=None) -> None:
        self.pipes = []
        self.env = env
        self.config_file_name = f"server_{env}.yml"
        config = Config()
        if bucket is None:
            bucket = config.get_base_model_path()
        self.bucket = bucket
        prefix = env
        self.storage_provider = StorageProvider(
            provider=provider,
            bucket=bucket,
            prefix=prefix,
        )
        # storage_provider.get_versions_info("new_model3")
        for model in models:
            model_version_list = model.split(":")
            self.pipes.append(model_version_list)

    def start_service(self):
        service_msg = Dict()
        for pipe in self.pipes:
            model_name = pipe[0]
            try:
                if len(pipe) > 1:
                    version = pipe[-1]
                else:
                    version_list = self.storage_provider.get_versions_info(model_name)
                    version = max(
                        version_list,
                        key=lambda x: float(re.findall(r"(\d+.\d+)", x)[0]),
                    )

            except:
                logger.error(f"no version found of {pipe[0]}", env=self.env)
                print(traceback.format_exc())
                continue

            prod_path = os.path.join(self.bucket, self.env, model_name, version)

            service_ops_file = os.path.join(
                self.bucket, self.env, model_name, ".SUCCESS"
            )
            sh.write(service_ops_file, str(version))

            if_dir = Path(prod_path).is_dir()
            status = "stoped"
            # msg = ""
            if not if_dir:
                # msg = "生产路径不存在"
                status = "no_code_path"
                logger.error(f"no_code_path of {model_name}", env=self.env)
                continue
            # service_msg[pipe.name]["msg"] = msg
            # service_msg[pipe.name]["status"] = status
            config_file = os.path.join(prod_path, "config", self.config_file_name)
            config = YAMLDataSet(config_file).load()
            ops_servers = config.get("ops_servers", ["recomserver", "rewardserver"])
            for ops_server in ops_servers:
                ops_server_config = config[ops_server]
                server_name = ops_server_config["server_name"]
                ports = ops_server_config["ports"]
                serving = ops_server_config["serving"]
                workers = ops_server_config["workers"]
                _prebuild_path = ops_server_config.get("prebuild_path", "src")

                prebuild_path = os.path.join(prod_path, _prebuild_path)
                make_msg = prebuild_server(
                    prebuild_path,
                    server_name,
                    ports,
                    workers=workers,
                    serving=serving,
                    model_name=model_name,
                )

            # make_msg = start_service_bymake(main_code_path=prod_path)
            service_msg[model_name]["msg"] = make_msg

        return service_msg
