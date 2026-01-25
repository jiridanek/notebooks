import pathlib
from typing import Generator

import pytest
import subprocess
import time
import os

# from kubernetes import config, client

CLUSTER_NAME = "pytest-kwok-cluster"

# need a brew install kwok instruction, and some linux steps

@pytest.fixture(scope="session")
def kwok_cluster() -> Generator[str]:
    """
    Spins up a KWOK cluster for the duration of the test session.
    """

    # Set env var so the python client picks it up automatically if we want
    kubeconfig_path = "/Users/jdanek/IdeaProjects/notebooks/kubeconfig"
    os.environ["KUBECONFIG"] = kubeconfig_path

    existing = subprocess.run(
        ["kwokctl", "get", "clusters", f"--name={CLUSTER_NAME}"],
        stdout=subprocess.PIPE, text=True
    )

    if not CLUSTER_NAME in existing.stdout.splitlines():
        print(f"\n🚀 Creating KWOK cluster: {CLUSTER_NAME}...")

        # 1. Create the cluster
        # Error response from daemon: bad parameter: link is not supported
        try:
            subprocess.run(
                ["kwokctl", "create", "cluster",
                 "--runtime=binary",
                 f"--name={CLUSTER_NAME}",
                 #
                 # "--wait=all",
                 f"--kubeconfig={kubeconfig_path}",
                 ],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error creating KWOK cluster: {e.stderr.decode()}")
            raise e

        # subprocess.run(
        #     ["kwokctl", "delete", "cluster", f"--name={CLUSTER_NAME}"],
        #     stdout=subprocess.DEVNULL,
        #     stderr=subprocess.DEVNULL,
        #     check=False
        # )
    else:
        print(existing.stdout.strip())

    # zero nodes by default in a new cluster
    try:
        subprocess.run(
            ["kwokctl", "scale", "node", "--replicas=1",
             f"--name={CLUSTER_NAME}"],
            check=True,
            capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error scaling KWOK cluster: {e.stderr.decode()}")
        raise e

    # this returns the content, not the path!

    # 2. Export the kubeconfig to a temporary file or environment variable
    # KWOK usually merges into ~/.kube/config, but for isolation we can grab the context
    # or just let it use default if you are okay with it modifying your global config.
    # A cleaner way for CI/Tests is asking kwok for the kubeconfig path:
    kubeconfig_path = subprocess.check_output(
        ["kwokctl", "get", "kubeconfig", "--name", CLUSTER_NAME],
        text=True
    ).strip()

    # Wait for the control plane to be responsive (usually instant with KWOK)
    # We can do a quick check-loop here if needed, but KWOK is synchronous.

    # Error from server (Forbidden): pods "my-test-pod" is forbidden: error looking up service account default/default: serviceaccount "default" not found
    # there seems to be a startup race before the default service account in the default namespace is created
    print("⏳ Waiting for default ServiceAccount...")
    # run_kubectl(f"wait --for=create serviceaccount/default --timeout=10s")
    subprocess.run(
        "until kubectl get serviceaccount default >/dev/null 2>&1; do sleep 1; done",
        shell=True,
        check=True,
        timeout=30,
    )
    print("✅ default ServiceAccount is ready")

    yield kubeconfig_path

    if "CI" in os.environ:
        print(f"\n🧹 Deleting KWOK cluster: {CLUSTER_NAME}...")
        subprocess.run(
            ["kwokctl", "delete", "cluster", "--name", CLUSTER_NAME],
            check=True,
            capture_output=True
        )
    else:
        print(f"\n🧹 Letting KWOK cluster run: {CLUSTER_NAME}...")

# @pytest.fixture(scope="session")
# def k8s_client(kwok_cluster):
#     """
#     Returns a configured Kubernetes client connected to the KWOK cluster.
#     """
#     # Load config from the file path returned by the cluster fixture
#     config.load_kube_config(config_file=kwok_cluster)
#     return client.CoreV1Api()
#
# @pytest.fixture(scope="session")
# def k8s_apps_client(kwok_cluster):
#     """
#     Returns a configured AppsV1 client (for Deployments/StatefulSets).
#     """
#     config.load_kube_config(config_file=kwok_cluster)
#     return client.AppsV1Api()
