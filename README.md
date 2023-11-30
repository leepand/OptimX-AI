# OptimX-AI
OptimX-AI 用于online-RL的轻量级MLOps平台

[![Build Status](https://img.shields.io/badge/leepand%2FOptimX-AI)](https://img.shields.io/badge/leepand%2FOptimX-AI)
[![License](https://img.shields.io/github/license/leepand/OptimX-AI)](https://img.shields.io/github/license/leepand/OptimX-AI)

optimx是一个用于在线强化学习（RL）模型的MLOps，主要使用由[MLOpsKit](https://github.com/leepand/mini-mlops)提供的技术。


* [Features](#features)
* [Installation](#installation)
* [Getting started](#getting-started)
* [Configuration](#configuration)
* [Screenshots](#screenshots)
* [License](#license)


## Features
OptimX-AI 是...

OptimX-AI是一个用于开发、部署和维护在线强化学习模型的框架。它支持实时更新模型，即在接收到反馈时立即更新模型，并在下一个请求中使用新的模型。在这个框架中，我们的应用场景主要使用小型模型，为每个用户构建独立的模型，并通过交互和优化来不断改进模型的决策能力。

✔ [*总览（Dashboard）*](https://www.github.com) • 系统的仪表板概述，显示 cpu、磁盘、网络、用户、内存、交换和模型数据。

✔ *多节点/集群* • 支持多个代理节点，这些节点要么由配置指定，要么在启动时将自身注册到运行 Web 界面的公共 optimx 节点。

✔ *Online-first* • 专为在线机器学习模型而设计，同时也支持批处理模型。

✔ *简洁优先* • 鼓励您使用SQL 处理数据并使用Python 定义模型。

✔ *自动更新* • 所有数据自动更新，无需刷新

✔ *日志监控* • 支持查看最新和搜索日志。日志按模式（如/var/log/*.log）添加，定期检查以说明新文件或已删除文件。