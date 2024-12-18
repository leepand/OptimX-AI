import bisect
import itertools
import json
import logging
import multiprocessing
import os
import sys
from time import perf_counter, sleep
import time

import click
import humanize
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, track
from rich.table import Table
from rich.tree import Tree

from optimx import ModelLibrary
from optimx.api import create_optimx_app
from optimx.assets.cli import assets_cli
from optimx.core.errors import ModelsNotFound
from optimx.core.library import download_assets
from optimx.core.model_configuration import list_assets
from optimx.utils.serialization import safe_np_dump

import optimx.ext.shellkit as sh
from optimx.ext import YAMLDataSet

from optimx.ext.prompts.prompt import create_template, readfile, PromptTemplate
from optimx.utils.shell_utils import get_port_status, start_service
from optimx.utils.killport import kill9_byport
from .env import Config


@click.group()
def optimx_cli():
    sys.path.append(os.getcwd())
    pass


optimx_cli.add_command(assets_cli)


def _configure_from_cli_arguments(models, required_models, settings):
    models = list(models) or None
    required_models = list(required_models) or None
    if not (models or os.environ.get("OPTIMX_DEFAULT_PACKAGE")):
        raise ModelsNotFound(
            "Please add `your_package` as argument or set the "
            "`OPTIMX_DEFAULT_PACKAGE=your_package` env variable."
        )

    service = ModelLibrary(
        models=models,
        required_models=required_models,
        settings=settings,
    )
    return service


@optimx_cli.command()
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", multiple=True)
def memory(models, required_models):
    """
    Show memory consumption of optimx models.
    """
    from memory_profiler import memory_usage

    def _load_model(m, service):
        service._load(m)
        sleep(1)

    service = _configure_from_cli_arguments(
        models, required_models, {"lazy_loading": True}
    )
    grand_total = 0
    stats = {}
    logging.getLogger().setLevel(logging.ERROR)
    if service.required_models:
        with Progress(transient=True) as progress:
            task = progress.add_task("Profiling memory...", total=len(required_models))
            for m in service.required_models:
                deps = service.configuration[m].model_dependencies
                deps = deps.values() if isinstance(deps, dict) else deps
                for dependency in list(deps) + [m]:
                    mu = memory_usage((_load_model, (dependency, service), {}))
                    stats[dependency] = mu[-1] - mu[0]
                    grand_total += mu[-1] - mu[0]
                progress.update(task, advance=1)

    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Model")
    table.add_column("Memory", style="dim")

    for k, (m, mc) in enumerate(stats.items()):
        table.add_row(
            m,
            humanize.naturalsize(mc * 10**6, format="%.2f"),
            end_section=k == len(stats) - 1,
        )
    table.add_row("Total", humanize.naturalsize(grand_total * 10**6, format="%.2f"))
    console.print(table)


@optimx_cli.command("list-assets")
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", multiple=True)
def list_assets_cli(models, required_models):
    """
    List necessary assets.

    List the assets necessary to run a given set of models.
    """
    service = _configure_from_cli_arguments(
        models, required_models, {"lazy_loading": True}
    )

    console = Console()
    if service.configuration:
        for m in service.required_models:
            assets_specs = list_assets(
                configuration=service.configuration, required_models=[m]
            )
            model_tree = Tree(f"[bold]{m}[/bold] ({len(assets_specs)} assets)")
            if assets_specs:
                for asset_spec_string in assets_specs:
                    model_tree.add(escape(asset_spec_string), style="dim")
            console.print(model_tree)


def add_dependencies_to_graph(g, model, configurations):
    g.add_node(
        model,
        type="model",
        fillcolor="/accent3/2",
        style="filled",
        shape="box",
    )
    model_configuration = configurations[model]
    if model_configuration.asset:
        g.add_node(
            model_configuration.asset,
            type="asset",
            fillcolor="/accent3/3",
            style="filled",
        )
        g.add_edge(model, model_configuration.asset)
    for dependent_model in model_configuration.model_dependencies:
        g.add_edge(model, dependent_model)
        add_dependencies_to_graph(g, dependent_model, configurations)


@optimx_cli.command()
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", multiple=True)
def dependencies_graph(models, required_models):
    import networkx as nx
    from networkx.drawing.nx_agraph import write_dot

    """
    Create a  dependency graph for a library.

    Create a DOT file with the assets and model dependency graph
    from a list of models.
    """
    service = _configure_from_cli_arguments(
        models, required_models, {"lazy_loading": True}
    )
    if service.configuration:
        dependency_graph = nx.DiGraph(overlap="False")
        for m in service.required_models:
            add_dependencies_to_graph(dependency_graph, m, service.configuration)
        write_dot(dependency_graph, "dependencies.dot")


@optimx_cli.command()
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", multiple=True)
def describe(models, required_models):
    """
    Describe a library.

    Show settings, models and assets for a given library.
    """
    service = _configure_from_cli_arguments(models, required_models, {})
    service.describe()


@optimx_cli.command()
@click.argument("model")
@click.argument("example")
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--n", "-n", default=100)
def time2(model, example, models, n):
    """
    Benchmark a model on an example.

    Time n iterations of a model's call on an example.
    """
    service = _configure_from_cli_arguments(models, [model], {"lazy_loading": True})

    console = Console()

    t0 = perf_counter()
    model = service.get(model)
    console.print(
        f"{f'Loaded model `{model.configuration_key}` in':50} "
        f"... {f'{perf_counter()-t0:.2f} s':>10}"
    )

    example_deserialized = json.loads(example)
    console.print(f"Calling `predict` {n} times on example:")
    console.print(f"{json.dumps(example_deserialized, indent = 2)}")

    times = []
    for _ in track(range(n)):
        t0 = perf_counter()
        model(example_deserialized)
        times.append(perf_counter() - t0)

    console.print(
        f"Finished in {sum(times):.1f} s, "
        f"approximately {sum(times)/n*1e3:.2f} ms per call"
    )

    t0 = perf_counter()
    model([example_deserialized] * n)
    batch_time = perf_counter() - t0
    console.print(
        f"Finished batching in {batch_time:.1f} s, approximately"
        f" {batch_time/n*1e3:.2f} ms per call"
    )


@optimx_cli.command("serve")
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", type=str, multiple=True)
@click.option("--host", type=str, default="localhost")
@click.option("--port", type=int, default=8000)
def serve(models, required_models, host, port):
    import uvicorn

    """
    Run a library as a service.

    Run an HTTP server with specified models using FastAPI
    """
    app = create_optimx_app(
        models=list(models) or None, required_models=list(required_models) or None
    )
    uvicorn.run(app, host=host, port=port)


@optimx_cli.command("predict")
@click.argument("model_name", type=str)
@click.argument("models", type=str, nargs=-1, required=False)
def predict(model_name, models):
    """
    Make predictions for a given model.
    """
    lib = _configure_from_cli_arguments(models, [model_name], {})
    model = lib.get(model_name)
    while True:
        r = click.prompt(f"[{model_name}]>")
        if r:
            res = model(json.loads(r))
            click.secho(json.dumps(res, indent=2, default=safe_np_dump))


def worker(lib, model_name, q_in, q):
    model = lib.get(model_name)
    n = 0
    done = False
    while not done:
        items = []
        indices = []
        while True:
            m = q_in.get()
            if m is None:
                done = True
                break
            k, item = m
            items.append(item)
            indices.append(k)
            if model.batch_size is None or len(items) >= model.batch_size:
                break
        for k, res in zip(indices, model.predict_gen(items)):
            q.put((k, res))
            n += 1
    q.put(None)
    return n


def writer(output, q, n_workers):
    next_index = 0
    items_to_write = []
    workers_done = 0
    done = False
    with open(output, "w") as f:
        while not done:
            while True:
                m = q.get()
                if m is None:
                    workers_done += 1
                    if workers_done == n_workers:
                        done = True
                        break
                    continue
                k, res = m
                bisect.insort(items_to_write, (k, res))
                if k == next_index:
                    break
            while len(items_to_write) and items_to_write[0][0] == next_index:
                _, res = items_to_write.pop(0)
                f.write(json.dumps(res) + "\n")
                next_index += 1
    return next_index


def writer_unordered(output, q, n_workers):
    workers_done = 0
    n_items = 0
    with open(output, "w") as f:
        while True:
            m = q.get()
            if m is None:
                workers_done += 1
                if workers_done == n_workers:
                    break
                continue
            _, res = m
            f.write(json.dumps(res) + "\n")
            n_items += 1

    return n_items


def reader(input, queues):
    queues_cycle = itertools.cycle(queues)
    q_in = next(queues_cycle)
    with open(input) as f:
        for k, l in enumerate(f):
            q_in.put((k, json.loads(l.strip())))
            q_in = next(queues_cycle)
    for q in queues:
        q.put(None)


@optimx_cli.command("batch")
@click.argument("model_name", type=str)
@click.argument("input", type=str)
@click.argument("output", type=str)
@click.option("--models", type=str, multiple=True)
@click.option("--processes", type=int, default=None)
@click.option("--unordered", is_flag=True)
def batch_predict(model_name, input, output, models, processes, unordered):
    """
    Barch predictions for a given model.
    """
    processes = processes or os.cpu_count()
    print(f"Using {processes} processes")
    lib = _configure_from_cli_arguments(models, [model_name], {"lazy_loading": True})

    manager = multiprocessing.Manager()
    results_queue = manager.Queue()
    n_workers = processes - 2
    items_queues = [manager.Queue() for _ in range(n_workers)]

    with multiprocessing.Pool(processes) as p:
        workers = [
            p.apply_async(worker, (lib, model_name, q_in, results_queue))
            for q_in in items_queues
        ]
        p.apply_async(reader, (input, items_queues))
        if unordered:
            r = p.apply_async(writer_unordered, (output, results_queue, n_workers))
        else:
            r = p.apply_async(writer, (output, results_queue, n_workers))
        wrote_items = r.get()
        for k, w in enumerate(workers):
            print(f"Worker {k} computed {w.get()} elements")
        print(f"Total: {wrote_items} elements")


@optimx_cli.command("tf-serving")
@click.argument("mode", type=click.Choice(["local-docker", "local-process", "remote"]))
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", multiple=True)
@click.option("--verbose", is_flag=True)
def tf_serving(mode, models, required_models, verbose):
    from optimx.utils.tensorflow import deploy_tf_models

    service = _configure_from_cli_arguments(
        models, required_models, {"lazy_loading": True}
    )

    deploy_tf_models(service, mode, verbose=verbose)


@optimx_cli.command("download-assets")
@click.argument("models", type=str, nargs=-1, required=False)
@click.option("--required-models", "-r", multiple=True)
def download(models, required_models):
    """
    Download all assets necessary to run a given set of models
    """
    download_assets(
        models=list(models) or None, required_models=list(required_models) or None
    )


@optimx_cli.command("init", no_args_is_help=True)
@click.option(
    "--project",
    "-p",
    help="project name",
    type=str,
    default="my_project",
    show_default=True,
)
@click.option(
    "--model",
    "-m",
    help="model name",
    type=str,
    default="my_model",
    show_default=True,
)
@click.option(
    "--version",
    "-v",
    help="model version",
    type=str,
    default="0.0",
    show_default=True,
)
def init(project, model, version):
    """
    Init ML project from ml_template.
    """
    base_path = os.getcwd()
    project_path = os.path.join(base_path, project)
    # make_containing_dirs(project_path)
    sh.mkdir(project_path)
    sh.write(f"{project_path}/.name", model)
    sh.write(f"{project_path}/.version", version)
    sh.mkdir(f"{project_path}/src")
    sh.mkdir(f"{project_path}/config")
    sh.mkdir(f"{project_path}/notebooks")
    sh.mkdir(f"{project_path}/logs")
    config = Config()
    with sh.cd(project_path):
        # 读取包中的文件内容-readme.md
        readme_contents = create_template(
            filename="README.md",
            input_variables=["model_name"],
            template_format="f-string",
            model_name=model,
        )

        readme_path = os.path.join(project_path, "README.md")
        sh.write(readme_path, readme_contents)

        recomserver_contents = create_template(
            filename="recomserver.py",
            input_variables=["model_name", "version"],
            template_format="jinja2",
            model_name=model,
            version=version,
        )

        # read recomserver.py
        recom_file_path = os.path.join(project_path, "src/recomserver.py")
        sh.write(recom_file_path, recomserver_contents)

        # read rewardserver.py
        rewardserver_contents = create_template(
            filename="rewardserver.py",
            input_variables=["model_name", "version"],
            template_format="jinja2",
            model_name=model,
            version=version,
        )

        # read recomserver.py
        reward_file_path = os.path.join(project_path, "src/rewardserver.py")
        utils_file_path = os.path.join(project_path, "src/utils.py")
        config_dev_meta_path = os.path.join(project_path, "config/server_dev.yml")
        config_prod_meta_path = os.path.join(project_path, "config/server_prod.yml")
        sh.write(reward_file_path, rewardserver_contents)
        sh.write(utils_file_path, readfile(sh, "utils.py"))
        c = YAMLDataSet(config_dev_meta_path)
        server_config_template = config.get_server_config_template()
        c.save(server_config_template)
        c_p = YAMLDataSet(config_prod_meta_path)
        c_p.save(server_config_template)

        # read config.py
        config_contents = create_template(
            filename="config.py",
            input_variables=["model_name"],
            template_format="jinja2",
            model_name=model,
        )
        config_notebooks_path = os.path.join(project_path, "notebooks/config.py")
        sh.write(config_notebooks_path, config_contents)

        # read open_debug_db.py
        open_debug_db_contents = create_template(
            filename="open_debug_db.py",
            input_variables=["model_name"],
            template_format="jinja2",
            model_name=model,
        )
        open_debug_db_path = os.path.join(project_path, "notebooks/open_debug_db.py")
        sh.write(open_debug_db_path, open_debug_db_contents)

        # read serving.py
        serving_contents = create_template(
            filename="serving.py",
            input_variables=["model_name"],
            template_format="jinja2",
            model_name=model,
        )
        serving_path = os.path.join(project_path, "notebooks/serving.py")
        sh.write(serving_path, serving_contents)
        logs_path = os.path.join(project_path, "logs/README.md")
        sh.write(logs_path, "## serving logs\n")

    print(f"Project {project} is created!")


# model_host = MODEL_SERVER_HOST["host"]
# model_port = MODEL_SERVER_HOST["port"]


@optimx_cli.command("run", no_args_is_help=True)
@click.option(
    "--service",
    "-s",
    help="service name: model_server/main",
    type=str,
    default="model_server",
    show_default=True,
)
@click.option(
    "--host",
    "-h",
    help="host of model server service",
    type=str,
    default="0.0.0.0",
    show_default=True,
)
@click.option(
    "--port",
    "-p",
    help="port of  model server service",
    type=str,
    default=None,
    show_default=True,
)
@click.option(
    "--mainport",
    help="main service port",
    type=str,
    default=None,
    show_default=True,
)
def run(service, host, port, mainport):
    """
    start services: main/model server.
    """
    config = Config()
    if port is None:
        port = config.get_local_model_port()
    base_path = config.get_base_model_path()
    if mainport is None:
        mainport = config.get_mlops_port()

    # start model server
    if service in ["model_server", "all"]:
        model_server_port_status = get_port_status(port=port)
        if model_server_port_status == "running":
            c = input(f"Confirm kill the model server port {port} (y/n)")
            if c == "n":
                return None
            else:
                kill9_byport(port)
                time.sleep(1)
                print(f"port {port} is killed! model server service")
        with sh.cd(base_path):
            sh.write(
                os.path.join(base_path, "model_server.py"),
                "from optimx.assets.drivers.dam import Dam\ndam = Dam()\n",
            )
            # 5005 与HTTPClient().get_config() 中的model_url的ip和port一致
            sh.write(
                os.path.join(base_path, "run_model_server.sh"),
                f"uvicorn model_server:dam.http_server --host 0.0.0.0 --port {port}",
            )

            model_server_run_msg = start_service(
                "nohup sh run_model_server.sh > run_model_server.log 2>&1 &"
            )

            print(
                f"stdout info: {model_server_run_msg}! model server service serving",
            )
    if service in ["main", "all"]:
        # start main serivce UI
        main_server_port_status = get_port_status(mainport)
        if main_server_port_status == "running":
            c = input(f"Confirm kill the main server port {mainport} (y/n)")
            if c == "n":
                return None
            else:
                kill9_byport(mainport)
                time.sleep(1)
                print(f"port {mainport} is killed! model server service")
        _server_host = "0.0.0.0"
        with sh.cd(base_path):
            process_script = f"optimxserver -p {mainport} > main_server.log 2>&1 &"
            main_service_msg = start_service(
                # script=f"nohup gunicorn --workers=3 -b {_server_host}:{mainport} {process_script}"
                script=f"nohup {process_script}"
            )
            print(
                f"serving ui info: {main_service_msg}! main service serving",
            )
