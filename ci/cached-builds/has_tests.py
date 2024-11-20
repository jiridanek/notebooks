#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import typing

import gha_pr_changed_files

"""Determines whether we have deploy Makefile tests for this target or not"""


class Args(argparse.Namespace):
    """Type annotation to have autocompletion for args"""
    target: str


def main() -> None:
    parser = argparse.ArgumentParser("make_test.py")
    parser.add_argument("--target", type=str)
    args = typing.cast(Args, parser.parse_args())

    has_tests = False
    dirs = gha_pr_changed_files.analyze_build_directories(args.target)
    for d in dirs:
        kustomization = pathlib.Path(d) / "kustomize/base/kustomization.yaml"
        has_tests = has_tests or kustomization.is_file()

    if "GITHUB_ACTIONS" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "at") as f:
            json.dump({"tests": has_tests}, fp=f)

    print(f"{has_tests=}")


if __name__ == "__main__":
    main()
