import logging
import psutil
import socket
import re
from datetime import datetime, timedelta
import uuid
import locale
from flask import (
    render_template,
    request,
    session,
    jsonify,
    Response,
    Blueprint,
    current_app,
    g,
)
from werkzeug.local import LocalProxy
from optimx.helpers import socket_families, socket_types
from optimx.model_process import compare_versions
from optimx.log import Logs

from flask_httpauth import HTTPBasicAuth

auth = HTTPBasicAuth()
logger = logging.getLogger("optimx.web")
webapp = Blueprint("optimx", __name__, static_folder="static")

users = {"admin": "admin", "leepand": 123}


@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None


def get_current_node():
    return current_app.optimx.get_node(g.node)


def get_current_service():
    return get_current_node().get_service()


current_node = LocalProxy(get_current_node)
current_service = LocalProxy(get_current_service)


def fromtimestamp(value, dateformat="%Y-%m-%d %H:%M:%S"):
    dt = datetime.fromtimestamp(int(value))
    return dt.strftime(dateformat)


def fromtimestamp2(value, dateformat="%Y-%m-%d %H:%M:%S"):
    dt = value.strftime(dateformat)
    return dt


@webapp.context_processor
def inject_nodes():
    return {"current_node": current_node, "nodes": current_app.optimx.get_nodes()}


@webapp.context_processor
def inject_header_data():
    sysinfo = current_service.get_sysinfo()
    uptime = timedelta(seconds=sysinfo["uptime"])
    uptime = str(uptime).split(".")[0]
    return {
        "os": sysinfo["os"],  # .decode('utf-8'),
        "hostname": sysinfo["hostname"],  # .decode('utf-8'),
        "uptime": uptime,
    }


@webapp.url_defaults
def add_node(endpoint, values):
    values.setdefault("node", g.node)


@webapp.before_request
def add_node():
    g.node = request.args.get("node", current_app.optimx.LOCAL_NODE)


@webapp.before_request
def check_access():
    if not current_node:
        return "Unknown optimx node specified", 404

    allowed_remote_addrs = current_app.config.get("PSDASH_ALLOWED_REMOTE_ADDRESSES")
    if allowed_remote_addrs:
        if request.remote_addr not in allowed_remote_addrs:
            current_app.logger.info(
                "Returning 401 for client %s as address is not in allowed addresses.",
                request.remote_addr,
            )
            current_app.logger.debug("Allowed addresses: %s", allowed_remote_addrs)
            return "Access denied", 401

    username = current_app.config.get("PSDASH_AUTH_USERNAME")
    password = current_app.config.get("PSDASH_AUTH_PASSWORD")
    if username and password:
        auth = request.authorization
        if not auth or auth.username != username or auth.password != password:
            return Response(
                "Access deined",
                401,
                {"WWW-Authenticate": 'Basic realm="psDash login required"'},
            )


@webapp.before_request
def setup_client_id():
    if "client_id" not in session:
        client_id = uuid.uuid4()
        current_app.logger.debug("Creating id for client: %s", client_id)
        session["client_id"] = client_id


@webapp.errorhandler(psutil.AccessDenied)
def access_denied(e):
    errmsg = "Access denied to %s (pid %d)." % (e.name, e.pid)
    return render_template("error.html", error=errmsg), 401


@webapp.errorhandler(psutil.NoSuchProcess)
def access_denied(e):
    errmsg = "No process with pid %d was found." % e.pid
    return render_template("error.html", error=errmsg), 404


@webapp.route("/")
@auth.login_required
def index():
    sysinfo = current_service.get_sysinfo()

    netifs = list(current_service.get_network_interfaces().values())
    netifs.sort(key=lambda x: x.get("bytes_sent"), reverse=True)

    data = {
        "load_avg": sysinfo["load_avg"],
        "num_cpus": sysinfo["num_cpus"],
        "memory": current_service.get_memory(),
        "swap": current_service.get_swap_space(),
        "disks": current_service.get_disks(),
        "cpu": current_service.get_cpu(),
        "users": current_service.get_users(),
        "net_interfaces": netifs,
        "page": "overview",
        "is_xhr": request.headers.get("X-Requested-With"),
    }

    return render_template("index.html", **data)


@webapp.route(
    "/processes", defaults={"sort": "cpu_percent", "order": "desc", "filter": "user"}
)
@webapp.route("/processes/<string:sort>")
@webapp.route("/processes/<string:sort>/<string:order>")
@webapp.route("/processes/<string:sort>/<string:order>/<string:filter>")
def processes(sort="pid", order="asc", filter="user"):
    procs = current_service.get_process_list()
    num_procs = len(procs)

    user_procs = [p for p in procs if p["user"] != "root"]
    num_user_procs = len(user_procs)
    if filter == "user":
        procs = user_procs

    procs.sort(key=lambda x: x.get(sort), reverse=True if order != "asc" else False)

    return render_template(
        "processes.html",
        processes=procs,
        sort=sort,
        order=order,
        filter=filter,
        num_procs=num_procs,
        num_user_procs=num_user_procs,
        page="processes",
        is_xhr=request.headers.get("X-Requested-With"),
    )


@webapp.route("/process/<int:pid>", defaults={"section": "overview"})
@webapp.route("/process/<int:pid>/<string:section>")
def process(pid, section):
    valid_sections = [
        "overview",
        "threads",
        "files",
        "connections",
        "memory",
        "environment",
        "children",
        "limits",
    ]

    if section not in valid_sections:
        errmsg = "Invalid subsection when trying to view process %d" % pid
        return render_template("error.html", error=errmsg), 404

    context = {
        "process": current_service.get_process(pid),
        "section": section,
        "page": "processes",
        "is_xhr": request.headers.get("X-Requested-With"),  # request.is_xhr
    }

    if section == "environment":
        penviron = current_service.get_process_environment(pid)

        whitelist = current_app.config.get("PSDASH_ENVIRON_WHITELIST")
        if whitelist:
            penviron = dict(
                (k, v if k in whitelist else "*hidden by whitelist*")
                for k, v in penviron.items()
            )

        context["process_environ"] = penviron
    elif section == "threads":
        context["threads"] = current_service.get_process_threads(pid)
    elif section == "files":
        context["files"] = current_service.get_process_open_files(pid)
    elif section == "connections":
        context["connections"] = current_service.get_process_connections(pid)
    elif section == "memory":
        context["memory_maps"] = current_service.get_process_memory_maps(pid)
    elif section == "children":
        context["children"] = current_service.get_process_children(pid)
    elif section == "limits":
        context["limits"] = current_service.get_process_limits(pid)

    return render_template("process/%s.html" % section, **context)


@webapp.route("/network")
def view_networks():
    netifs = list(current_service.get_network_interfaces().values())
    netifs.sort(key=lambda x: x.get("bytes_sent"), reverse=True)

    # {'key', 'default_value'}
    # An empty string means that no filtering will take place on that key
    form_keys = {
        "pid": "",
        "family": socket_families[socket.AF_INET],
        "type": socket_types[socket.SOCK_STREAM],
        "state": "LISTEN",
    }

    form_values = dict(
        (k, request.args.get(k, default_val)) for k, default_val in form_keys.items()
    )

    for k in ("local_addr", "remote_addr"):
        val = request.args.get(k, "")
        if ":" in val:
            host, port = val.rsplit(":", 1)
            form_values[k + "_host"] = host
            form_values[k + "_port"] = int(port)
        elif val:
            form_values[k + "_host"] = val

    conns = current_service.get_connections(form_values)
    conns.sort(key=lambda x: x["state"])

    states = [
        "ESTABLISHED",
        "SYN_SENT",
        "SYN_RECV",
        "FIN_WAIT1",
        "FIN_WAIT2",
        "TIME_WAIT",
        "CLOSE",
        "CLOSE_WAIT",
        "LAST_ACK",
        "LISTEN",
        "CLOSING",
        "NONE",
    ]

    return render_template(
        "network.html",
        page="network",
        network_interfaces=netifs,
        connections=conns,
        socket_families=socket_families,
        socket_types=socket_types,
        states=states,
        is_xhr=request.headers.get("X-Requested-With"),  # request.is_xhr,
        num_conns=len(conns),
        **form_values
    )


@webapp.route("/disks")
def view_disks():
    disks = current_service.get_disks(all_partitions=True)
    io_counters = list(current_service.get_disks_counters().items())
    io_counters.sort(key=lambda x: x[1]["read_count"], reverse=True)
    return render_template(
        "disks.html",
        page="disks",
        disks=disks,
        io_counters=io_counters,
        is_xhr=request.headers.get("X-Requested-With"),
    )


@webapp.route("/models")
def view_models():
    disks = current_service.get_disks(all_partitions=True)
    io_counters = list(current_service.get_disks_counters().items())
    # model_list = current_service.get_models_list()

    envs = {"Dev": "dev", "Prod": "prod"}
    form_keys = {
        "pid": "",
        "env": envs["Dev"],
        "type": socket_types[socket.SOCK_STREAM],
        "state": "LISTEN",
    }

    io_counters.sort(key=lambda x: x[1]["read_count"], reverse=True)
    form_values = dict(
        (k, request.args.get(k, default_val)) for k, default_val in form_keys.items()
    )
    models_list, sub_model_info = current_service.get_models_env(filters=form_values)
    return render_template(
        "models.html",
        page="models",
        disks=disks,
        envs=envs,
        models=models_list,
        sub_model_info=sub_model_info,
        io_counters=io_counters,
        is_xhr=request.headers.get("X-Requested-With"),
        **form_values
    )


@webapp.route(
    "/model/<modelname>",
    defaults={"section": "overview", "env": "dev", "version": "None"},
)
@webapp.route("/model/<modelname>/<string:version>/<string:env>/<string:section>/")
def model_details(modelname, section, env, version):
    filename = request.args.get("filename")
    seek_tail = request.args.get("seek_tail", "1") != "0"
    session_key = session.get("client_id")

    def read_log(filename, session_key, seek_tail=False):
        logs = Logs()
        logs.add_patterns([filename])
        log = logs.get(filename, key=session_key)
        if seek_tail:
            log.set_tail_position()
        return log.read()

    valid_sections = [
        "overview",
        "threads",
        "files",
        "connections",
        "memory",
        "environment",
        "children",
        "viewmodel",
    ]

    if section not in valid_sections:
        errmsg = "Invalid subsection when trying to view model %d" % 1
        return render_template("error.html", error=errmsg), 404
    form_values = {"env": env}
    models_list, sub_model_info = current_service.get_models_env(filters=form_values)
    model_details = sub_model_info[modelname]
    if model_details["model_version_cnt"] > 0:
        versions = model_details["model_version_list"]
        max_version = max(versions, key=lambda x: int(re.findall(r"v(\d+)", x)[0]))
    else:
        max_version = "v0"

    if version == "None":
        version = max_version
    context = {
        "model_info": {"name": modelname, "max_version": max_version},
        "section": section,
        "env": env,
        "current_version": version,
        "model_details": model_details,
        "page": "models",
        "is_xhr": request.headers.get("X-Requested-With"),  # request.is_xhr
    }

    (
        model_version_files_details,
        model_version_files,
    ) = current_service.get_model_version_info(name=modelname, version=version, env=env)
    context["file_nums"] = len(model_version_files)

    if section == "environment":
        penviron = "current_service.get_process_environment(pid)"

        whitelist = current_app.config.get("PSDASH_ENVIRON_WHITELIST")
        if whitelist:
            penviron = dict(
                (k, v if k in whitelist else "*hidden by whitelist*")
                for k, v in penviron.items()
            )

        context["process_environ"] = penviron
    elif section == "threads":
        context["threads"] = "current_service.get_process_threads(pid)"
    elif section == "files":
        context["files"] = model_version_files_details
    elif section == "connections":
        context["connections"] = "current_service.get_process_connections(pid)"
    elif section == "memory":
        context["memory_maps"] = "current_service.get_process_memory_maps(pid)"
    elif section == "children":
        context["children"] = "current_service.get_process_children(pid)"
    elif section == "viewmodel":
        # context["viewmodel"] = "current_service.get_process_limits(pid)"
        try:
            content_model = read_log(
                filename, session_key=session_key, seek_tail=seek_tail
            )
            context["content_model"] = content_model
        except:
            context["content_model"] = "nulls"
        context["filename"] = filename
    return render_template("model/%s.html" % section, **context)


@webapp.route("/logs")
def view_logs():
    available_logs = list(current_service.get_logs())
    # available_logs.sort(cmp=lambda x1, x2: locale.strcoll(x1['path'], x2['path']))

    return render_template(
        "logs.html",
        page="logs",
        logs=available_logs,
        is_xhr=request.headers.get("X-Requested-With"),
    )


@webapp.route("/log")
def view_log():
    filename = request.args["filename"]
    seek_tail = request.args.get("seek_tail", "1") != "0"
    session_key = session.get("client_id")

    try:
        content = current_service.read_log(
            filename, session_key=session_key, seek_tail=seek_tail
        )
    except KeyError:
        error_msg = "File not found. Only files passed through args are allowed."
        # if request.is_xhr:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return error_msg
        return render_template("error.html", error=error_msg), 404

    # if request.is_xhr:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return content

    return render_template("log.html", content=content, filename=filename)


import traceback


@webapp.route("/vmodel22")
def view_model22():
    filename = request.args["filename"]
    seek_tail = request.args.get("seek_tail", "1") != "0"
    session_key = session.get("client_id")

    try:

        def read_log(filename, session_key, seek_tail=False):
            logs = Logs()
            logs.add_patterns([filename])
            log = logs.get(filename, key=session_key)
            if seek_tail:
                log.set_tail_position()
            return log.read()

        # filename="../bird-Copy1.log"
        # content = current_service.read_log(
        content = read_log(filename, session_key=session_key, seek_tail=seek_tail)
        print(content, "content")
    except KeyError:
        print(traceback.format_exc())
        error_msg = "File not found. Only files passed through args are allowed."
        # if request.is_xhr:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return error_msg
        return render_template("error.html", error=error_msg), 404

    # if request.is_xhr:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return content

    global_display = {"page": "models"}

    return render_template(
        "model/viewmodel.html", content=content, filename=filename, **global_display
    )


@webapp.route("/log/search")
def search_log():
    filename = request.args["filename"]
    query_text = request.args["text"]
    session_key = session.get("client_id")

    try:
        data = current_service.search_log(filename, query_text, session_key=session_key)
        return jsonify(data)
    except KeyError:
        return "Could not find log file with given filename", 404


@webapp.route("/register")
def register_node():
    name = request.args["name"]
    port = request.args["port"]
    host = request.remote_addr

    current_app.optimx.register_node(name, host, port)
    return jsonify({"status": "OK"})


@webapp.route("/api/token")
def login_token():
    username = request.args["username"]
    # query_text = request.args['text']
    # session_key = session.get('client_id')

    try:
        data = username
        return jsonify({"status1": "ok", "status": 200})
    except KeyError:
        return "Could not find log file with given filename", 404
