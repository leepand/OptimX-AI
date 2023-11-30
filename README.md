# OptimX-AI

[![Build Status](https://img.shields.io/badge/leepand%2FOptimX-AI)](https://img.shields.io/badge/leepand%2FOptimX-AI)
[![License](https://img.shields.io/github/license/leepand/OptimX-AI)](https://img.shields.io/github/license/leepand/OptimX-AI)

OptimX-AI 是一个用于在线（online）强化学习（RL）模型的轻量级 MLOps，主要使用由[MLOpsKit](https://github.com/leepand/mini-mlops)提供的技术。

* [Features](#features)
* [Installation](#installation)
* [Getting started](#getting-started)
* [Configuration](#configuration)
* [Screenshots](#screenshots)
* [License](#license)


## Features

OptimX-AI是一个用于开发、部署和维护在线强化学习模型的框架。它支持实时更新模型，即在接收到反馈时立即更新模型，并在下一个请求中使用新的模型。在这个框架中，我们的应用场景主要使用小型模型，为每个用户构建独立的模型，并通过交互和优化来不断改进模型的决策能力。

✔ [*总览（Dashboard）*](https://www.github.com) • 系统的仪表板概述，显示 cpu、磁盘、网络、用户、内存、交换和模型数据。

✔ *多节点/集群* • 支持多个代理节点，这些节点要么由配置指定，要么在启动时将自身注册到运行 Web 界面的公共 optimx 节点。

✔ *Online-first* • 专为在线机器学习模型而设计，同时也支持批处理模型。

✔ *简洁优先* • 鼓励您使用SQL 处理数据并使用Python 定义模型。

✔ *自动更新* • 所有数据自动更新，无需刷新

✔ *日志监控* • 支持查看最新和搜索日志。日志按模式（如/var/log/*.log）添加，定期检查以说明新文件或已删除文件。

## Installation

请确保您的系统能够构建Python C扩展。在Debian派生的发行版，如Ubuntu，可以使用`apt-get`命令安装`build-essential`和`python-dev`软件包：

`# apt-get install build-essential python-dev`

而在RHEL（Fedora，CentOS等）发行版上：

```
# yum groupinstall "Development Tools"
# yum install python-devel
```

Installation using pip:<br>
`$ pip install .`

## Getting started

启动 optimx:<br>
`$ optimx`

使用 optimx agent:<br>
`$ optimx -a --register-to [http|https]://[host]:[port] --register-as my-agent-node`

这将以代理模式启动optimx，并尝试将节点注册到由`--register-to`选项指定的主optimx节点。当以代理模式启动optimx时，它会作为一个代理节点运行，并尝试将自己注册到主optimx节点上。这种模式允许将多个optimx节点连接到一个主节点，以实现集中化的监控和管理。

通过使用--register-to选项，您可以指定主optimx节点的地址，以便代理节点可以将自己注册到该主节点。一旦代理节点成功注册，它将与主节点建立连接，并向主节点汇报其状态和信息。主节点可以收集和展示所有注册的代理节点的数据，并提供集中化的监控和管理功能。

代理模式对于在分布式环境中部署optimx非常有用。通过将多个代理节点连接到一个主节点，您可以方便地监控和管理整个集群的状态和性能。这种架构还允许水平扩展，以适应不断增长的节点数量。

要成功使用代理模式，请确保主optimx节点已正确配置，并可以接受来自代理节点的注册请求。同时，代理节点需要正确指定--register-to选项，以确保连接到正确的主节点。

当以代理模式启动时，代理节点将在主机和端口上设置一个RPC服务器，而不是Web服务器。主机和端口分别由`-p/--port`和`-b/--bind`选项指定。

主 optimx 节点（提供HTTP服务）将显示可供切换的注册节点列表。

以下是可用的命令行参数（command-line arguments）：

```
$ optimx --help
usage: optimx [-h] [-l path] [-b host] [-p port] [-d] [-a]
              [--register-to host:port] [--register-as name]

optimx [version] - mlops information web dashboard

optional arguments:
  -h, --help            show this help message and exit
  -l path, --log path   log files to make available for optimx. Patterns (e.g.
                        /var/log/**/*.log) are supported. This option can be
                        used multiple times.
  -b host, --bind host  host to bind to. Defaults to 0.0.0.0 (all interfaces).
  -p port, --port port  port to listen on. Defaults to 5000.
  -d, --debug           enables debug mode.
  -a, --agent           Enables agent mode. This launches a RPC server, using
                        zerorpc, on given bind host and port.
  --register-to host:port
                        The optimx node running in web mode to register this
                        agent to on start up. e.g 10.0.1.22:5000
  --register-as name    The name to register as. (This will default to the
                        node's hostname)
```