from setuptools import setup, find_packages

setup(
    name="nq",
    version="0.0.1",
    description="A tool for managing git submodule patches",
    author="lmstudio",
    packages=find_packages(),
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "nq=nq.cli:main",
        ],
    },
    classifiers=[],
)
