import logging
from typing import Callable, List

import joblib
from tqdm.auto import tqdm

from .opts import options
from .utils.exceptions import ExceptionWithMessage, validate_type

log = logging.getLogger(__name__)


class MissingDependency(ExceptionWithMessage):
    pass


class ProgressParallel(joblib.Parallel):
    """
    Manage progress bar monitoring of parallel execution of tasks.
    """

    def __init__(self, total: int = None, *args, **kwargs):
        """
        Create a new progress bar, with `total` number of tasks,
        `args`/`kwargs` additional parameters to pass to the joblib.Parallel constructor.
        """

        self._total = total
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """
        Execute tasks in parallel with progress bar.
        """
        # with tqdm(**(options().get("tqdm") | {"total": self._total})) as self._pbar:
        #    return joblib.Parallel.__call__(self, *args, **kwargs)
        with tqdm(**(options().get("tqdm") or {"total": self._total})) as self._pbar:
            return joblib.Parallel.__call__(self, *args, **kwargs)

    def print_progress(self):
        """
        Our chance to update the progress bar once tasks complete.
        """
        if self._total is None:
            self._pbar.total = self.n_dispatched_tasks
        self._pbar.n = self.n_completed_tasks
        self._pbar.refresh()


def parallel(tasks: List[Callable], n_jobs: int = None) -> List[object]:
    """
    Execute a list of callables, `tasks`, in parallel, returning their return values as a list.
    """

    # Instantiate the (parallel) executor. The execution of runs is not threads-safe.
    # You must parallelize the execution with processes (prefer='processes', loky by default).
    p = ProgressParallel(n_jobs=n_jobs, total=len(tasks), prefer="processes")

    # Get the reeturn values, and return them as a list.
    # This function completes once all tasks return.
    rets = p(joblib.delayed(func)() for func in tasks)
    return rets


class Job:
    """
    Manage the execution of tasks as a parallelized job.
    """

    def __init__(
        self,
        tasks: List[Callable] = None,
        n_jobs: int = None,
        backend: str = None,
    ):
        """
        Prepare a new job to execute: `tasks` are callables to evaluate, `n_jobs` and `backend`
        are passed to joblib.Parallel. If not set, default values from options are used.
        Using ‘n_jobs=1’ enables to turn off parallel computing for debugging.
        """

        self.tasks: list = validate_type(tasks, list)
        self.backend = options().default_if_null(backend, "execution.backend")
        self.n_jobs: int = validate_type(
            options().default_if_null(n_jobs, "execution.n_jobs"), int
        )

    def execute(self) -> List[object]:
        """
        Execute the job.
        """

        # Figure out the degree of parallellism, and make it explicit for reporting.
        n_jobs = self.n_jobs

        if self.backend == "dask":
            try:
                from distributed import get_client
            except ImportError as e:
                raise MissingDependency(
                    "Dask backend requested but not installed, aborting."
                ) from e
            client = get_client()
            log.debug(f"Scheduler: {client.scheduler.address}")
            log.debug(f"Dask dashboard: {client.dashboard_link}")
            if self.n_jobs == -1:
                # Adjust n_jobs considering the number of workers available in Dask.
                n_jobs = len(client.scheduler_info()["workers"])
        elif self.backend == "ray":
            try:
                from ray import init as init_ray
                from ray import is_initialized as ray_is_initialized
                from ray.util.joblib import register_ray
            except ImportError as e:
                raise MissingDependency(
                    "Ray backend requested but not installed, aborting."
                ) from e
            if not ray_is_initialized():
                register_ray()
                init_ray(**options().get("execution.backend_params"))
        elif self.backend == joblib.parallel.DEFAULT_BACKEND:
            if self.n_jobs < 0:
                n_jobs = joblib.cpu_count() + 1 - self.n_jobs

        log.debug(f"Using backend: {self.backend}")
        with joblib.parallel_config(self.backend):
            log.debug(
                f"Executing {len(self.tasks)} tasks on {n_jobs} workers (backend:{self.backend})"
            )
            executed_tasks = parallel(self.tasks, n_jobs=n_jobs)
            return executed_tasks
