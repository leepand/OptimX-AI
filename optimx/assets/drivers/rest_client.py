import functools
import requests
import urllib.parse
import json
from optimx.config import MODEL_SERVER_HOST


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


model_host = MODEL_SERVER_HOST["host"]
model_port = MODEL_SERVER_HOST["port"]
host_defualt = f"http://{model_host}:{model_port}"


class RestClient(SDK):
    def __init__(self, host=host_defualt, name="models"):
        super().__init__(host)
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
