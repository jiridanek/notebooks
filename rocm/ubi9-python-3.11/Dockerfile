# Install ROCm AMD from:
# https://github.com/ROCm/ROCm-docker/blob/master/dev/Dockerfile-centos-7-complete
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG SOURCE_CODE=rocm/ubi9-python-3.11

LABEL name="odh-notebook-rocm-python-3.11" \
      summary="ROCm Python 3.11 base image for ODH notebooks" \
      description="ROCm Python 3.11 builder image based on UBI9 for ODH notebooks" \
      io.k8s.display-name="ROCm Python 3.11 base image for ODH notebooks" \
      io.k8s.description="ROCm Python 3.11 builder image based on UBI9 for ODH notebooks" \
      authoritative-source-url="https://github.com/opendatahub-io/notebooks" \
      io.openshift.build.commit.ref="main" \
      io.openshift.build.source-location="https://github.com/opendatahub-io/notebooks/tree/main/rocm/ubi9-python-3.11" \
      io.openshift.build.image="quay.io/opendatahub/workbench-images:rocm-ubi9-python-3.11"

USER 0
WORKDIR /opt/app-root/bin

# Please keep in sync with ROCm/python3.11 dependent images
ARG ROCM_VERSION=6.1
ARG AMDGPU_VERSION=6.1

# Enable epel-release repositories

# Install the ROCm rpms
RUN echo "[ROCm]" > /etc/yum.repos.d/rocm.repo && \
    echo "name=ROCm" >> /etc/yum.repos.d/rocm.repo && \
    echo "baseurl=https://repo.radeon.com/rocm/rhel9/$ROCM_VERSION/main" >> /etc/yum.repos.d/rocm.repo && \
    echo "enabled=1" >> /etc/yum.repos.d/rocm.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/rocm.repo && \
    echo "[amdgpu]" > /etc/yum.repos.d/amdgpu.repo && \
    echo "name=amdgpu" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "baseurl=https://repo.radeon.com/amdgpu/$AMDGPU_VERSION/rhel/9.4/main/x86_64" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "enabled=1" >> /etc/yum.repos.d/amdgpu.repo && \
    echo "gpgcheck=0" >> /etc/yum.repos.d/amdgpu.repo && \
    yum install -y rocm && \
    yum clean all && rm -rf /var/cache/yum

# Restore notebook user workspace
USER 1001
WORKDIR /opt/app-root/src
