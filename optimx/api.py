import os
from typing import Any, Dict, List, Optional, Union

import fastapi
from rich.console import Console
from structlog import get_logger

from optimx.core.errors import ModelsNotFound
from optimx.core.library import LibrarySettings, ModelConfiguration, ModelLibrary
from optimx.core.model import AbstractModel, AsyncModel
from optimx.core.types import LibraryModelsType
import optimx.ext.shellkit as sh
from optimx.assets.manager import AssetsManager
from optimx.assets.remote import StorageProvider
from optimx.utils.file_utils import data_dir

logger = get_logger(__name__)


class OptimxAPIRouter(fastapi.APIRouter):
    def __init__(
        self,
        # ModelLibrary arguments
        settings: Optional[Union[Dict, LibrarySettings]] = None,
        assetsmanager_settings: Optional[dict] = None,
        configuration: Optional[
            Dict[str, Union[Dict[str, Any], ModelConfiguration]]
        ] = None,
        models: Optional[LibraryModelsType] = None,
        required_models: Optional[Union[List[str], Dict[str, Any]]] = None,
        # APIRouter arguments
        **kwargs,
    ) -> None:
        # add custom startup/shutdown events
        on_startup = kwargs.pop("on_startup", [])
        # on_startup.append(self._on_startup)
        kwargs["on_startup"] = on_startup
        on_shutdown = kwargs.pop("on_shutdown", [])
        on_shutdown.append(self._on_shutdown)
        kwargs["on_shutdown"] = on_shutdown
        super().__init__(**kwargs)

        self.lib = ModelLibrary(
            required_models=required_models,
            settings=settings,
            assetsmanager_settings=assetsmanager_settings,
            configuration=configuration,
            models=models,
        )

    async def _on_shutdown(self):
        await self.lib.aclose()


class OptimxAutoAPIRouter(OptimxAPIRouter):
    def __init__(
        self,
        # ModelLibrary arguments
        required_models: Optional[List[str]] = None,
        settings: Optional[Union[Dict, LibrarySettings]] = None,
        assetsmanager_settings: Optional[dict] = None,
        configuration: Optional[
            Dict[str, Union[Dict[str, Any], ModelConfiguration]]
        ] = None,
        models: Optional[LibraryModelsType] = None,
        # paths overrides change the configuration key into a path
        route_paths: Optional[Dict[str, str]] = None,
        # APIRouter arguments
        **kwargs,
    ) -> None:
        super().__init__(
            required_models=required_models,
            settings=settings,
            assetsmanager_settings=assetsmanager_settings,
            configuration=configuration,
            models=models,
            **kwargs,
        )

        route_paths = route_paths or {}
        for model_name in self.lib.required_models:
            m: AbstractModel = self.lib.get(model_name)
            if not isinstance(m, AbstractModel):
                continue
            path = route_paths.get(model_name, "/predict/" + model_name)
            batch_path = route_paths.get(model_name, "/predict/batch/" + model_name)

            summary = ""
            description = ""
            if m.__doc__:
                doclines = m.__doc__.strip().split("\n")
                summary = doclines[0]
                if len(doclines) > 1:
                    description = "".join(doclines[1:])

            console = Console(no_color=True)
            with console.capture() as capture:
                t = m.describe()
                console.print(t)
            description += "\n\n```" + str(capture.get()) + "```"

            logger.info("Adding model", name=model_name)
            item_type = m._item_type or Any
            try:
                item_type.schema()  # type: ignore
            except (ValueError, AttributeError):
                logger.info(
                    "Discarding item type info for model", name=model_name, path=path
                )
                item_type = Any

            self.add_api_route(
                path,
                self._make_model_endpoint_fn(m, item_type),
                methods=["POST"],
                description=description,
                summary=summary,
                tags=[str(type(m).__module__)],
            )
            self.add_api_route(
                batch_path,
                self._make_batch_model_endpoint_fn(m, item_type),
                methods=["POST"],
                description=description,
                summary=summary,
                tags=[str(type(m).__module__)],
            )
            logger.info("Added model to service", name=model_name, path=path)

    def _make_model_endpoint_fn(self, model, item_type):
        if isinstance(model, AsyncModel):

            async def _aendpoint(
                item: item_type = fastapi.Body(...),
                model=fastapi.Depends(lambda: self.lib.get(model.configuration_key)),
            ):
                return await model.predict(item)

            return _aendpoint

        def _endpoint(
            item: item_type = fastapi.Body(...),
            model=fastapi.Depends(lambda: self.lib.get(model.configuration_key)),
        ):
            return model.predict(item)

        return _endpoint

    def _make_batch_model_endpoint_fn(self, model, item_type):
        if isinstance(model, AsyncModel):

            async def _aendpoint(
                item: List[item_type] = fastapi.Body(...),
                model=fastapi.Depends(lambda: self.lib.get(model.configuration_key)),
            ):
                return await model.predict_batch(item)

            return _aendpoint

        def _endpoint(
            item: List[item_type] = fastapi.Body(...),
            model=fastapi.Depends(lambda: self.lib.get(model.configuration_key)),
        ):
            return model.predict_batch(item)

        return _endpoint


def create_optimx_app(models=None, required_models=None):
    """
    Creates a optimx FastAPI app with the specified models and required models.

    This is meant to be used in conjunction with gunicorn or uvicorn in order to
     start a server.

    Run with:
    ```
    export OPTIMX_REQUIRED_MODELS=... # optional
    export OPTIMX_DEFAULT_PACKAGE=... # mandatory
    gunicorn --workers 4 \
            --preload \
            --worker-class=uvicorn.workers.UvicornWorker \
            'optimx.api.create_optimx_app()'
    ```
    """
    if not (models or os.environ.get("OPTIMX_DEFAULT_PACKAGE")):
        raise ModelsNotFound(
            "Please add `your_package` as argument or set the "
            "`OPTIMX_DEFAULT_PACKAGE=your_package` env variable."
        )

    if os.environ.get("v_REQUIRED_MODELS") and not required_models:
        required_models = os.environ.get("OPTIMX_REQUIRED_MODELS").split(":")
    app = fastapi.FastAPI()
    router = OptimxAutoAPIRouter(required_models=required_models, models=models)
    app.include_router(router)
    return app


home_data_path = data_dir()


def pull_assets(
    name,
    env="dev",
    version=None,
    assets_dir=os.getcwd(),
    provider="local",
    bucket=home_data_path,
    force_download=False,
):
    """
    从指定的存储位置拉取资产。

    参数:
        name (str): 资产名称。
        env (str, 可选): 环境名称，默认为"dev"。
        version (str, 可选): 资产版本，默认为None。
        assets_dir (str, 可选): 资产保存目录，默认为当前工作目录。
        provider (str, 可选): 存储提供者，默认为"local"。
        bucket (str, 可选): 存储桶或路径，默认为home_data_path。
        force_download (bool, 可选): 是否强制下载资产，默认为False。

    返回值:
        assets_info (dict): 拉取的资产信息。

    """
    manager = AssetsManager(
        assets_dir=assets_dir,
        storage_provider=StorageProvider(
            provider=provider,
            bucket=bucket,
            prefix=env,
        ),
    )
    if version:
        model_meta = f"{name}:{version}"
    else:
        model_meta = name

    assets_info = manager.fetch_asset(
        model_meta, return_info=True, force_download=force_download
    )
    return assets_info
