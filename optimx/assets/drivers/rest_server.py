from abc import ABCMeta
import os
import functools

from fastapi import Depends, File, Form, FastAPI, UploadFile
import pydantic
import traceback

api = FastAPI()


class Settings(pydantic.BaseSettings):
    dam: None
    filestore_dir: str = os.environ.get("FILESTORE_DIR", os.getcwd())


@functools.lru_cache()
def get_settings():
    return Settings()


@api.post("/api/git-bus/models/push")
async def push_model(
    name: str = Form(...),
    version: str = Form(...),
    profile: str = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    try:
        if file:
            pipe_api_instance = pipe_api.APIClient(profile=profile)
            base_dir = pipe_api_instance.dir
            if version is None:
                base_file_path = os.path.join(base_dir, name)
            else:
                base_file_path = os.path.join(base_dir, name, version)

            remotefile = os.path.join(base_file_path, filename)
            parent_directory = os.path.dirname(remotefile)
            sh.mkdir(parent_directory)

            filename = await utils.save_file(file, remotefile)

        return {"status": "ok", "details": f"model repo {remotefile} is created!"}
    except:
        return {"status": "failed", "details": str(traceback.format_exc())}


class Dam(metaclass=ABCMeta):  # (pydantic.BaseSettings):
    def __init__(self):
        self.model_store = None
        self.data_store = None

    @property
    def http_server(self):
        def get_settings_override():
            return Settings(dam=self)

        api.dependency_overrides[get_settings] = get_settings_override

        return api
