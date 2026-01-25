import json
import subprocess
import uuid

import pytest

from . import k8s_models, notebook_runner
from .notebook_runner import K8sShell, NotebookLogic


@pytest.mark.parametrize("notebook_name, expected_flavor", [
    # Bash: case "${full_notebook_name}" in *ubi9-*) ...
    ("jupyter-ubi9-python-3.9", "ubi9"),
    ("jupyter-alpine-python", ""),
])
def test_get_os_flavor(notebook_name, expected_flavor):
    assert NotebookLogic.get_os_flavor(notebook_name) == expected_flavor


@pytest.mark.parametrize("notebook_name, expected_flavor", [
    # Bash: *cuda-* | jupyter-pytorch-*)
    ("jupyter-pytorch-ubi9", "cuda"),
    ("cuda-jupyter-tensorflow-ubi9", "cuda"),
    # Bash: *rocm-*)
    ("jupyter-rocm-tensorflow-ubi9", "rocm"),
    ("jupyter-minimal-ubi9", ""),
])
def test_get_accelerator_flavor(notebook_name, expected_flavor):
    assert NotebookLogic.get_accelerator_flavor(notebook_name) == expected_flavor


@pytest.mark.parametrize("target, expected_label", [
    # Standard CUDA case: strips 'cuda-', replaces dots
    ("cuda-jupyter-tensorflow-ubi9-python-3.9", "jupyter-tensorflow-ubi9-python-3-9"),

    # Standard Pytorch case (no cuda prefix in target usually, but handled)
    ("jupyter-pytorch-ubi9-python-3.9", "jupyter-pytorch-ubi9-python-3-9"),

    # ROCm case: converts 'rocm-jupyter' to 'jupyter-rocm'
    ("rocm-jupyter-tensorflow-ubi9-python-3.9", "jupyter-rocm-tensorflow-ubi9-python-3-9"),

    # Minimal case: strips 'rocm' prefix if present?
    # Bash logic: 'rocm-jupyter-minimal' -> 'jupyter-minimal'
    ("rocm-jupyter-minimal-ubi9-python-3.9", "jupyter-minimal-ubi9-python-3-9"),

    # Simple case
    ("jupyter-minimal-ubi9-python-3.9", "jupyter-minimal-ubi9-python-3-9"),
])
def test_get_app_label(target, expected_label):
    assert NotebookLogic.get_app_label(target) == expected_label


@pytest.mark.parametrize("target, expected_flavor", [
    ("jupyter-ubi9-python-3.9", "python-3.9"),
    ("cuda-jupyter-tensorflow-ubi9-python-3.11", "python-3.11"),
    # Case where input might already use dashes (makefile behavior varies)
    ("jupyter-ubi9-python-3-9", "python-3-9"),
])
def test_get_python_flavor(target, expected_flavor):
    assert NotebookLogic.get_python_flavor(target) == expected_flavor


class TestNotebookAppLabel:

    @pytest.mark.parametrize("target, expected_label", [
        # 1. Standard Case: No prefixes, dots replaced by dashes
        # Bash: tr '.' '-'
        ("jupyter-ubi9-python-3.9", "jupyter-ubi9-python-3-9"),

        # 2. CUDA Prefix: Stripped completely
        # Bash: test_target#'cuda-'
        ("cuda-jupyter-tensorflow-ubi9-python-3.9", "jupyter-tensorflow-ubi9-python-3-9"),

        # 3. Pytorch (No cuda prefix in input, but logic should handle it normally)
        ("jupyter-pytorch-ubi9-python-3.9", "jupyter-pytorch-ubi9-python-3-9"),

        # 4. ROCm Reordering: 'rocm-jupyter' becomes 'jupyter-rocm'
        # Bash case: $rocm_target_prefix*) notebook_name=jupyter-rocm...
        ("rocm-jupyter-tensorflow-ubi9-python-3.9", "jupyter-rocm-tensorflow-ubi9-python-3-9"),

        # 5. Minimal Edge Case: 'minimal' notebooks strip the 'rocm' prefix entirely
        # Bash case: *$jupyter_minimal_notebook_id*) ... strips up to 'jupyter'
        ("rocm-jupyter-minimal-ubi9-python-3.9", "jupyter-minimal-ubi9-python-3-9"),
        ("cuda-jupyter-minimal-ubi9-python-3.9", "jupyter-minimal-ubi9-python-3-9"),

        # 6. Dot Replacement check
        ("jupyter.notebook.with.dots", "jupyter-notebook-with-dots"),
    ])
    def test_get_app_label(self, target, expected_label):
        """
        Tests the conversion of the makefile target name to the Kubernetes App Label.
        """
        assert NotebookLogic.get_app_label(target) == expected_label

    @pytest.mark.parametrize("target, expected_flavor", [
        # Bash logic: python_flavor="python-${test_target//*-python-/}"
        # It essentially extracts the version at the end and prepends 'python-'

        ("jupyter-ubi9-python-3.9", "python-3.9"),
        ("cuda-jupyter-tensorflow-ubi9-python-3.11", "python-3.11"),

        # If the input already has dashes in the version (rare but possible in k8s labels)
        ("jupyter-ubi9-python-3-9", "python-3-9"),
    ])
    def test_get_python_flavor(self, target, expected_flavor):
        assert NotebookLogic.get_python_flavor(target) == expected_flavor


from pathlib import Path

REPO_ROOT = Path("/mock/repo")


class TestNotebookPaths:

    # --- Notebook Directory Tests ---
    @pytest.mark.parametrize("nb_id, os_flavor, py_flavor, subpath, expected", [
        ("minimal", "ubi9", "python-3.9", "", "/mock/repo/jupyter/minimal/ubi9-python-3.9"),
        ("minimal", "ubi9", "python-3.9", "test", "/mock/repo/jupyter/minimal/ubi9-python-3.9/test"),
        ("tensorflow", "ubi9", "python-3.11", "", "/mock/repo/jupyter/tensorflow/ubi9-python-3.11"),
    ])
    def test_get_notebook_dir(self, nb_id, os_flavor, py_flavor, subpath, expected):
        result = NotebookLogic.get_notebook_dir(REPO_ROOT, nb_id, os_flavor, py_flavor, subpath)
        assert result == Path(expected)

    # --- Source of Truth (Imagestream) Tests ---
    # These mimic the complex case statement in _get_source_of_truth_filepath

    @pytest.mark.parametrize("notebook_id, accelerator, expected_filename", [
        # Case 1: Minimal (standard)
        ("minimal", "", "jupyter-minimal-notebook-imagestream.yaml"),
        # Case 1b: Minimal with GPU (rare, but logic supports it)
        ("minimal", "cuda", "jupyter-minimal-gpu-notebook-imagestream.yaml"),
        ("minimal", "rocm", "jupyter-rocm-minimal-notebook-imagestream.yaml"),

        # Case 2: Datascience / TrustyAI (No special gpu/cuda prefix handling in filename usually)
        ("datascience", "", "jupyter-datascience-notebook-imagestream.yaml"),
        ("datascience", "cuda", "jupyter-datascience-notebook-imagestream.yaml"),  # Ignores accelerator in name
        ("trustyai", "", "jupyter-trustyai-notebook-imagestream.yaml"),

        # Case 3: PyTorch / TensorFlow
        # Standard
        ("pytorch", "", "jupyter-pytorch-notebook-imagestream.yaml"),
        # CUDA specific: filename changes to just 'jupyter-{id}' usually?
        # Wait, let's look at bash logic:
        # if [ "${accelerator_flavor}" = 'cuda' ]; then filename="jupyter-${notebook_id}-${file_suffix}"
        ("pytorch", "cuda", "jupyter-pytorch-notebook-imagestream.yaml"),

        # ACTUALLY - checking bash logic again:
        # case pytorch/tensorflow:
        #   filename="jupyter-${accelerator_flavor:+"$accelerator_flavor"-}${notebook_id}-${file_suffix}"
        #   if [ "${accelerator_flavor}" = 'cuda' ]; then filename="jupyter-${notebook_id}-${file_suffix}" fi

        # So for cuda+pytorch, it effectively strips 'cuda-' from the filename, resulting in jupyter-pytorch-...
        ("pytorch", "cuda", "jupyter-pytorch-notebook-imagestream.yaml"),
        ("tensorflow", "cuda", "jupyter-tensorflow-notebook-imagestream.yaml"),

        # ROCm case for pytorch/tensorflow
        ("pytorch", "rocm", "jupyter-rocm-pytorch-notebook-imagestream.yaml"),
        ("tensorflow", "rocm", "jupyter-rocm-tensorflow-notebook-imagestream.yaml"),
    ])
    def test_get_source_of_truth_filepath(self, notebook_id, accelerator, expected_filename):
        expected_path = REPO_ROOT / "manifests/base" / expected_filename
        assert NotebookLogic.get_source_of_truth_path(REPO_ROOT, notebook_id, accelerator) == expected_path


class TestNotebookData:

    def test_merge_version_data_adds_hardcoded_tools(self):
        # Input mimics the output of the first yq command in the bash script
        # which merges software and python-dependencies annotations
        input_json = json.dumps({
            "python": "3.9",
            "pip": "21.0"
        })

        result = NotebookLogic.merge_version_data(input_json)
        data = json.loads(result)

        # Verify original data is preserved
        assert data["python"] == "3.9"
        # Verify hardcoded tools are added
        assert data["nbdime"] == "4.0"
        assert data["nbgitpuller"] == "1.2"

    def test_merge_version_data_handles_empty_input(self):
        result = NotebookLogic.merge_version_data("")
        data = json.loads(result)
        assert data["nbdime"] == "4.0"

    def test_merge_version_data_handles_bad_json(self):
        # Should likely fail gracefully or return just defaults
        result = NotebookLogic.merge_version_data("{bad_json")
        data = json.loads(result)
        assert data["nbdime"] == "4.0"

    @pytest.mark.parametrize("pod_name, accelerator, expected_id", [
        ("jupyter-minimal-abcde", "", "minimal"),
        ("jupyter-datascience-12345", "", "datascience"),
        ("jupyter-trustyai-xyz", "", "trustyai"),
        # Logic for tensorflow/pytorch often involves accelerator prefixes in ID
        ("jupyter-tensorflow-pod", "cuda", "cuda/tensorflow"),
        ("jupyter-pytorch-pod", "rocm", "rocm/pytorch"),
        ("jupyter-pytorch-pod", "", "pytorch"),  # If no accelerator detected
    ])
    def test_determine_notebook_id_from_pod(self, pod_name, accelerator, expected_id):
        assert NotebookLogic.determine_notebook_id_from_pod(pod_name, accelerator) == expected_id

    @pytest.mark.parametrize("nb_id, expected", [
        ("datascience", True),
        ("trustyai", True),
        ("tensorflow", True),
        ("pytorch", True),
        ("minimal", False),
        ("cuda/tensorflow", True),  # Should handle prefixes if logic allows
    ])
    def test_is_datascience_derived(self, nb_id, expected):
        assert NotebookLogic.is_datascience_derived(nb_id) is expected


def test_determine_notebook_id_handles_rocm_positioning():
    # In bash: *tensorflow* matches regardless of prefix
    # Your previous split("-")[1] logic would return "rocm" here, which is wrong.
    pod_name = "jupyter-rocm-tensorflow-58b6f7d56-xlk2w"
    assert NotebookLogic.determine_notebook_id_from_pod(pod_name, "rocm") == "rocm/tensorflow"


def test_is_datascience_derived_is_strict():
    # Bash script has an explicit list. "minimal" is false, but "random-new-thing" should also be false.
    assert NotebookLogic.is_datascience_derived("cuda/tensorflow") is True
    assert NotebookLogic.is_datascience_derived("minimal") is False
    assert NotebookLogic.is_datascience_derived("unknown-image") is False


class TestK8sShell:

    # def test_wait_for_workload(self):
    #
    #     shell = K8sShell.create_null()
    #     tracker = shell.track_commands()
    #     shell.wait_for_workload("my-app")
    #
    #     assert tracker.data == [
    #         ['kubectl', 'wait', '--for=condition=ready', 'pod', '-l', 'app=my-app', '--timeout=600s']
    #     ]

    def test_get_pod_name(self):

        target_pod = k8s_models.Pod(
            metadata=k8s_models.ObjectMeta(
                name="found-me-123",
                labels={"app": "target-app", "env": "prod"}
            )
        )

        # 1. Configurable Responses
        # We configure the stub to return a specific stdout when it sees the "get pods" command

        # {
        #     "kubectl get pods -l app=my-app -o jsonpath={.items[0].metadata.name}": {
        #         "stdout": "jupyter-minimal-xyz123"
        #     }
        # })

        shell = K8sShell.create_null(responses="jupyter-minimal-xyz123")

        tracker = shell.track_commands()
        pod_name = shell.get_pod_name(label="my-app")
        assert pod_name == "jupyter-minimal-xyz123"

        assert tracker.data == [
            ['kubectl', 'get', 'pods', '-l', 'app=my-app', '-o', 'jsonpath={.items[0].metadata.name}']
        ]

    def test_get_pod_name2(self):
        shell = K8sShell.create_null(responses="jupyter-minimal-xyz123")
        tracker = shell.track_commands()
        pod = shell.get_pod_name("my-app")

        assert pod == "jupyter-minimal-xyz123"
        assert tracker.data == [[
            "kubectl", "get", "pods", "-l", "app=my-app",
            "-o", "jsonpath={.items[0].metadata.name}"
        ]]


    @staticmethod
    def _kubectl_exec_cmd(cmd: str) -> list[str]:
        return ['kubectl', 'exec', 'my-pod', '--', '/bin/sh', '-c', cmd]

    def test_exec_papermill_success(self):
        # In the script logic, grep returning 1 means "FAILED string NOT found" -> Success
        shell = K8sShell.create_null(responses=[
            "",
            subprocess.CalledProcessError(1, None, None, None),
            "test PASSED",
        ])
        tracker = shell.track_commands()

        shell.exec_papermill_test("my-pod", "test.ipynb", "out_prefix")

        assert tracker.data == [
            self._kubectl_exec_cmd("export IPY_KERNEL_LOG_LEVEL=DEBUG; python3 -m papermill test.ipynb out_prefix_output.ipynb --kernel python3 --log-level DEBUG --stderr-file out_prefix_error.txt"),
            self._kubectl_exec_cmd("grep FAILED out_prefix_error.txt"),
        ]

        # We verify both the papermill command AND the grep command were issued
        assert len(tracker.data) == 2
        assert "papermill" in tracker.data[0][-1] # The last arg of the first command
        assert "grep FAILED" in tracker.data[1][-1]

        assert shell.get_exit_code() is None

    def test_exec_papermill_success2(self):
        shell = K8sShell.create_null(responses=[
            "",
            subprocess.CalledProcessError(1, None, None, None),
            "test PASSED",
        ])
        tracker = shell.track_commands()

        # Mock grep returning 1 (meaning "FAILED" was NOT found, which implies success in this script's logic)
        # The script: grep FAILED ...; case "$?" in 1) success ;;

        # This test ensures we run the papermill command, then the check command
        shell.exec_papermill_test("my-pod", "test.ipynb", "out_prefix")

        # Verify papermill invocation
        papermill_call = tracker.data[0]  # Second to last call
        grep_call = tracker.data[1]  # Last call

        assert "papermill" in papermill_call[6]  # The command string is index 4 in ["kubectl", "exec", ..., "--", "cmd"]
        assert "grep FAILED" in grep_call[6]


    def test_exec_papermill_failure(self):
        # In the script logic, grep returning 0 means "FAILED string FOUND" -> Script Error
        shell = K8sShell.create_null(responses=[
            subprocess.CalledProcessError(1, None, None, None),
            "FAILED",
            "test FAILED",
        ])

        tracker = shell.track_commands()
        shell.exec_papermill_test("my-pod", "test.ipynb", "out_prefix")

        assert tracker.data == [
            self._kubectl_exec_cmd("export IPY_KERNEL_LOG_LEVEL=DEBUG; python3 -m papermill test.ipynb out_prefix_output.ipynb --kernel python3 --log-level DEBUG --stderr-file out_prefix_error.txt"),
            self._kubectl_exec_cmd("grep FAILED out_prefix_error.txt"),
            self._kubectl_exec_cmd("cat out_prefix_error.txt"),
        ]

        # We expect the script to exit(1) if it finds the FAILED string
        assert shell.get_exit_code() == 1

    def test_wait_for_workload(self):
        shell = K8sShell.create_null(responses="")
        tracker = shell.track_commands()
        shell.wait_for_workload("my-app")

        # Verify strict kubectl command structure from bash script
        assert tracker.data == [[
            "kubectl", "wait", "--for=condition=ready", "pod",
            "-l", "app=my-app", "--timeout=600s"
        ]]


    def test_copy_to_pod(self):
        shell = K8sShell.create_null(responses="")
        tracker = shell.track_commands()
        shell.copy_to_pod("my-pod", "src/file.txt", "./dest.txt")

        assert tracker.data == [["kubectl", "cp", "src/file.txt", "my-pod:./dest.txt"]]

### kwok tests

# Only run if kwok is available or explicitly requested
@pytest.mark.integration
def test_get_pod_name_real_integration(kwok_cluster):
    """
    Verifies that K8sShell.get_pod_name works against a real K8s API (KWOK).
    """
    unique_label = f"test-run-{uuid.uuid4()}"
    pod_name = f"test-pod-{uuid.uuid4()}"

    # 1. SETUP: Create a real Pod object in the fake cluster
    # We use kubectl directly to seed the state
    manifest = f"""
apiVersion: v1
kind: Pod
metadata:
  name: {pod_name}
  labels:
    app: {unique_label}
spec:
  containers:
  - name: box
    image: busybox
    command: ["sleep", "3600"]
    """
    subprocess.run(["kubectl", "apply", "-f", "-"], input=manifest, text=True, check=True)

    try:
        # 2. EXECUTE: Use the REAL shell (no mocks!)
        # This sends "kubectl get pods -l app=..." to the KWOK API server
        shell = K8sShell.create()
        result = shell.get_pod_name(unique_label)

        # 3. VERIFY: Did we get the name back?
        assert result == pod_name

    finally:
        subprocess.run(
            ["kubectl", "delete", "pod", pod_name, "--grace-period=0", "--force"],
            capture_output=True
        )

@pytest.mark.integration
def test_wait_for_workload_real_integration(kwok_cluster):
    """
    Verifies wait logic. Note: KWOK pods simulate 'Running' state quickly
    but might need extra config to show 'Ready' condition automatically.
    """
    unique_label = f"wait-test-{uuid.uuid4()}"
    pod_name = f"wait-pod-{uuid.uuid4()}"

    try:
        # KWOK automatically simulates Node assignment and "Fake" running
        # We create a pod that KWOK will pick up
        subprocess.run(
            ["kubectl", "run", pod_name, "--image=busybox", f"--labels=app={unique_label}"],
            check=True
        )

        # We manually patch the status to Ready because KWOK default stages
        # might not set the specific Ready condition instantly without config.
        # This proves our 'kubectl wait' command syntax is correct and can parse the condition.

        # patch = '{"status": {"conditions": [{"type": "Ready", "status": "False"}]}}'
        # subprocess.run(
        #     ["kubectl", "patch", "pod", pod_name, "--subresource=status", "--type=merge", "-p", patch],
        #     check=True
        # )

        shell = K8sShell.create()
        shell.wait_for_workload(unique_label, timeout_sec=10)

    finally:
        subprocess.run(["kubectl", "delete", "pod", pod_name], capture_output=True)

def test_run_main(kwok_cluster):
    subprocess.run(["kubectl", "apply", "-k", "/Users/jdanek/IdeaProjects/notebooks/jupyter/datascience/ubi9-python-3.12/kustomize/base"],
                   text=True, check=True)
    notebook_runner.main(_sys=notebook_runner._StubbedSys(argv=["notebook_runner.py", "jupyter-datascience-ubi9-python-3.12"]))

def run_kubectl(args):
    """Helper to run setup commands directly."""
    import subprocess
    subprocess.run(f"kubectl {args}", shell=True, check=True)

