from setuptools import find_packages, setup

from vedro_profiling import version


def find_required():
    with open("requirements.txt") as f:
        return f.read().splitlines()


def find_dev_required():
    with open("requirements-dev.txt") as f:
        return f.read().splitlines()


setup(
    name="vedro-profiling",
    version=version,
    description="Vedro plugin for measuring resource usage of tests",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nikita Mikheev",
    author_email="thelol1mpo@gmail.com",
    python_requires=">=3.10",
    url="https://github.com/lolimpo/vedro-profiling",
    license="Apache-2.0",
    packages=find_packages(exclude=["tests", "tests.*"]),
    package_data={"vedro_profiling": ["py.typed"]},
    install_requires=find_required(),
    tests_require=find_dev_required(),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Typing :: Typed"
    ]
)
