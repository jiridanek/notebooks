#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import hashlib
import os
import pathlib
import pickle
import shutil
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Generator


@dataclasses.dataclass
class ProcessResult():
    """Cacheable result of a process execution."""

    args: list[str]
    """The arguments used to run the process, for debuggability."""

    stdout: str
    stderr: str
    returncode: int


def main():
    cache_dir = pathlib.Path("~/.cache/skopeo").expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]
    key = hashlib.sha256(str(args).encode()).hexdigest()
    value_file = cache_dir / key

    """Ad-hoc caching implementation.

    Caches the result of a process execution in a pickle file named by hash of the arguments..

    If the number of keys becomes large and listing the cache directory becomes slow,
     introduce a two-layer approach of using ./<2 chars of hash>/<hash> directory structure.

    Implemented after considering https://pypi.org/project/diskcache/
     and the alternative packages mentioned in its documentation."""
    value: ProcessResult
    if value_file.exists():
        print("Using cached result from {}".format(value_file), file=sys.stderr)
        with open(value_file, "rb") as value_fp:
            value = pickle.load(value_fp)
    else:
        print("running skopeo:", args, file=sys.stderr)
        skopeo_path = next(s for s in whiches("skopeo")
                           if pathlib.Path(s).absolute() != pathlib.Path(__file__))
        process = subprocess.run([skopeo_path, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 check=False)
        value = ProcessResult(
            args=args,
            stdout=process.stdout.decode(),
            stderr=process.stderr.decode(),
            returncode=process.returncode)
        with tempfile.NamedTemporaryFile(dir=cache_dir, delete=False) as tmp_file:
            pickle.dump(value, tmp_file, protocol=0)  # protocol 0 is text-based
        shutil.move(tmp_file.name, value_file)

    print(value.stdout, end="")
    print(value.stderr, end="", file=sys.stderr)
    sys.exit(value.returncode)


def whiches(cmd: str, mode: int = os.F_OK | os.X_OK, path: str = None) -> Generator[str, None, None]:
    """Returns an iterable of all occurrences of `cmd` in `PATH` or `path`."""
    paths = (path or os.environ.get("PATH", os.defpath)).split(os.pathsep)
    return (w for p in paths
            if (w := shutil.which(cmd, mode, p)) is not None)


if __name__ == "__main__":
    main()
