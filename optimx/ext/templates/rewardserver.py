from optimx.ext import YAMLDataSet
from optimx import Model, ModelLibrary
from optimx.utils.logx import log_reward_debug, log_reward_error
from optimx import make

import traceback
import numpy as np

from utils import MODEL_ENV, VERSION, json_dumps_data


class RewardServer(Model):
    CONFIGURATIONS = {"rewardserver": {"env": MODEL_ENV}}

    def _load(self):
        self.model_name = f"{{model_name}}"
        self.debug_db = make(
            "cache/feature_store-v1", db_name="debug_tests.db", env=MODEL_ENV
        )

        self.model_db = make(
            "cache/{{model_name}}-v{{version}}",
            db_name="{{model_name}}.db",
            env=MODEL_ENV,
        )

    def _predict(self, items):
        uid = items.get("uid")
        request_id = items.get("request_id")
        try:
            return items
        except:
            # 将异常堆栈信息写入错误日志文件
            error_content = [
                f"{self.model_name}:{request_id}-error",
                str(traceback.format_exc()),
            ]
            log_reward_error([error_content])
            debug_content = [
                f"{self.model_name}:{request_id}-debug",
                json_dumps_data(debug_content),
            ]
            log_reward_debug([debug_content])
            return items


library = ModelLibrary(models=[RewardServer])
model = library.get("rewardserver")
