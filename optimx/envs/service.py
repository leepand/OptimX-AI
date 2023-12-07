import os
from pathlib import Path, PurePosixPath
from structlog import get_logger

from optimx.config import MODEL_BASE_PATH
from optimx.utils.addict import Dict

logger = get_logger(__name__)


class ServiceMgr:
    def __init__(self, models, env="dev") -> None:
        self.pipes = []
        self.env = env
        self.config_file_name = f"server_{env}.yml"
        for model in models:
            self.pipes.append(Pipe(name=model, profile=env))

    def start_service(self):
        service_msg = Dict()
        for pipe in self.pipes:
            latest_version = pipe.mlflow_client.list_model_versions(
                pipe.name, "Production"
            )
            if len(latest_version) > 0:
                version = f"v{latest_version[0].version}"
            else:
                model_ver = pipe.mlflow_client.list_model_versions(pipe.name)
                if len(model_ver) > 0:
                    v = model_ver[0]
                    version = f"v{v}"
                else:
                    logger.error(f"no version found of {pipe.name}", env=self.env)
                    continue

            prod_path = os.path.join(pipe.dir, version)
            if_dir = Path(prod_path).is_dir()
            status = "stoped"
            # msg = ""
            if not if_dir:
                # msg = "生产路径不存在"
                status = "no_code_path"
                logging.error(f"no_code_path of {pipe.name}")
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
                    model_name=pipe.name,
                )

            # make_msg = start_service_bymake(main_code_path=prod_path)
            service_msg[pipe.name]["msg"] = make_msg

        return service_msg
