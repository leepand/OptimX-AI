from optimx.ext import YAMLDataSet
from optimx import Model, ModelLibrary
from optimx.utils.logx import (
    log_recom_error,
    log_recom_debug,
    log_reward_debug,
    log_reward_error,
)

import traceback
import numpy as np
import json
import os


class RewardServer(Model):
    CONFIGURATIONS = {"rewardserver": {}}

    def _load(self):
        self.debug_db = make("cache/feature_store-v1", db_name="debug_tests.db")

        self.model_db = make(
            "cache/{{model_name}}-v{{version}}", db_name="{{model_name}}.db"
        )

    def _predict(self, items):
        uid = items.get("uid")
        request_id = items.get("request_id")
        try:
            debug_log(
                items=items,
                model_name="{{model_name}}",
                debug_db=self.debug_db,
                logs_debug=self.reward_logs_debug,
                request_id=request_id,
            )

            return items
        except:
            # 将异常堆栈信息写入错误日志文件
            error_content = ["error", str(traceback.format_exc())]
            log_reward_error(error_content)
            return items


library = ModelLibrary(models=[RewardServer])

model = library.get("rewardserver")
