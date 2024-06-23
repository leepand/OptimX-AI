import logging
import psutil
import socket
import re
import os
from datetime import datetime, timedelta
from hashlib import md5
import uuid
import locale
import random
from flask import (
    render_template,
    after_this_request,
    request,
    redirect,
    url_for,
    make_response,
    session,
    jsonify,
    Response,
    Blueprint,
    current_app,
    g,
)
from pathlib import Path
import traceback

from werkzeug.local import LocalProxy
from optimx.helpers import socket_families, socket_types
from optimx.log import Logs
from optimx.utils.sys_utils import cat_file_content
from optimx.model_assets import ALLOWED_ENV
from optimx.config import MODEL_BASE_PATH
import optimx.ext.shellkit as sh
import importlib.util

from flask_httpauth import HTTPBasicAuth
from optimx import ServiceMgr
from .database import DB
from .api import Client
from .push_model_ui import SHA_TZ

auth = HTTPBasicAuth()
logger = logging.getLogger("optimx.web")
webapp = Blueprint("optimx", __name__, static_folder="static")

users = {"admin": "admin", "leepand": 123, "pandeng.li@163.com": 123}


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
    if isinstance(value, float):
        value = datetime.fromtimestamp(int(value))
    value = value.astimezone(SHA_TZ)
    dt = value.strftime(dateformat)
    return dt


@webapp.context_processor
def inject_nodes():
    user_info = DB.read(request.cookies.get("email"))
    if user_info:
        user_info = user_info[0][0]
    else:
        user_info = "None"
    return {
        "current_node": current_node,
        "nodes": current_app.optimx.get_nodes(),
        "user_info": user_info,
    }


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


# @webapp.before_request
def check_session():
    UID, PID, Session_code, email = (
        request.cookies.get("UID"),
        request.cookies.get("PID"),
        request.cookies.get("Session_code"),
        request.cookies.get("email"),
    )
    if UID == None and PID == None and email == None and Session_code == None:
        return "not_logged"
    elif not email == None and email != "":
        session_check = DB.get_session(email)
        if (
            UID == session_check[0]
            and PID == session_check[1]
            and email == session_check[2]
            and Session_code == session_check[3]
        ):
            return "logged"
        else:
            request.cookies.pop("UID", None)
            request.cookies.pop("PID", None)
            request.cookies.pop("email", None)
            request.cookies.pop("Session_code", None)
            return "session_cleared"
    else:
        return "not_logged"


@webapp.before_request
def check_access():
    if not current_node:
        return "Unknown optimx node specified", 404

    allowed_remote_addrs = current_app.config.get("OPTIMX_ALLOWED_REMOTE_ADDRESSES")
    if allowed_remote_addrs:
        if request.remote_addr not in allowed_remote_addrs:
            current_app.logger.info(
                "Returning 401 for client %s as address is not in allowed addresses.",
                request.remote_addr,
            )
            current_app.logger.debug("Allowed addresses: %s", allowed_remote_addrs)
            return "Access denied", 401

    username = current_app.config.get("OPTIMX_AUTH_USERNAME")
    password = current_app.config.get("OPTIMX_AUTH_PASSWORD")
    if username and password:
        auth = request.authorization
        if not auth or auth.username != username or auth.password != password:
            return Response(
                "Access deined",
                401,
                {"WWW-Authenticate": 'Basic realm="optimx login required"'},
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


@webapp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        UID, PID, Session_code, email = (
            request.cookies.get("UID"),
            request.cookies.get("PID"),
            request.cookies.get("Session_code"),
            request.cookies.get("email"),
        )
        if UID == None and PID == None and email == None and Session_code == None:
            return render_template("login.html")
        elif not email == None and email != "":
            session_check = DB.get_session(email)
            if (
                UID == session_check[0]
                and PID == session_check[1]
                and email == session_check[2]
                and Session_code == session_check[3]
            ):
                #  return redirect(url_for("optimx.index"))
                return render_template("login.html")
            else:
                request.cookies.pop("UID", None)
                request.cookies.pop("PID", None)
                request.cookies.pop("email", None)
                request.cookies.pop("Session_code", None)
                return render_template("login.html")
        else:
            return render_template("login.html")
    elif request.method == "POST":
        email = request.form.get("email")
        paswd = request.form.get("password")
        check_login = DB.read(email)
        if check_login == "User not found":
            return render_template("login.html", status="Account not registered.")
        else:
            if md5(paswd.encode()).hexdigest() == DB.read(email)[0][2]:
                cookies_set = DB.get_session(email)
                user_info = cookies_set[0][0]
                resp = make_response(
                    redirect(url_for("optimx.index", user_info=user_info))
                )  # return user details
                resp.set_cookie("UID", cookies_set[0])
                resp.set_cookie("PID", cookies_set[1])
                resp.set_cookie("email", cookies_set[2])
                resp.set_cookie("Session_code", cookies_set[3])
                return resp
            else:
                return render_template("login.html", status="Wrong email and password.")
    else:
        return redirect(url_for("login"))


@webapp.route("/logout", methods=["POST", "GET"])
def logout():
    if request.method == "GET":

        @after_this_request
        def after_index(response):
            response.set_cookie("UID", "")
            response.set_cookie("PID", "")
            response.set_cookie("email", "")
            response.set_cookie("Session_code", "")

            return response

        return redirect(url_for("optimx.home"))
    elif request.method == "POST":
        resp = make_response(redirect(url_for("optimx.home")))
        resp.delete_cookie("UID")
        resp.delete_cookie("PID")
        resp.delete_cookie("email")
        resp.delete_cookie("Session_code")
        return resp


@webapp.route("/sing-up", methods=["GET", "POST"])
def singup():
    if request.method == "GET":
        result = check_session()
        if result == "not_logged":
            return render_template("singup.html"), 200
        else:
            # return redirect(url_for("optimx.index"))
            return render_template("singup.html"), 200
    elif request.method == "POST":
        fullName = request.form.get("fullname")
        Email = request.form.get("email")
        Password = request.form.get("password")
        confirm = DB.create(fullName, Email, Password)
        if confirm == 201:
            return render_template("login.html", status="Account created sucessfull.")
        elif confirm == 302:
            return render_template("singup.html", status="Account already registered.")


@webapp.route("/home")
# @auth.login_required
def home():
    return render_template("home.html")


@webapp.route("/")
# @auth.login_required
def index():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    elif result == "logged":
        user_info = "leepand"#DB.read(request.cookies.get("email"))[0][0]
        sysinfo = current_service.get_sysinfo()

        netifs = list(current_service.get_network_interfaces().values())
        netifs.sort(key=lambda x: x.get("bytes_sent"), reverse=True)
        models_dev = current_service.get_models_origin("dev")
        models_prod = current_service.get_models_origin("prod")

        models_cnt = max(len(list(models_dev.keys())), len(list(models_prod.keys())))
        models = {}
        models["models_cnt"] = models_cnt
        model_version_cnt = 0

        for model in list(models_dev.keys()):
            if model in ["model_cnt", "page_info"]:
                continue
            model_version_cnt += len(models_dev[model]["version_list"])

        model_version_cnt = 0
        for model in list(models_prod.keys()):
            if model in ["model_cnt", "page_info"]:
                continue
            model_version_cnt += len(models_prod[model]["version_list"])

        models["model_version_cnt"] = model_version_cnt
        # print(user_info,"user_info")
        is_xhr = "x-requested-with" in request.headers
        data = {
            "models": models,
            "load_avg": sysinfo["load_avg"],
            "num_cpus": sysinfo["num_cpus"],
            "memory": current_service.get_memory(),
            "swap": current_service.get_swap_space(),
            "disks": current_service.get_disks(),
            "cpu": current_service.get_cpu(),
            "users": current_service.get_users(),
            "net_interfaces": netifs,
            "page": "overview",
            "user_info": user_info,
            "is_xhr": is_xhr,
        }

        return render_template("index.html", **data)


@webapp.route(
    "/processes", defaults={"sort": "cpu_percent", "order": "desc", "filter": "user"}
)
@webapp.route("/processes/<string:sort>")
@webapp.route("/processes/<string:sort>/<string:order>")
@webapp.route("/processes/<string:sort>/<string:order>/<string:filter>")
def processes(sort="pid", order="asc", filter="user"):
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    procs = current_service.get_process_list()
    num_procs = len(procs)

    user_procs = [p for p in procs if p["user"] != "root"]
    num_user_procs = len(user_procs)
    if filter == "user":
        procs = user_procs

    procs.sort(key=lambda x: x.get(sort), reverse=True if order != "asc" else False)
    is_xhr = "x-requested-with" in request.headers
    return render_template(
        "processes.html",
        processes=procs,
        sort=sort,
        order=order,
        filter=filter,
        num_procs=num_procs,
        num_user_procs=num_user_procs,
        page="processes",
        is_xhr=is_xhr,
    )


@webapp.route("/process/<int:pid>", defaults={"section": "overview"})
@webapp.route("/process/<int:pid>/<string:section>")
def process(pid, section):
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
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

    is_xhr = "x-requested-with" in request.headers
    context = {
        "process": current_service.get_process(pid),
        "section": section,
        "page": "processes",
        "is_xhr": is_xhr,  # request.is_xhr
    }

    if section == "environment":
        penviron = current_service.get_process_environment(pid)

        whitelist = current_app.config.get("OPTIMX_ENVIRON_WHITELIST")
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
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
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
    is_xhr = "x-requested-with" in request.headers
    return render_template(
        "network.html",
        page="network",
        network_interfaces=netifs,
        connections=conns,
        socket_families=socket_families,
        socket_types=socket_types,
        states=states,
        is_xhr=is_xhr,  # request.is_xhr,
        num_conns=len(conns),
        **form_values,
    )


@webapp.route("/disks")
def view_disks():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    disks = current_service.get_disks(all_partitions=True)
    io_counters = list(current_service.get_disks_counters().items())
    io_counters.sort(key=lambda x: x[1]["read_count"], reverse=True)
    is_xhr = "x-requested-with" in request.headers
    return render_template(
        "disks.html",
        page="disks",
        disks=disks,
        io_counters=io_counters,
        is_xhr=is_xhr,
    )


@webapp.route("/models")
def view_models():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    envs = {e: e for e in ALLOWED_ENV}
    previous = request.args.get("previous")
    next = request.args.get("next")
    page_index = request.args.get("page_index")
    page_info = None
    if page_index:
        page_info = {"previous": previous, "next": next, "page_index": int(page_index)}
    else:
        page_info = {"previous": "0", "next": "0", "page_index": 1}

    form_keys = {"env": envs["dev"]}
    form_values = dict(
        (k, request.args.get(k, default_val)) for k, default_val in form_keys.items()
    )

    for k in ["model_name"]:
        val = request.args.get(k, "")
        form_values["search_" + k] = val

    model_assets_info = current_service.get_model_assets(
        filters=form_values, page_info=page_info
    )
    models_list = []
    model_infos_sub = {}

    if model_assets_info["model_infos_sub"]:
        model_infos_sub = model_assets_info["model_infos_sub"]
        models_list = list(model_infos_sub.keys())
        models_list = [
            model for model in models_list if model not in ["model_cnt", "page_info"]
        ]
        model_infos_sub["env"] = model_assets_info["env"]
        # print(model_assets_info, "test")
    is_xhr = "x-requested-with" in request.headers
    return render_template(
        "models.html",
        page="models",
        envs=envs,
        models=models_list,
        sub_model_info=model_infos_sub,
        is_xhr=is_xhr,
        **form_values,
    )


@webapp.route(
    "/model/<modelname>",
    defaults={"section": "overview", "env": "dev", "version": "None"},
)
@webapp.route("/model/<modelname>/<string:version>/<string:env>/<string:section>/")
def model_details(modelname, section, env, version):
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
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
        "files",
        "environment",
        "viewmodel",
        "model_logs",
    ]

    if section not in valid_sections:
        errmsg = "Invalid subsection when trying to view model %d" % 1
        return render_template("error.html", error=errmsg), 404
    form_values = {"env": env}
    model_assets_info = current_service.get_model_assets(
        filters=form_values, model_names=[modelname]
    )
    model_details = model_assets_info["model_infos_sub"][modelname]
    model_details["name"] = modelname
    if len(model_details["version_list"]) > 0:
        versions = model_details["version_list"]
        max_version = max(versions, key=lambda x: float(re.findall(r"(\d+.\d+)", x)[0]))
    else:
        max_version = "0.0"

    if version == "None":
        version = max_version
    is_xhr = "x-requested-with" in request.headers
    context = {
        "model_info": {"name": modelname, "max_version": max_version},
        "section": section,
        "env": env,
        "current_version": version,
        "model_details": model_details,
        "page": "models",
        "is_xhr": is_xhr,  # request.is_xhr
    }

    model_version_files = model_details[version].get("contents", [])
    context["file_nums"] = 0
    if len(model_version_files) > 0:
        if model_details[version].get("size") != "0 KB":
            context["file_nums"] = len(model_version_files)

    if section == "environment":
        penviron = {}
        recomserver_ports_list = model_details["recom_ports"]
        rewardserver_ports_list = model_details["reward_ports"]
        penviron["recom_pid_process"] = {}
        penviron["reward_pid_process"] = {}
        penviron["reward_pid_list"] = []
        penviron["recom_pid_list"] = []
        penviron["recom_port"] = []
        penviron["reward_port"] = []
        if len(recomserver_ports_list) > 0:
            recom_port = recomserver_ports_list[0]
            penviron["recom_port"] = recom_port
            pid_list = current_service.get_pid_from_port_node(recom_port)
            if len(pid_list) > 0:
                penviron["recom_pid_list"] = pid_list
                pid_select = random.choice(pid_list)
                pid_info = current_service.get_process(int(pid_select))
                penviron["recom_pid_select"] = pid_select
                penviron["recom_workers"] = max(0, len(pid_list) - 1)
                penviron["recom_pid_process"] = pid_info

        if len(rewardserver_ports_list) > 0:
            reward_port = rewardserver_ports_list[0]
            penviron["reward_port"] = reward_port
            pid_list = current_service.get_pid_from_port_node(reward_port)
            if len(pid_list) > 0:
                penviron["reward_pid_list"] = pid_list
                penviron["reward_workers"] = max(0, len(pid_list) - 1)
                pid_select = random.choice(pid_list)
                pid_info = current_service.get_process(int(pid_select))
                penviron["reward_pid_select"] = pid_select
                penviron["reward_pid_process"] = pid_info

        context["process_environ"] = penviron

    elif section == "files":
        context["files"] = current_service.get_model_version_file_info(
            env=env, modelname=modelname, version=version, fnames=model_version_files
        )
    elif section == "viewmodel":
        # context["viewmodel"] = "current_service.get_process_limits(pid)"
        try:
            ops = request.args.get("ops")
            ori_ops = "model_logs"
            if ops in ["push_to_dev", "push_to_prod"]:
                from .push_model_ui import new_push, update_push

                # local asset-file path
                version_files_path = model_details[version].get("version_files_path")
                if ops == "push_to_dev":
                    profile = "dev"
                else:
                    profile = "prod"

                log_path = os.path.join(version_files_path, "logs")
                sh.mkdir(log_path)
                log_file = os.path.join(log_path, f"{filename}.log")

                push_params = {
                    "name": modelname,
                    "filename": version_files_path,
                    "profile": profile,
                    "log_file": log_file,
                    "dry_run": False,
                }
                if filename == "push_model_new":
                    push_params = push_params

                elif filename == "push_model_update":
                    push_params["bump_major"] = False
                    push_params["newversion"] = False

                elif filename == "push_model_bump_minor":
                    push_params["bump_major"] = False
                    push_params["newversion"] = True

                else:
                    push_params["bump_major"] = True
                    push_params["newversion"] = True

                if filename == "push_model_new":
                    new_push(**push_params)
                else:
                    update_push(**push_params)
                filename = os.path.join(log_path, f"{filename}.log")
            if ops == "restart":
                # ops = request.args.get("version")
                test = ServiceMgr([f"{modelname}:{version}"], env=env)
                test.start_service()
                ops = "model_logs"
                filename = "all"
                ori_ops = "restart"

            if ops == "testing":
                version_files_path = None
                if len(model_version_files) > 0:
                    version_files_path = model_details[version].get(
                        "version_files_path"
                    )

                if version_files_path:
                    base_path = version_files_path
                else:
                    base_path = os.path.join(MODEL_BASE_PATH, env, modelname, version)
                base_path = os.path.join(MODEL_BASE_PATH, env, modelname, version)
                if filename == "recom_test":
                    import json

                    log_name = os.path.join(base_path, "logs", "recom_test.log")
                    try:
                        # Load the Python file
                        test_data_file = os.path.join(base_path, "src", "test_data.py")
                        spec = importlib.util.spec_from_file_location(
                            "test_data", test_data_file
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        ports = model_details["recom_ports"]
                        test_result = Client(port=ports[0]).predict(module.recom)
                        if isinstance(module.recom, dict):
                            sh.write(log_name, json.dumps(module.recom))
                        else:
                            sh.write(log_name, str(module.recom))
                    except:
                        test_result = traceback.format_exc()

                    sh.write(log_name, "\n\n", "a")
                    sh.write(log_name, "\n\ntest result:\n\n", "a")
                    if isinstance(test_result, dict):
                        sh.write(log_name, json.dumps(test_result), "a")
                    else:
                        sh.write(log_name, str(test_result), "a")
                else:
                    import json

                    log_name = os.path.join(base_path, "logs", "reward_test.log")
                    try:
                        # Load the Python file
                        test_data_file = os.path.join(base_path, "src", "test_data.py")
                        spec = importlib.util.spec_from_file_location(
                            "test_data", test_data_file
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        ports = model_details["reward_ports"]
                        test_result = Client(port=ports[0]).predict(
                            module.reward, "predict/rewardserver"
                        )
                        if isinstance(module.recom, dict):
                            sh.write(log_name, json.dumps(module.reward))
                        else:
                            sh.write(log_name, str(module.reward))
                    except:
                        test_result = traceback.format_exc()

                    sh.write(log_name, "\n\n", "a")
                    sh.write(log_name, "\n\ntest result:\n\n", "a")
                    if isinstance(test_result, dict):
                        sh.write(log_name, json.dumps(test_result), "a")
                    else:
                        sh.write(log_name, str(test_result), "a")

                filename = log_name
                ops = "model_logs"
                ori_ops = "testing"

            if ops == "model_logs":
                if ori_ops == "testing":
                    context["content_model"] = cat_file_content(filename)
                    filename = filename
                else:
                    version_files_path = None
                    if len(model_version_files) > 0:
                        version_files_path = model_details[version].get(
                            "version_files_path"
                        )

                    if version_files_path:
                        base_path = version_files_path
                    else:
                        base_path = os.path.join(
                            MODEL_BASE_PATH, env, modelname, version
                        )
                    # print(base_path, "base_path")
                    log_path = os.path.join(base_path, "logs") + os.sep
                    if filename == "recom_log":
                        logs = Path(log_path).glob("*recom*.log")
                    elif filename == "reward_log":
                        logs = Path(log_path).glob("*reward*.log")
                    else:
                        logs = Path(log_path).glob("*.log")
                    file_contents = []
                    filenames = []
                    for _log in logs:
                        file_contents.append(cat_file_content(_log))
                        filenames.append(str(_log))
                    context["content_model"] = "\n".join(file_contents)
                    filename = "\n".join(filenames)
            else:
                # content_model = read_log(
                #    filename, session_key=session_key, seek_tail=seek_tail
                # )
                # context["content_model"] = content_model
                file_contents = [cat_file_content(filename)]
                context["content_model"] = "\n".join(file_contents)
        except:
            try:
                context["content_model"] = cat_file_content(filename)
            except:
                context["content_model"] = str(traceback.format_exc())

        context["filename"] = filename
    elif section == "overview":
        ops = request.args.get("ops")
        if ops == "restart":
            test = ServiceMgr([f"{modelname}:{version}"], env=env)
            test.start_service()
        if env == "preprod":
            context["push_script"] = (
                f"optimx assets push --name {modelname} \n"
                f"--profile {env} --filename {version} --preview --update \n"
                f"--newversion --bump"
            )
        else:
            recomserver_ports_list = model_details["recom_ports"]
            rewardserver_ports_list = model_details["reward_ports"]
            context["recom_status"] = "not deployed"
            if len(recomserver_ports_list) > 0:
                recom_port = recomserver_ports_list[0]
                # pid_list = current_service.get_pid_from_port_node(recom_port)
                status_port = current_service.get_port_status(recom_port)
                # if len(pid_list) > 0:
                if status_port == 0:
                    context["recom_status"] = "running"
                else:
                    context["recom_status"] = "failed"

            context["reward_status"] = "not deployed"
            if len(rewardserver_ports_list) > 0:
                reward_port = rewardserver_ports_list[0]
                # pid_list = current_service.get_pid_from_port_node(reward_port)
                status_port = current_service.get_port_status(reward_port)
                # if len(pid_list) > 0:
                if status_port == 0:
                    # if len(pid_list) > 0:
                    context["reward_status"] = "running"
                else:
                    context["reward_status"] = "failed"

    elif section == "model_logs":
        try:
            model_version_list_details = [
                modelv.get("file_path")
                for modelv in model_details["model_version_list_details"]
                if modelv.get("filename") == version
            ]
            if len(model_version_list_details) > 0:
                base_path = model_version_list_details[0]
            else:
                base_path = "./"
            log_path = os.path.join(base_path, "logs") + os.sep
            if filename == "recom_log":
                logs = Path(log_path).glob("*recom*.log")
            else:
                logs = Path(log_path).glob("*reward*.log")
            file_contents = []
            for _log in logs:
                file_contents.append(cat_file_content(_log))
            context["content_model"] = "\n".join(file_contents)
        except:
            base_path = model_details["model_version_list_details"].get("file_path", "")
            log_path = os.path.join(base_path, "logs") + os.sep
            _log = log_path
            context["content_model"] = str(traceback.format_exc())

        context["filename"] = _log
        # print(context)
        section = "viewmodel"

    return render_template("model/%s.html" % section, **context)


@webapp.route("/logs")
def view_logs():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    available_logs = list(current_service.get_logs())
    # available_logs.sort(cmp=lambda x1, x2: locale.strcoll(x1['path'], x2['path']))

    is_xhr = "x-requested-with" in request.headers
    return render_template(
        "logs.html",
        page="logs",
        logs=available_logs,
        is_xhr=is_xhr,
    )


@webapp.route("/log")
def view_log():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    filename = request.args["filename"]
    seek_tail = request.args.get("seek_tail", "1") != "0"
    session_key = session.get("client_id")

    try:
        content = current_service.read_log(
            filename, session_key="session_key", seek_tail=seek_tail
        )
    except KeyError:
        error_msg = "File not found. Only files passed through args are allowed."
        # if request.is_xhr:
        if "x-requested-with" in request.headers:
            return error_msg
        return render_template("error.html", error=error_msg), 404

    # if request.is_xhr:
    if "x-requested-with" in request.headers:
        # if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        # print(content,"x-requested-with")
        # print(request.headers)
        return content

    return render_template("log.html", page="logs", content=content, filename=filename)


@webapp.route("/log/search")
def search_log():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
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
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    name = request.args["name"]
    port = request.args["port"]
    host = request.remote_addr

    current_app.optimx.register_node(name, host, port)
    return jsonify({"status": "OK"})


@webapp.route("/api/token")
def login_token():
    result = check_session()
    result="logged"
    if result == "not_logged":
        return render_template("home.html")
    username = request.args["username"]
    # query_text = request.args['text']
    # session_key = session.get('client_id')

    try:
        data = username
        return jsonify({"status1": "ok", "status": 200})
    except KeyError:
        return "Could not find log file with given filename", 404
