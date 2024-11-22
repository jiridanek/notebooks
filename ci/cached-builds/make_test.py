#!/usr/bin/env python3
import argparse
import functools
import subprocess
import sys
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

    prefix = args.target.translate(str.maketrans(".", "-"))
    pod = prefix + "-notebook-0"  # `$(kubectl get statefulset -o name | head -n 1)` would work too
    namespace = "ns-" + prefix

    check_call(f"kubectl create namespace {namespace}", shell=True)
    check_call(f"kubectl config set-context --current --namespace={namespace}", shell=True)
    check_call(f"kubectl label namespace {namespace} fake-scc=fake-restricted-v2", shell=True)

    check_call(f"make {deploy}-{args.target}", shell=True)
    try:
        check_call(f"make test-{args.target}", shell=True)
        check_call(f"make un{deploy}-{args.target}", shell=True)
    finally:
        # dump a lot of info to the GHA logs

        call(f"kubectl get statefulsets", shell=True)
        call(f"kubectl describe statefulsets", shell=True)
        call(f"kubectl get pods", shell=True)
        call(f"kubectl describe pods", shell=True)
        # describe does not show everything about the pod
        call(f"kubectl get pods -o yaml", shell=True)

        # events aren't all that useful, but it can tell what was happening in the current namespace
        call(f"kubectl get events", shell=True)

        # relevant if the pod is crashlooping, this shows the final lines
        call(f"kubectl logs {namespace}/{pod} --previous", shell=True)
        # regular logs from a running (or finished) pod
        call(f"kubectl logs {namespace}/{pod}", shell=True)

    print(f"[INFO] Finished testing {args.target}")


@functools.wraps(subprocess.check_call)
def check_call(*args, **kwargs) -> int:
    print(f"[INFO] Running command {args, kwargs}")
    sys.stdout.flush()
    result = subprocess.check_call(*args, **kwargs)
    print(f"\tDONE running command {args, kwargs}")
    sys.stdout.flush()
    return result

@functools.wraps(subprocess.call)
def call(*args, **kwargs) -> int:
    print(f"[INFO] Running command {args, kwargs}")
    sys.stdout.flush()
    result = subprocess.call(*args, **kwargs)
    print(f"\tDONE running command {args, kwargs}")
    sys.stdout.flush()
    return result


if __name__ == "__main__":
    main()
