from optimx.ext import YAMLDataSet
from optimx import Model, ModelLibrary, make
from optimx.utils.logx import log_recom_error, log_recom_debug
from optimx import make

import traceback
import numpy as np
import os
import json

from utils import debug_log, MODEL_ENV, VERSION


class RecomServer(Model):
    CONFIGURATIONS = {"recomserver": {"env": MODEL_ENV}}

    def _load(self):
        self.model_name = f"{{model_name}}"
        self.debug_db = make(
            f"cache/feature_store-v0.0", db_name="debug_tests.db", env=MODEL_ENV
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
            debug_log(
                items=items,
                model_name="{{model_name}}",
                debug_db=self.debug_db,
                logs_debug=self.recom_logs_debug,
                request_id=request_id,
            )

            return items
        except:
            # 将异常堆栈信息写入错误日志文件
            error_content = [
                f"{self.model_name}:{request_id}-error",
                str(traceback.format_exc()),
            ]
            log_recom_error([error_content])
            return items


library = ModelLibrary(models=[RecomServer])

model = library.get("recomserver")
