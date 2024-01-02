import logging
import os
import platform
import psutil
import socket
import time
import zerorpc
from optimx.log import Logs
from optimx.helpers import socket_families, socket_types
from optimx.net import get_interface_addresses, NetIOCounters
from optimx.utils.sys_utils import get_process_details, get_pid_from_port, check_port

from optimx.model_assets import get_models_meta, get_file_info, ALLOWED_ENV

logger = logging.getLogger("optimx.node")


class Node(object):
    def __init__(self):
        self._service = None

    def get_id(self):
        raise NotImplementedError

    def _create_service(self):
        raise NotImplementedError

    def get_service(self):
        if not self._service:
            self._service = self._create_service()
        return self._service


class RemoteNode(Node):
    def __init__(self, name, host, port):
        super(RemoteNode, self).__init__()
        self.name = name
        self.host = host
        self.port = int(port)
        self.last_registered = None

    def _create_service(self):
        logger.info("Connecting to node %s", self.get_id())
        c = zerorpc.Client()
        c.connect("tcp://%s:%s" % (self.host, self.port))
        logger.info("Connected.")
        return c

    def get_id(self):
        return "%s:%s" % (self.host, self.port)

    def update_last_registered(self):
        self.last_registered = int(time.time())


class LocalNode(Node):
    def __init__(self):
        super(LocalNode, self).__init__()
        self.name = "OptimX"
        self.net_io_counters = NetIOCounters()
        self.logs = Logs()

    def get_id(self):
        return "localhost"

    def _create_service(self):
        return LocalService(self)


class LocalService(object):
    def __init__(self, node):
        self.node = node

    def get_model_assets(self, filters=None, model_names=[], page_info=None):
        filters = filters or {}
        model_infos = {}
        env = filters.get("env")
        if env in ALLOWED_ENV:
            search_model_name = filters.get("search_model_name")
            if search_model_name:
                search_model_name = search_model_name
            else:
                search_model_name = None
            model_infos_sub = get_models_meta(
                env=env,
                model_names=model_names,
                page_info=page_info,
                search_model_name=search_model_name,
            )
            model_infos["env"] = env
            model_infos["model_infos_sub"] = model_infos_sub
        return model_infos

    def get_models_origin(self, v):
        return get_models_meta(env=v)

    def get_model_version_file_info(self, env, modelname, version, fnames):
        version_files = get_file_info(
            env=env, name=modelname, version=version, filenames=fnames
        )
        return version_files

    def get_pid_from_port_node(self, port):
        return get_pid_from_port(port)

    def get_process_details_byport(self, port, cmd_type):
        cmds_content, pid_list = get_process_details(strport=port, return_type=cmd_type)
        return cmds_content, pid_list

    def get_sysinfo(self):
        uptime = int(time.time() - psutil.boot_time())
        sysinfo = {
            "uptime": uptime,
            "hostname": socket.gethostname(),
            "os": platform.platform(),
            "load_avg": os.getloadavg(),
            "num_cpus": psutil.cpu_count(),
        }

        return sysinfo

    def get_memory(self):
        return psutil.virtual_memory()._asdict()

    def get_swap_space(self):
        sm = psutil.swap_memory()
        swap = {
            "total": sm.total,
            "free": sm.free,
            "used": sm.used,
            "percent": sm.percent,
            "swapped_in": sm.sin,
            "swapped_out": sm.sout,
        }
        return swap

    def get_cpu(self):
        return psutil.cpu_times_percent(0)._asdict()

    def get_cpu_cores(self):
        return [c._asdict() for c in psutil.cpu_times_percent(0, percpu=True)]

    def get_disks(self, all_partitions=False):
        disks = []
        for dp in psutil.disk_partitions(all_partitions):
            usage = psutil.disk_usage(dp.mountpoint)
            disk = {
                "device": dp.device,
                "mountpoint": dp.mountpoint,
                "type": dp.fstype,
                "options": dp.opts,
                "space_total": usage.total,
                "space_used": usage.used,
                "space_used_percent": usage.percent,
                "space_free": usage.free,
            }
            disks.append(disk)

        return disks

    def get_disks_counters(self, perdisk=True):
        return dict(
            (dev, c._asdict())
            for dev, c in psutil.disk_io_counters(perdisk=perdisk).items()
        )

    def get_users(self):
        return [u._asdict() for u in psutil.users()]

    def get_port_status(self, port):
        return check_port(port=port)

    def get_network_interfaces(self):
        io_counters = self.node.net_io_counters.get()
        addresses = get_interface_addresses()

        netifs = {}
        for addr in addresses:
            c = io_counters.get(addr["name"])
            if not c:
                continue
            netifs[addr["name"]] = {
                "name": addr["name"],
                "ip": addr["ip"],
                "bytes_sent": c["bytes_sent"],
                "bytes_recv": c["bytes_recv"],
                "packets_sent": c["packets_sent"],
                "packets_recv": c["packets_recv"],
                "errors_in": c["errin"],
                "errors_out": c["errout"],
                "dropped_in": c["dropin"],
                "dropped_out": c["dropout"],
                "send_rate": c["tx_per_sec"],
                "recv_rate": c["rx_per_sec"],
            }

        return netifs

    def get_process_list(self):
        process_list = []
        for p in psutil.process_iter():
            mem = p.memory_info()

            # psutil throws a KeyError when the uid of a process is not associated with an user.
            try:
                username = p.username()
            except KeyError:
                username = None

            proc = {
                "pid": p.pid,
                "name": p.name(),
                "cmdline": " ".join(p.cmdline()),
                "user": username,
                "status": p.status(),
                "created": p.create_time(),
                "mem_rss": mem.rss,
                "mem_vms": mem.vms,
                "mem_percent": p.memory_percent(),
                "cpu_percent": p.cpu_percent(0),
            }
            process_list.append(proc)

        return process_list

    def get_process(self, pid):
        p = psutil.Process(pid)
        mem = p.memory_info()
        cpu_times = p.cpu_times()

        # psutil throws a KeyError when the uid of a process is not associated with an user.
        try:
            username = p.username()
        except KeyError:
            username = None

        return {
            "pid": p.pid,
            "ppid": p.ppid(),
            "parent_name": p.parent().name() if p.parent() else "",
            "name": p.name(),
            "cmdline": " ".join(p.cmdline()),
            "user": username,
            "uid_real": p.uids().real,
            "uid_effective": p.uids().effective,
            "uid_saved": p.uids().saved,
            "gid_real": p.gids().real,
            "gid_effective": p.gids().effective,
            "gid_saved": p.gids().saved,
            "status": p.status(),
            "created": p.create_time(),
            "terminal": p.terminal(),
            "mem_rss": mem.rss,
            "mem_vms": mem.vms,
            "mem_shared": 2,  # mem.shared,
            "mem_text": 2,  # "mem.text",
            "mem_lib": 3,  # "mem.lib",
            "mem_data": 3,  # "mem.data",
            "mem_dirty": 4,  # "mem.dirty",
            "mem_percent": p.memory_percent(),
            "cwd": p.cwd(),
            "nice": p.nice(),
            "io_nice_class": "p.ionice()[0]",
            "io_nice_value": "p.ionice()[1]",
            "cpu_percent": p.cpu_percent(0),
            "num_threads": p.num_threads(),
            "num_files": len(p.open_files()),
            "num_children": len(p.children()),
            "num_ctx_switches_invol": p.num_ctx_switches().involuntary,
            "num_ctx_switches_vol": p.num_ctx_switches().voluntary,
            "cpu_times_user": cpu_times.user,
            "cpu_times_system": cpu_times.system,
            "cpu_affinity": "p.cpu_affinity()",
        }

    def get_process_limits(self, pid):
        p = psutil.Process(pid)
        return {
            "RLIMIT_AS": p.rlimit(psutil.RLIMIT_AS),
            "RLIMIT_CORE": p.rlimit(psutil.RLIMIT_CORE),
            "RLIMIT_CPU": p.rlimit(psutil.RLIMIT_CPU),
            "RLIMIT_DATA": p.rlimit(psutil.RLIMIT_DATA),
            "RLIMIT_FSIZE": p.rlimit(psutil.RLIMIT_FSIZE),
            "RLIMIT_LOCKS": p.rlimit(psutil.RLIMIT_LOCKS),
            "RLIMIT_MEMLOCK": p.rlimit(psutil.RLIMIT_MEMLOCK),
            "RLIMIT_MSGQUEUE": p.rlimit(psutil.RLIMIT_MSGQUEUE),
            "RLIMIT_NICE": p.rlimit(psutil.RLIMIT_NICE),
            "RLIMIT_NOFILE": p.rlimit(psutil.RLIMIT_NOFILE),
            "RLIMIT_NPROC": p.rlimit(psutil.RLIMIT_NPROC),
            "RLIMIT_RSS": p.rlimit(psutil.RLIMIT_RSS),
            "RLIMIT_RTPRIO": p.rlimit(psutil.RLIMIT_RTPRIO),
            "RLIMIT_RTTIME": p.rlimit(psutil.RLIMIT_RTTIME),
            "RLIMIT_SIGPENDING": p.rlimit(psutil.RLIMIT_SIGPENDING),
            "RLIMIT_STACK": p.rlimit(psutil.RLIMIT_STACK),
        }

    def get_process_environment(self, pid):
        with open("/proc/%d/environ" % pid) as f:
            contents = f.read()
            env_vars = dict(
                row.split("=", 1) for row in contents.split("\0") if "=" in row
            )
        return env_vars

    def get_process_threads(self, pid):
        threads = []
        proc = psutil.Process(pid)
        for t in proc.threads():
            thread = {
                "id": t.id,
                "cpu_time_user": t.user_time,
                "cpu_time_system": t.system_time,
            }
            threads.append(thread)
        return threads

    def get_process_open_files(self, pid):
        proc = psutil.Process(pid)
        return [f._asdict() for f in proc.open_files()]

    def get_process_connections(self, pid):
        proc = psutil.Process(pid)
        connections = []
        for c in proc.connections(kind="all"):
            conn = {
                "fd": c.fd,
                "family": socket_families[c.family],
                "type": socket_types[c.type],
                "local_addr_host": c.laddr[0] if c.laddr else None,
                "local_addr_port": c.laddr[1] if c.laddr else None,
                "remote_addr_host": c.raddr[0] if c.raddr else None,
                "remote_addr_port": c.raddr[1] if c.raddr else None,
                "state": c.status,
            }
            connections.append(conn)

        return connections

    def get_process_memory_maps(self, pid):
        return [m._asdict() for m in psutil.Process(pid).memory_maps()]

    def get_process_children(self, pid):
        proc = psutil.Process(pid)
        children = []
        for c in proc.children():
            child = {
                "pid": c.pid,
                "name": c.name(),
                "cmdline": " ".join(c.cmdline()),
                "status": c.status(),
            }
            children.append(child)

        return children

    def get_connections(self, filters=None):
        filters = filters or {}
        connections = []

        for c in psutil.net_connections("all"):
            conn = {
                "fd": c.fd,
                "pid": c.pid,
                "family": socket_families[c.family],
                "type": socket_types[c.type],
                "local_addr_host": c.laddr[0] if c.laddr else None,
                "local_addr_port": c.laddr[1] if c.laddr else None,
                "remote_addr_host": c.raddr[0] if c.raddr else None,
                "remote_addr_port": c.raddr[1] if c.raddr else None,
                "state": c.status,
            }

            for k, v in filters.items():
                if v and conn.get(k) != v:
                    break
            else:
                connections.append(conn)

        return connections

    def get_logs(self):
        available_logs = []
        for log in self.node.logs.get_available():
            try:
                stat = os.stat(log.filename)
                available_logs.append(
                    {
                        "path": log.filename.encode("utf-8"),
                        "size": stat.st_size,
                        "atime": stat.st_atime,
                        "mtime": stat.st_mtime,
                    }
                )
            except OSError:
                logger.info(
                    'Could not stat "%s", removing from available logs', log.filename
                )
                self.node.logs.remove_available(log.filename)

        return available_logs

    def read_log(self, filename, session_key=None, seek_tail=False):
        log = self.node.logs.get(filename, key=session_key)
        if seek_tail:
            log.set_tail_position()
        return log.read()

    def search_log(self, filename, text, session_key=None):
        log = self.node.logs.get(filename, key=session_key)
        pos, bufferpos, res = log.search(text)
        stat = os.stat(log.filename)
        data = {
            "position": pos,
            "buffer_pos": bufferpos,
            "filesize": stat.st_size,
            "content": res,
        }
        return data
