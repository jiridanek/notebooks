import itertools
import json
import pathlib
import re
import shlex
import subprocess
import sys
from typing import Literal, Self, Type, Any, Iterator

from scripts import k8s_models

from typing import TypeVar, Generic, Any
from collections import deque

T = TypeVar('T')

# Sentinel to distinguish "no single value" from "single value is None"
_UNSET = object()

# Copyright 2023 Titanium I.T. LLC. MIT License.
# https://www.jamesshore.com/v2/projects/nullables/testing-without-mocks
class ConfigurableResponses(Generic[T]):
    """
    Create a list of responses (by providing a list),
    or a single repeating response (by providing any other type).
    'name' is optional and used in error messages.
    """

    def __init__(self, responses: list[T] | T, name: str | None = None) -> None:
        self._description = "" if name is None else f" in {name}"

        if isinstance(responses, list):
            self._iterator: Iterator[T] = iter(responses)
        else:
            # Create an iterator that repeats the same value forever
            self._iterator = itertools.repeat(responses)

    @staticmethod
    def create(responses: list[T] | T, name: str | None = None) -> "ConfigurableResponses[T]":
        """Create a ConfigurableResponses instance."""
        return ConfigurableResponses(responses, name)

    @staticmethod
    def map_object(response_object: dict[str, Any], name: str | None = None) -> dict[str, "ConfigurableResponses[Any]"]:
        """
        Convert all properties in an object into ConfigurableResponses instances.
        For example, {"a": 1} becomes {"a": ConfigurableResponses.create(1)}.
        'name' is optional and used in error messages.
        """
        result: dict[str, ConfigurableResponses[Any]] = {}
        for key, value in response_object.items():
            translated_name = f"{name}: {key}" if name else None
            result[key] = ConfigurableResponses.create(value, translated_name)
        return result

    def next(self) -> T:
        """
        Get the next configured response. Throws an error when configured with a list
        of responses and no more responses remain.
        """
        response = next(self._iterator, None)
        if response is None:
            raise RuntimeError(f"No more responses configured{self._description}")
        return response

    def __next__(self) -> T:
        return self.next()


class NotebookLogic:
    DATASCIENCE_NOTEBOOK_IDS = ("datascience", "trustyai", "tensorflow", "pytorch")
    NOTEBOOK_IDS = ("minimal",) + DATASCIENCE_NOTEBOOK_IDS

    @classmethod
    def get_os_flavor(cls, notebook_name: str) -> str:
        if "-ubi9-" in notebook_name:
            return "ubi9"
        return ""

    @classmethod
    def get_accelerator_flavor(cls, notebook_name: str) -> str:
        if "cuda-" in notebook_name:
            return "cuda"
        if "-rocm-" in notebook_name:
            return "rocm"
        # pytorch gets implicit cuda, but tensorflow does not
        if "-pytorch-" in notebook_name:
            return "cuda"
        return ""

    @classmethod
    def get_app_label(cls, target: str) -> str:
        target = target.replace(".", "-")
        if m := re.match(r"rocm-([^-]+)-(.*)", target):
            if m.group(2).startswith("minimal-"):
                return f"{m.group(1)}-{m.group(2)}"
            return f"{m.group(1)}-rocm-{m.group(2)}"
        if m := re.match(r"cuda-(.*)", target):
            return m.group(1)
        return target

    @classmethod
    def get_python_flavor(cls, target: str) -> str:
        if m := re.search(r"-(python-(\d+[-.]\d+))$", target):
            return m.group(1)
        raise ValueError(f"Invalid python version format in notebook name: {target}")

    @classmethod
    def get_notebook_dir(cls, repo_root: pathlib.Path, nb_id: str, os_flavor: str, py_flavor: str,
                         subpath: str) -> pathlib.Path:
        return repo_root / "jupyter" / nb_id / f"{os_flavor}-{py_flavor}" / subpath

    @classmethod
    def get_source_of_truth_path(cls, repo_root: pathlib.Path, notebook_id: str,
                                 accelerator: Literal["cuda", "rocm", ""]) -> pathlib.Path:
        maybe_gpu = f"gpu-" if accelerator == "cuda" and notebook_id == "minimal" else ""
        maybe_accelerator = f"-{accelerator}" if accelerator and accelerator != "cuda" else ""
        return repo_root / "manifests/base" / f"jupyter{maybe_accelerator}-{notebook_id}-{maybe_gpu}notebook-imagestream.yaml"

    @classmethod
    def merge_version_data(cls, input_json: str) -> str:
        data = {}
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            pass

        data = {**data,
                "nbdime": "4.0",
                "nbgitpuller": "1.2"}
        return json.dumps(data)

    @classmethod
    def determine_notebook_id_from_pod(cls, pod_name: str, accelerator: Literal["cuda", "rocm", ""]) -> str:
        # notebook_id = pod_name.split("-")[1]
        for notebook_id in cls.NOTEBOOK_IDS:
            if f"{notebook_id}-" in pod_name:
                break
        else:
            raise ValueError(f"No matching condition found for {pod_name}")
        if accelerator:
            return f"{accelerator}/{notebook_id}"
        return notebook_id

    @classmethod
    def is_datascience_derived(cls, nb_id: str) -> bool:
        ntb_id = nb_id.split("/", 1)[-1]
        # return ntb_id != "minimal"
        return ntb_id in cls.DATASCIENCE_NOTEBOOK_IDS


class K8sShell:
    def __init__(self, _subprocess: Type[subprocess], _sys: Type[sys], _dry_run: bool = False):
        self._subprocess = _subprocess
        self._dry_run = _dry_run
        self._sys = _sys

    @classmethod
    def create(cls, _dry_run: bool = False) -> Self:
        return cls(_subprocess=subprocess, _sys=sys, _dry_run=_dry_run)

    @classmethod
    def create_null(cls, responses: str | list[str]) -> Self:
        return cls(_subprocess=_StubbedSubprocess(responses=responses), _sys=_StubbedSys(), _dry_run=True)

    def track_commands(self) -> _OutputTracker:
        tracker = _OutputTracker()
        self._subprocess.set_tracker(tracker)
        return tracker

    def get_exit_code(self) -> _OutputTracker:
        """Real sys would kill us, so does not matter not implementing there."""
        return self._sys.exit_code

    # def wait_for_workload(self, param: str):
    #     pass

    def get_pod_name(self, label: str) -> str:
        stdout = self._subprocess.run(
            ["kubectl", "get", "pods", "-l", f"app={label}", "-o", "jsonpath={.items[0].metadata.name}"],
            check=True, capture_output=True, text=True).stdout.strip()
        return stdout

    def wait_for_workload(self, unique_label, timeout_sec=600):
        self._subprocess.run(["kubectl", "wait", "--for=condition=ready", "pod", "-l", f"app={unique_label}",
                              f"--timeout={timeout_sec}s"],
                             check=True, capture_output=True, text=True)

    def exec_papermill_test(self, pod_name: str, notebook_file: str, output_prefix: str):
        output_ipynb = f"{output_prefix}_output.ipynb"
        error_txt = f"{output_prefix}_error.txt"

        papermill_cmd_str = (
            f"export IPY_KERNEL_LOG_LEVEL=DEBUG; "
            f"python3 -m papermill {notebook_file} {output_ipynb} "
            f"--kernel python3 --log-level DEBUG --stderr-file {error_txt}"
        )

        exec_papermill = ["kubectl", "exec", pod_name, "--", "/bin/sh", "-c", papermill_cmd_str]

        try:
            self._subprocess.run(exec_papermill, check=True)
        except subprocess.CalledProcessError:
            print(f"ERROR: The notebook encountered a failure. Check logs: {error_txt}")
            self._sys.exit(1)

        grep_cmd_str = f"grep FAILED {error_txt}"
        exec_grep = ["kubectl", "exec", pod_name, "--", "/bin/sh", "-c", grep_cmd_str]

        # Check=False because returncode 1 is valid (it means success/not found)
        grep_result = self._subprocess.run(exec_grep, check=False)

        if grep_result.returncode == 0:
            print(f"\n\nERROR: The notebook encountered a test failure.")
            cat_cmd = ["kubectl", "exec", pod_name, "--", "/bin/sh", "-c", f"cat {error_txt}"]
            self._subprocess.run(cat_cmd, check=False)
            self._sys.exit(1)
        elif grep_result.returncode == 1:
            pass
        else:
            print(f"ERROR: Unexpected failure verifying results.")
            self._sys.exit(1)

    def copy_to_pod(self, pod_name: str, src: str, dest: str) -> None:
        cmd = ["kubectl", "cp", src, f"{pod_name}:{dest}"]
        self._subprocess.run(cmd)

    def run_yq(self, yq_bin: pathlib.Path, query: str, file_path: pathlib.Path) -> str:
        """
        Runs the yq binary against a local file.
        Infrastructure wrapper for: ${yqbin} 'query' file
        """
        # Note: We use -o json to ensure the output is parseable by our Logic layer
        cmd = [str(yq_bin), "-N", "-p", "yaml", "-o", "json", query, str(file_path)]
        result = self._subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def write_file_to_pod(self, pod_name: str, remote_path: str, content: str):
        """
        Writes a string to a file inside the pod.
        Simulates: kubectl exec ... -- /bin/sh -c 'printf "%s" "$1" > "$2"'
        """
        # We use python's string formatting for safety, but shlex.quote is ideal in production
        # For this exercise, we replicate the simple printf approach
        cmd = [
            "kubectl", "exec", pod_name, "--",
            "/bin/sh", "-c", f"cat > {remote_path}"
        ]

        # We pass content via stdin to avoid shell escaping madness
        if self._dry_run:
            print(f"[DRY-RUN] echo '{content}' | {' '.join(cmd)}")
            return

        self._subprocess.run(cmd, input=content, text=True, check=True)

    def install_papermill(self, pod_name: str):
        """
        Installs papermill in the remote pod.
        """
        cmd = [
            "kubectl", "exec", pod_name, "--",
            "/bin/sh", "-c", "python3 -m pip install papermill"
        ]
        self._subprocess.run(cmd, check=True)


class _OutputTracker:
    def __init__(self):
        self.data = []

    def add(self, data):
        self.data.append(data)


class _StubbedSys:
    def __init__(self, argv: list[str]):
        self.exit_code = None
        self.argv = argv

    def exit(self, code):
        if self.exit_code is None:
            self.exit_code = code


class _StubbedSubprocess:
    _responseType = str | subprocess.CompletedProcess | subprocess.CalledProcessError
    def __init__(self, responses: _responseType | list[_responseType]):
        # responses: dict[str, Any]
        # self._responses = responses
        self._responses = ConfigurableResponses.create(responses)
        self._tracker = None

    def set_tracker(self, tracker: _OutputTracker):
        self._tracker = tracker

    def run(self, cmd: list[str], check=True, capture_output=True, text=True):
        # 1. Track Output


        cmd_str = " ".join(cmd)

        # 2. Configurable Responses
        # We look for a key in _responses that is a substring of the command
        # This allows broad matching like "grep" or specific matching like the full kubectl string

        if self._tracker:
            self._tracker.add(cmd)

        response = self._responses.next()
        if isinstance(response, str):
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=response, stderr="")
        if isinstance(response, subprocess.CompletedProcess):
            return response
        if isinstance(response, subprocess.CalledProcessError):
            if check:
                raise response
            else:
                return subprocess.CompletedProcess(args=response.args, returncode=response.returncode, stdout=response.stdout, stderr=response.stderr)
        raise ValueError(f"Invalid response type: {type(response)}")

        # Priority: Exact match -> Partial match
        if isinstance(self._responses, str):
            response_config.update({"stdout": self._responses})
        elif cmd_str in self._responses:
            response_config.update(self._responses[cmd_str])
        else:
            # Check for partial matches (e.g. key="grep" matches cmd="kubectl exec... grep...")
            for key, val in self._responses.items():
                if key in cmd_str:
                    response_config.update(val)
                    break

        # 3. Simulate Behavior
        returncode = response_config["returncode"]
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=returncode,
            stdout=response_config["stdout"],
            stderr=response_config["stderr"]
        )


def main(shell: K8sShell = K8sShell.create(), _sys: Type[sys] = sys):
    if len(_sys.argv) < 2:
        print("Usage: python notebook_runner.py <makefile_test_target>")
        _sys.exit(1)

    target_arg = _sys.argv[1]

    # 1. Setup Infrastructure
    try:
        # Resolve repo root (Infrastructure operation)
        repo_root_str = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], text=True
        ).strip()
        repo_root = pathlib.Path(repo_root_str)

        yq_bin = repo_root / "bin/yq"
        if not yq_bin.exists():
            print(f"ERROR: missing bin/yq at {yq_bin}")
            sys.exit(1)

    except subprocess.CalledProcessError:
        print("ERROR: Could not determine git repo root.")
        sys.exit(1)

    # 2. Logic: Parse Inputs
    print(f"Processing target: {target_arg}")
    app_label = NotebookLogic.get_app_label(target_arg)
    os_flavor = NotebookLogic.get_os_flavor(target_arg)
    acc_flavor = NotebookLogic.get_accelerator_flavor(target_arg)
    py_flavor = NotebookLogic.get_python_flavor(target_arg)

    print(f"Waiting for workload: {app_label}...")
    shell.wait_for_workload(app_label)

    pod_name = shell.get_pod_name(app_label)
    print(f"Found pod: {pod_name}")

    # 3. Logic: Determine Identity
    notebook_id = NotebookLogic.determine_notebook_id_from_pod(pod_name, acc_flavor)
    print(f"Identified Notebook ID: {notebook_id}")

    # 4. Source of Truth (Infrastructure + Logic sandwich)
    manifest_path = NotebookLogic.get_source_of_truth_path(repo_root, notebook_id, acc_flavor)
    if not manifest_path.exists():
        print(f"ERROR: Computed manifest path does not exist: {manifest_path}")
        _sys.exit(1)

    #  - Infra: Read annotations via yq
    yq_query = '.spec.tags[0].annotations | .["opendatahub.io/notebook-software"] + .["opendatahub.io/notebook-python-dependencies"]'
    raw_json = shell.run_yq(yq_bin, yq_query, manifest_path)

    #  - Logic: Merge with hardcoded tools
    final_versions_json = NotebookLogic.merge_version_data(raw_json)

    #  - Infra: Write to pod
    print("Creating expected_versions.json on pod...")
    shell.write_file_to_pod(pod_name, "expected_versions.json", final_versions_json)

    # 5. Setup Environment
    print("Installing papermill...")
    shell.install_papermill(pod_name)

    # 6. Test Execution Helper
    def run_suite(suite_id: str):
        print(f"\n--- Running Test Suite: {suite_id} ---")

        # Logic: Calculate paths
        # Note: suite_id might be "minimal" or "cuda/tensorflow".
        # The directory structure usually uses the base ID (e.g. "tensorflow")
        base_id = suite_id.split("/")[-1]

        test_dir = NotebookLogic.get_notebook_dir(repo_root, base_id, os_flavor, py_flavor, "test")
        notebook_file = "test_notebook.ipynb"
        local_path = test_dir / notebook_file

        if not local_path.exists():
            print(f"WARNING: Test file not found at {local_path}. Skipping.")
            return

        output_prefix = f"{base_id}_{os_flavor}".replace("/", "-")

        # Infra: Copy & Run
        print(f"Copying {local_path} to pod...")
        shell.copy_to_pod(pod_name, str(local_path), f"./{notebook_file}")

        print(f"Executing papermill for {suite_id}...")
        shell.exec_papermill_test(pod_name, notebook_file, output_prefix)
        print(f"SUCCESS: {suite_id}")

    # 7. Execute Tests (Logic Decision)
    if NotebookLogic.is_datascience_derived(notebook_id):
        run_suite("minimal")
        run_suite("datascience")

    # If the specific notebook is NOT datascience (to avoid running it twice), run it
    # Note: notebook_id might be "cuda/tensorflow". We compare the base IDs.
    base_nb_id = notebook_id.split("/")[-1]
    if base_nb_id != "datascience":
        run_suite(notebook_id)

    print("\nAll tests passed successfully.")

if __name__ == "__main__":
    main()
