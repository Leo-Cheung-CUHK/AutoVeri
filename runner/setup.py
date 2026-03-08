"""
setup.py for autoverif-runner.

Prefer using pyproject.toml for new projects, but setup.py is used here
for maximum compatibility with older pip versions.
"""

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", encoding="utf-8") as fh:
    install_requires = [
        line.strip()
        for line in fh
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="autoverif-runner",
    version="0.1.0",
    author="AutoVerif AI",
    description="Local simulation runner for the AutoVerif AI platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://app.autoverif.ai",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            "autoverif-runner=autoverif_runner.main:cli",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        "Environment :: Console",
        "Topic :: Software Development :: Testing",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    ],
    keywords="verilator simulation hdl verification eda autoverif",
)
