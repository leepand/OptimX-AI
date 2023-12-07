from optimx.ext import YAMLDataSet

c = YAMLDataSet("../config/server_dev.yml")
c.load()

cc = {
    "ops_servers": ["recomserver", "rewardserver"],
    "recomserver": {
        "host": "0.0.0.0",
        "ports": [4001],
        "prebuild_path": "src",
        "server_name": "recomserver",
        "serving": True,
        "workers": 4,
    },
    "rewardserver": {
        "host": "0.0.0.0",
        "ports": [5001],
        "prebuild_path": "src",
        "server_name": "rewardserver",
        "serving": True,
        "workers": 4,
    },
}

c2 = YAMLDataSet("../config/server_prod.yml")
c2.save(cc)
