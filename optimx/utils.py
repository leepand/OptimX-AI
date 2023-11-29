import os
import platform
import random


def cat_file_content(file):
    with open(file, "r") as f:
        code_content = f.read()

    return code_content


def get_pid_from_port(strport):
    # Get process IDs using lsof command
    strport = str(strport)
    cmd = "lsof -i:%s | awk '{print $2}'" % strport
    fd_pid = os.popen(cmd)
    pids = fd_pid.read().strip().split("\n")
    fd_pid.close()

    if len(pids) == 1 and pids[0] == "":
        print("Process not found.")
        return []
    # Get command or memory information for each process
    pid_list = []
    for pid in pids:
        if pid != "PID":
            pid_list.append(pid)

    return pid_list


def get_process_details(strport, return_type="cmd"):
    valid_return_types = ["cmd", "cpu", "mem", "user", "start", "time"]
    if return_type not in valid_return_types:
        print("Valid return types:", ", ".join(valid_return_types))
        return [], []
    cmds_content = []

    # Get process IDs using lsof command
    cmd = "lsof -i:%s | awk '{print $2}'" % strport
    fd_pid = os.popen(cmd)
    pids = fd_pid.read().strip().split("\n")
    fd_pid.close()

    if len(pids) == 1 and pids[0] == "":
        print("Process not found.")
        return [], []

    # Get command or memory information for each process
    pid_list = []
    for pid in pids:
        if pid != "PID":
            pid_list.append(pid)

    pid_for_meta = random.choice(pid_list)
    if platform.system() == "Linux":
        if return_type == "cmd":
            cmd_option = "cmd"
        elif return_type == "mem":
            cmd_option = "%mem"
        elif return_type == "user":
            cmd_option = "user"
        elif return_type == "time":
            cmd_option = "time"
        elif return_type == "start":
            cmd_option = "start"
        else:
            cmd_option = "cmd"
        cmd = f"ps -p {pid_for_meta} -o {cmd_option} -ww"
    elif platform.system() == "Darwin":
        if return_type == "cmd":
            cmd_option = "command"
        elif return_type == "mem":
            cmd_option = "%mem"
        elif return_type == "user":
            cmd_option = "user"
        elif return_type == "time":
            cmd_option = "time"
        elif return_type == "start":
            cmd_option = "start"
        else:
            cmd_option = "command"
        cmd = f"ps -p {pid_for_meta} -o {cmd_option} -ww"
    else:
        return [], []

    cmds = os.popen(cmd)
    cmds_content.extend(cmds.read().strip().split("\n"))
    cmds.close()

    return cmds_content, pid_list
