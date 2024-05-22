import json
import math
import os
import re
from typing import Iterable, cast

"""Trivial Makefile parser that extracts target dependencies so that we can build each Dockerfile image target in its
own GitHub Actions job and handle dependencies between them.

The parsing is not able to handle general Makefiles, it only works with the Makefile in this project.
Use https://pypi.org/project/py-make/ or https://github.com/JetBrains/intellij-plugins/tree/master/makefile/grammars if you look for general parser."""


def read_makefile_lines(lines: Iterable[str]) -> list[str]:
    """Processes line continuations lines and line comments
    Note that this does not handle escaped backslash and escaped hash, or hash inside literals, ..."""
    output = []
    current = ""
    for line in lines:
        # remove comment
        if (i := line.find("#")) != -1:
            line = line[:i]

        # line continuation
        if line.endswith("\\\n"):
            current += line[:-2]
        else:
            current += line[:-1]
            output.append(current)
            current = ""
    if current:
        output.append(current)
    return output


def extract_target_dependencies(lines: Iterable[str]) -> dict[str, list[str]]:
    tree = {}
    for line in lines:
        # not a target
        if line.startswith("\t"):
            continue
        # .PHONY targets and such
        if line.startswith("."):
            continue

        r = re.compile(r"""
        ^                     # match from beginning
        ([-A-Za-z0-9.]+)\s*:  # target name
        (?:\s*                # any number of spaces between dependent targets
            ([-A-Za-z0-9.]+)  #     dependent target name(s)
        )*                    # ...
        \s*$                  # any whitespace at the end of the line
        """, re.VERBOSE)
        if m := re.match(r, line):
            target, *deps = m.groups()
            if deps == [None]:
                deps = []
            tree[target] = deps
    return tree


def compute_target_distances_from_root(tree: dict[str, list[str]]) -> dict[str, int]:
    levels = {key: math.inf for key in tree}

    # roots have distance of 0
    roots = [key for key, value in tree.items() if not value]
    for root in roots:
        levels[root] = 0

    # iterate through undetermined targets and try to compute their distance
    # this is an inefficient quadratic loop, but it does not matter here
    while math.inf in levels.values():
        changed = False
        for key, value in levels.items():
            if value == math.inf:
                dist = max(levels[dep] for dep in tree[key])
                if dist < math.inf:
                    levels[key] = dist + 1
                    changed = True
        if not changed:
            raise Exception("Iteration did not make any progress")

    # math.inf is a float; at this point we know all inf values were replaced by integral distances
    return cast(dict[str, int], levels)


def print_github_actions_matrix(levels: dict[str, int]) -> list[str]:
    """Outputs GitHub matrix definition Json as per
    """
    lines = []
    for level in set(levels.values()):
        targets: list[str] = list(l for l, v in levels.items() if v == level)

        # in level 0, we only want base images, not other utility tasks
        if level == 0:
            targets = [t for t in targets if t.startswith("base-")]

        # we won't build rhel-based images because they need subscription
        targets = [t for t in targets if "rhel" not in t]

        matrix = {"target": targets}
        lines.append(f"level{level}={json.dumps(matrix, separators=(",", ":"))}")
    return lines

def main() -> None:
    # https://www.gnu.org/software/make/manual/make.html#Reading-Makefiles
    with open("Makefile", "rt") as makefile:
        lines = read_makefile_lines(makefile)
    tree = extract_target_dependencies(lines)
    levels = compute_target_distances_from_root(tree)

    output = print_github_actions_matrix(levels)

    print(*output)
    with open(os.environ["GITHUB_OUTPUT"], "at") as f:
        for line in output:
            print(line, file=f)


if __name__ == '__main__':
    main()
