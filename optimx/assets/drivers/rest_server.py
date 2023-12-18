from abc import ABCMeta
import os
import functools
import aiofiles
import logging

from fastapi import Depends, File, Form, FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTasks

import pydantic
import traceback

from optimx.config import MODEL_BASE_PATH, REMOTE_PREDEPLOY_PATH_DICT
import optimx.ext.shellkit as sh
from .dam import Dam

log = logging.getLogger("optimx")

api = FastAPI()


class Settings(pydantic.BaseSettings):
    dam: Dam = None
    filestore_dir: str = os.environ.get("FILESTORE_DIR", os.getcwd())


@functools.lru_cache()
def get_settings():
    return Settings()


async def save_file(file: UploadFile, filestore: str) -> str:
    """
    Saves the file to the filestore location.
    :param file: The temporary spooled file-like object.
    :param filestore: The location to where the file will be saved.
    :return: filename
    """
    try:
        # async with aiofiles.open(os.path.join(filestore, file.filename), "wb") as f:
        async with aiofiles.open(filestore, "wb") as f:

            # Read the data in chunks and save it, as we go.
            for i in iter(lambda: file.file.read(1024 * 1024 * 64), b""):

                # We can improve this by keeping track of the chunks saved,
                # report that number with an API endpoint and have the client
                # start the upload from the last saved chunk if the upload was
                # interrupted intentionally or due to a network failure.
                await f.write(i)
        log.info(f"File saved as {file.filename}")
    except Exception as e:

        # Not trying to cover all possible errors here, just bubble up the details.
        # Response format based on https://datatracker.ietf.org/doc/html/rfc7807
        problem_response = {"type": str(type(e).__name__), "details": str(e)}
        headers = {"Content-Type": "application/problem+json"}
        log.error(problem_response)
        raise HTTPException(status_code=500, detail=problem_response, headers=headers)
    return file.filename


@api.post("/api/models/push")
async def push_model(
    name: str = Form(...),
    version: str = Form(...),
    env: str = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    try:
        if file:
            model_path = os.path.join(MODEL_BASE_PATH, env, name, version, "db")
            remotefile = os.path.join(model_path, filename)
            parent_directory = os.path.dirname(remotefile)
            sh.mkdir(parent_directory)

            filename = await save_file(file, remotefile)

        return {"status": "ok", "details": f"model repo {remotefile} is created!"}
    except:
        return {"status": "failed", "details": str(traceback.format_exc())}


@api.post("/api/models/upload_blob")
async def upload_blob(
    object_name: str = Form(...),
    bucket: str = Form(...),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    try:
        if file:
            model_path = os.path.join(MODEL_BASE_PATH)
            remotefile = os.path.join(model_path, object_name)
            parent_directory = os.path.dirname(remotefile)
            sh.mkdir(parent_directory)

            filename = await save_file(file, remotefile)

        return {"status": "ok", "details": f"model repo {remotefile} is created!"}
    except:
        return {"status": "failed", "details": str(traceback.format_exc())}


def remove_file(path: str) -> None:
    os.unlink(path)


@api.get("/api/models/clone")
async def clone_file(
    name: str, version: str, env: str, background_tasks: BackgroundTasks
):
    try:
        model_path = os.path.join(MODEL_BASE_PATH)
        model_remotedir = os.path.join(model_path, env, name, version)
        model_tempdir = os.path.join(model_path, ".cache")
        sh.mkdir(model_tempdir)
        file_to_achive = os.path.join(model_tempdir, f"{name}.tgz")
        sh.archive(
            file_to_achive,
            sh.walk(
                model_remotedir, include=["*.py", "*.md", "*.ipynb", "*yml", "*.yaml"]
            ),
        )
        file_to_download = FileResponse(path=file_to_achive, filename=f"{name}.tgz")
        # sh.rmfile(file_to_achive)
        background_tasks.add_task(remove_file, file_to_achive)
        return file_to_download
    except:
        return {"status": "failed", "details": str(traceback.format_exc())}


@api.post("/api/models/deploy")
async def deploy_model(
    name: str = Form(...),
    version: str = Form(...),
    server_base_path: str = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
):
    try:
        if file:
            if server_base_path == "df":
                _server_base_path = REMOTE_PREDEPLOY_PATH_DICT["df"]
            elif server_base_path == "cf":
                _server_base_path = REMOTE_PREDEPLOY_PATH_DICT["cf"]
            else:
                _server_base_path = server_base_path

            model_path = os.path.join(_server_base_path, name, version)
            cache_path = os.path.join(_server_base_path, name, ".cache")
            sh.mkdir(cache_path)
            remotefile = os.path.join(cache_path, f"{filename}.tgz")
            sh.mkdir(model_path)
            _filename = await save_file(file, remotefile)
            dest_path = remotefile
            save_path = cache_path
            sh.rm(os.path.join(save_path, filename))
            sh.unarchive(dest_path, save_path)
            sh.cp(os.path.join(save_path, filename), model_path)

        return {"status": "ok", "details": f"model repo {remotefile} is created!"}
    except:
        return {"status": "failed", "details": str(traceback.format_exc())}
