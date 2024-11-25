import functools
import requests
import urllib.parse
import os

from optimx.utils.file_utils import fsync_open
import optimx.ext.shellkit as sh
from optimx.env import Config


class SDK:
    def __init__(self, host: str):
        self.host = host

    @functools.lru_cache(maxsize=None)
    def session(self):
        s = requests.Session()
        return s

    def request(self, method, endpoint, as_json=True, session=None, **kwargs):
        r = (session or self.session()).request(
            method=method, url=urllib.parse.urljoin(self.host, endpoint), **kwargs
        )
        r.raise_for_status()
        return (
            r.json()
            if as_json and r.headers.get("content-type") == "application/json"
            else r
        )

    def get(self, endpoint, **kwargs):
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        return self.request("POST", endpoint, **kwargs)

    def put(self, endpoint, **kwargs):
        return self.request("PUT", endpoint, **kwargs)


class RestClient(SDK):
    def __init__(self, host=None, name="models"):
        # super().__init__(host)
        if host is None:
            config = Config()
            model_host = config.get_local_model_host()
            model_port = config.get_local_model_port()
            self.host = f"http://{model_host}:{model_port}"
        else:
            self.host = host

        self.name = name

    def push(self, name, version, env, fnamelocal, filename):
        with open(fnamelocal, "rb") as f:
            _f = {"file": f}
            return self.post(
                f"/api/{self.name}/push",
                as_json=True,
                data={
                    "name": name,
                    "version": version,
                    "env": str(env),
                    "filename": filename,
                },
                files=_f,
            )

    def upload_blob(self, object_name, file_path):
        with open(file_path, "rb") as f:
            _f = {"file": f}
            return self.post(
                f"/api/{self.name}/upload_blob",
                as_json=True,
                data={"object_name": object_name, "bucket": "bucket"},
                files=_f,
            )

    def clone(self, name, version, env, save_path, rm_zipfile=True):
        resp = self.get(
            f"/api/{self.name}/clone",
            params={"name": name, "version": version, "env": env},
        )
        filename = f"{name}.tgz"
        dest_path = os.path.join(save_path, filename)
        if isinstance(resp, dict):
            print(resp)
            return resp
        with fsync_open(dest_path, "wb") as file:
            for data in resp.iter_content(chunk_size=1024):
                file.write(data)

        sh.unarchive(dest_path, os.path.join(save_path, name))
        if rm_zipfile:
            sh.rmfile(dest_path)

        print(f" - model data to path = `{os.path.join(save_path, name)}` ")
        print(f" - model data from env = `{env}` ")
        print(f" - model name = `{name}` ")
        print(f" - model version = `{version}` ")

    def deploy(self, name, version, local_path, filename, server_base_path="df"):
        zip_file = f"{filename}.tgz"
        sh.archive(zip_file, sh.walk(os.path.join(local_path, filename)))
        with open(zip_file, "rb") as f:
            _f = {"file": f}
            return self.post(
                f"/api/{self.name}/deploy",
                as_json=True,
                data={
                    "name": name,
                    "version": version,
                    "filename": filename,
                    "server_base_path": server_base_path,
                },
                files=_f,
            )
