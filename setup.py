from optimx import __version__
from setuptools import setup, find_packages

setup(
    name="optimx",
    version=__version__,
    description="optimx web dashboard",
    long_description="optimx is a mlops web dashboard for online RL models",
    classifiers=[
        "Topic :: System :: Monitoring",
        "Topic :: System :: Logging",
        "Topic :: System :: Networking :: Monitoring",
        "Development Status :: 4 - Beta",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "License :: Public Domain",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
    ],
    keywords="optimx web dashboard",
    author="leepand",
    author_email="leepand6@gmail.com",
    url="https://github.com/leepand/OptimX-AI",
    license="Apache License 2.0",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "Flask",
        "psutil",
        "glob2",
        "gevent",
        "zerorpc",
        "netifaces",
        "argparse",
    ],
    test_suite="tests",
    tests_require=["unittest2"],
    entry_points={
        "console_scripts": [
            "optimxserver = optimx.run:main",
            "optimx = optimx.cli:optimx_cli",
        ]
    },
)
