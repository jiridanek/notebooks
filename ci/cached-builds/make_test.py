#!/usr/bin/env python3
import argparse
import functools
import subprocess
import typing

"""Runs the make commands used to deploy, test, and undeploy image in Kubernetes"""


class Args(argparse.Namespace):
    """Type annotation to have autocompletion for args"""
    target: str


def main() -> None:
    parser = argparse.ArgumentParser("make_test.py")
    parser.add_argument("--target", type=str)
    args = typing.cast(Args, parser.parse_args())

    if args.target.startswith("rstudio"):
        deploy = "deploy"
    else:
        deploy = "deploy9"

    namespace = "ns-" + args.target.translate(str.maketrans("", "", "."))

    check_call(f"kubectl create namespace {namespace}", shell=True)
    check_call(f"kubectl config set-context --current --namespace={namespace}", shell=True)

    check_call(f"make {deploy}-{args.target}", shell=True)
    check_call(f"make test-{args.target}", shell=True)
    check_call(f"make un{deploy}-{args.target}", shell=True)

    print(f"[INFO] Finished testing {args.target}")


@functools.wraps(subprocess.check_call)
def check_call(*args, **kwargs) -> int:
    print(f"[INFO] Running command {args, kwargs}")
    result = subprocess.check_call(*args, **kwargs)
    print(f"\tDONE running command {args, kwargs}")
    return result


if __name__ == "__main__":
    main()
