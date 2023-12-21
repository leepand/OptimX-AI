import os
import json
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from hashlib import sha1
import json
import numpy as np
from typing import Any, Dict, List, NewType, Optional, Set, Tuple, Union

from pydantic import (
    BaseModel,
    Extra,
    NonNegativeInt,
    confloat,
    conint,
    constr,
    validate_arguments,
    validator,
)

SHA_TZ = timezone(
    timedelta(hours=8),
    name="Asia/Shanghai",
)
MODEL_ENV = "dev"
VERSION = "0.0"


def get_bj_day():
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=11)
    beijing_now = utc_now.astimezone(SHA_TZ)
    _bj = beijing_now.strftime("%Y-%m-%d")  # 结果显示：'2017-10-07'

    return _bj


def get_week_day():
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=11)
    beijing_now = utc_now.astimezone(SHA_TZ)

    return beijing_now.weekday()


def get_bj_day_time():
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=11)
    beijing_now = utc_now.astimezone(SHA_TZ)
    _bj = beijing_now.strftime("%Y-%m-%d %H:%M:%S")  # 结果显示：'2017-10-07'

    return _bj


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


def sigmoid(x):
    return float(1 / (1 + np.exp(-x)))


ActionId = NewType("ActionId", constr(min_length=1))
Float01 = NewType("Float_0_1", confloat(ge=0, le=1))
Probability = NewType("Probability", Float01)


def get_pareto_front(p: Dict[ActionId, List[Probability]]) -> List[ActionId]:
    """
    Create Pareto optimal set of actions (Pareto front) A* identified as actions that are not dominated by any action
    out of the set A*.

    Parameters:
    -----------
    p: Dict[ActionId, Probability]
        The dictionary or actions and their sampled probability of getting a positive reward for each objective.

    Return
    ------
    pareto_front: set
        The list of Pareto optimal actions
    """
    # store non dominated actions
    pareto_front = []

    for this_action in p.keys():
        is_pareto = (
            True  # we assume that action is Pareto Optimal until proven otherwise
        )
        other_actions = [a for a in p.keys() if a != this_action]

        for other_action in other_actions:
            # check if this_action is not dominated by other_action based on
            # multiple objectives reward prob vectors
            is_dominated = not (
                # an action cannot be dominated by an identical one
                (p[this_action] == p[other_action])
                # otherwise, apply the classical definition
                or any(
                    p[this_action][i] > p[other_action][i]
                    for i in range(len(p[this_action]))
                )
            )

            if is_dominated:
                # this_action dominated by at least one other_action,
                # this_action is not pareto optimal
                is_pareto = False
                break

        if is_pareto:
            # this_action is pareto optimal
            pareto_front.append(this_action)

    return pareto_front


def test_pareto_front():
    # works in 2D
    #
    #    +
    # .3 |     X
    #    |
    # .2 |          X
    #    |
    # .1 |      X       X
    #    |
    #  0 | X            X
    #    +-----------------+
    #      0   .1  .2  .3

    p2d = {
        "a0": [0.1, 0.3],
        "a1": [0.1, 0.3],
        "a2": [0.0, 0.0],
        "a3": [0.1, 0.1],
        "a4": [0.3, 0.1],
        "a5": [0.2, 0.2],
        "a6": [0.3, 0.0],
        "a7": [0.1, 0.1],
    }

    assert get_pareto_front(p2d) == ["a0", "a1", "a4", "a5"]

    p2d = {
        "a0": [0.1, 0.1],
        "a1": [0.3, 0.3],
        "a2": [0.3, 0.3],
    }

    assert get_pareto_front(p2d) == ["a1", "a2"]

    # works in 3D
    p3d = {
        "a0": [0.1, 0.3, 0.1],
        "a1": [0.1, 0.3, 0.1],
        "a2": [0.0, 0.0, 0.1],
        "a3": [0.1, 0.1, 0.1],
        "a4": [0.3, 0.1, 0.1],
        "a5": [0.2, 0.2, 0.1],
        "a6": [0.3, 0.0, 0.1],
        "a7": [0.1, 0.1, 0.3],
    }

    assert get_pareto_front(p3d) == ["a0", "a1", "a4", "a5", "a7"]
