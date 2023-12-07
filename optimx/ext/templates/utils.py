import os
import json
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from hashlib import sha1
import json

SHA_TZ = timezone(
    timedelta(hours=8),
    name="Asia/Shanghai",
)


def get_bj_day():
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=11)
    beijing_now = utc_now.astimezone(SHA_TZ)
    _bj = beijing_now.strftime("%Y-%m-%d")  # 结果显示：'2017-10-07'

    return _bj


def get_week_day():
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=11)
    beijing_now = utc_now.astimezone(SHA_TZ)

    return beijing_now.weekday()


def json_dumps_data(data):
    _data = json.dumps(
        data,
        separators=(",", ":"),
    )
    return _data


class littleAb:
    def __init__(self, name):
        self.name = name

    def _get_hash(self, client_id):
        salty = "{0}.{1}".format(self.name, client_id).encode("utf-8")

        # We're going to take the first 7 bytes of the client UUID
        # because of the largest integer values that can be represented safely
        # with Sixpack client libraries
        # More Info: https://github.com/seatgeek/sixpack/issues/132#issuecomment-54318218
        hashed = sha1(salty).hexdigest()[:7]
        return int(hashed, 16)


def debug_log(items, model_name, debug_db, logs_debug, request_id):
    debug_key = f"{model_name}:debug"
    debug_param = debug_db.get(debug_key)

    # 检查是否设置了调试参数
    if debug_param == "1":
        debug_log_file = os.path.join(logs_debug, f"{request_id}_params.txt")
        # 将请求参数写入调试日志文件
        with open(debug_log_file, "w") as f:
            f.write(json.dumps(items))


def remove_first_value_if_condition_met(lst, condition, n):
    if len(lst) > 0 and condition(lst, n):
        lst.pop(0)
    return lst


# 示例条件：如果列表第一个元素大于10，则去掉第一个值
def condition(lst, n):
    return len(lst) > n


def filter_value(lst, value):
    filtered_list = [x for x in lst if x != value]
    return filtered_list
