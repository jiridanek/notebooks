"""Hatchling custom build hook for odh-codeserver.

Drives the code-server npm build pipeline during `pip wheel` / `pip install`,
producing a wheel that contains the release-standalone tree. AIPCC's fromager
calls `pip wheel` via the standard PEP 517 interface, so this hook is invoked
automatically with no fromager-specific configuration.

Two build modes are supported:

1. **Hermetic (Konflux / cachi2)**: all npm deps are prefetched at
   ``/cachi2/output/deps/npm/``.  ``npm ci --offline`` is used.
2. **Non-hermetic (fromager selfservice / local dev)**: npm deps are fetched
   from the network.  ``npm ci`` is used (without ``--offline``).

The mode is auto-detected by checking for the ``/cachi2/output`` directory
or the ``HERMETO_OUTPUT`` environment variable.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


CODESERVER_VERSION = "v4.106.3"


class CustomBuildHook(BuildHookInterface):
    """Build hook that compiles code-server and packs the result into the wheel."""

    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return

        root = Path(self.root)
        source_code, source_prefetch = self._locate_sources(root)

        hermetic = self._is_hermetic()

        self._log(f"code-server version : {CODESERVER_VERSION}")
        self._log(f"source_code         : {source_code}")
        self._log(f"source_prefetch     : {source_prefetch}")
        self._log(f"hermetic            : {hermetic}")
        self._log(f"platform            : {platform.machine()}")

        self._run_apply_patch(source_code, source_prefetch)

        if hermetic:
            self._run_setup_offline(source_code, source_prefetch)
            self._run_npm_ci_offline(source_code, source_prefetch)
        else:
            self._run_npm_ci_online(source_prefetch)

        self._run_npm_build(source_code, source_prefetch)
        self._run_npm_build_vscode(source_code, source_prefetch)
        self._run_npm_release(source_code, source_prefetch)
        self._run_npm_release_standalone(source_code, source_prefetch)

        data_dir = root / "odh_codeserver" / "data"
        self._copy_release_standalone(source_prefetch, data_dir)

        self._set_platform_tag(build_data)

    # ------------------------------------------------------------------
    # Source location helpers
    # ------------------------------------------------------------------

    def _locate_sources(self, root: Path) -> tuple[Path, Path]:
        """Return (source_code, source_prefetch) paths.

        In the Dockerfile these are set by ENV vars.  When building as a
        Python package the layout depends on whether we are inside the
        notebooks repo tree or building from a standalone sdist.
        """
        env_code = os.environ.get("CODESERVER_SOURCE_CODE")
        env_prefetch = os.environ.get("CODESERVER_SOURCE_PREFETCH")

        if env_code and env_prefetch:
            return Path(env_code), Path(env_prefetch)

        # In-tree build: odh-codeserver sits next to ubi9-python-3.12
        sibling = root.parent / "ubi9-python-3.12"
        if sibling.is_dir():
            source_code = sibling
            source_prefetch = sibling / "prefetch-input" / "code-server"
            return source_code, source_prefetch

        raise FileNotFoundError(
            "Cannot locate code-server sources. Set CODESERVER_SOURCE_CODE "
            "and CODESERVER_SOURCE_PREFETCH environment variables, or build "
            "from within the notebooks repository tree."
        )

    @staticmethod
    def _is_hermetic() -> bool:
        hermeto = os.environ.get("HERMETO_OUTPUT", "/cachi2/output")
        return Path(hermeto).is_dir()

    # ------------------------------------------------------------------
    # Build steps (mirror the Dockerfile RUN commands)
    # ------------------------------------------------------------------

    def _run_apply_patch(self, source_code: Path, source_prefetch: Path) -> None:
        """Overlay patches and run apply-patch.sh."""
        self._log("Applying patches ...")

        patches_dir = source_code / "prefetch-input" / "patches"
        version_overlay = patches_dir / f"code-server-{CODESERVER_VERSION}"
        if version_overlay.is_dir():
            self._log(f"Overlaying {version_overlay} onto {source_prefetch}")
            shutil.copytree(version_overlay, source_prefetch, dirs_exist_ok=True)

        target_patches = source_code / "patches"
        target_patches.mkdir(parents=True, exist_ok=True)
        for script in ("setup-offline-binaries.sh", "codeserver-offline-env.sh", "tweak-gha.sh"):
            src = patches_dir / script
            if src.exists():
                shutil.copy2(src, target_patches / script)

        apply_script = patches_dir / "apply-patch.sh"
        if apply_script.exists():
            shutil.copy2(apply_script, source_code / "apply-patch.sh")

        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f"cd {source_code} && bash ./apply-patch.sh",
            env=env,
        )

    def _run_setup_offline(self, source_code: Path, source_prefetch: Path) -> None:
        """Run setup-offline-binaries.sh (hermetic mode only)."""
        self._log("Running setup-offline-binaries.sh ...")
        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f"cd {source_code} && source ./patches/setup-offline-binaries.sh",
            env=env,
        )

    def _run_npm_ci_offline(self, source_code: Path, source_prefetch: Path) -> None:
        self._log("npm ci --offline ...")
        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f"cd {source_code} && "
            f"source ./patches/setup-offline-binaries.sh && "
            f"cd {source_prefetch} && "
            f"CI=1 npm ci --offline",
            env=env,
        )

    def _run_npm_ci_online(self, source_prefetch: Path) -> None:
        self._log("npm ci (non-hermetic, with network) ...")
        self._shell(f"cd {source_prefetch} && npm ci")

    def _run_npm_build(self, source_code: Path, source_prefetch: Path) -> None:
        self._log("npm run build ...")
        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f". {source_code}/patches/codeserver-offline-env.sh && "
            f"cd {source_prefetch} && npm run build",
            env=env,
        )

    def _run_npm_build_vscode(self, source_code: Path, source_prefetch: Path) -> None:
        version = CODESERVER_VERSION.lstrip("v")
        self._log(f"npm run build:vscode (VERSION={version}) ...")
        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f". {source_code}/patches/codeserver-offline-env.sh && "
            f"cd {source_prefetch} && VERSION={version} npm run build:vscode",
            env=env,
        )

    def _run_npm_release(self, source_code: Path, source_prefetch: Path) -> None:
        self._log("npm run release ...")
        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f". {source_code}/patches/codeserver-offline-env.sh && "
            f"export KEEP_MODULES=1 && cd {source_prefetch} && npm run release",
            env=env,
        )

    def _run_npm_release_standalone(self, source_code: Path, source_prefetch: Path) -> None:
        self._log("npm run release:standalone ...")
        env = self._build_env(source_code, source_prefetch)
        self._shell(
            f". {source_code}/patches/codeserver-offline-env.sh && "
            f"export KEEP_MODULES=1 && cd {source_prefetch} && npm run release:standalone",
            env=env,
        )

    # ------------------------------------------------------------------
    # Post-build: copy artefacts into the wheel tree
    # ------------------------------------------------------------------

    def _copy_release_standalone(self, source_prefetch: Path, data_dir: Path) -> None:
        """Copy release-standalone/ into odh_codeserver/data/ for the wheel."""
        release_dir = source_prefetch / "release-standalone"
        if not release_dir.is_dir():
            raise FileNotFoundError(
                f"release-standalone not found at {release_dir}. "
                "The npm build may have failed."
            )

        self._log(f"Copying {release_dir} -> {data_dir}")
        if data_dir.exists():
            shutil.rmtree(data_dir)
        shutil.copytree(release_dir, data_dir, symlinks=True)

        # Also copy the wrapper script that goes to /usr/bin/code-server
        nfpm_script = source_prefetch / "ci" / "build" / "code-server-nfpm.sh"
        if nfpm_script.exists():
            dest = data_dir / "bin" / "code-server-wrapper.sh"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(nfpm_script, dest)

        self._fix_permissions(data_dir)

    @staticmethod
    def _fix_permissions(data_dir: Path) -> None:
        """Ensure key binaries have executable permission."""
        executables = [
            data_dir / "bin" / "code-server",
            data_dir / "bin" / "code-server-wrapper.sh",
            data_dir / "lib" / "node",
        ]
        for exe in executables:
            if exe.exists():
                exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # ------------------------------------------------------------------
    # Platform tag
    # ------------------------------------------------------------------

    @staticmethod
    def _set_platform_tag(build_data: dict) -> None:
        """Set wheel platform tag to manylinux_2_28_{arch}."""
        machine = platform.machine()
        arch_map = {
            "x86_64": "x86_64",
            "aarch64": "aarch64",
            "ppc64le": "ppc64le",
            "s390x": "s390x",
        }
        arch = arch_map.get(machine, machine)
        tag = f"manylinux_2_28_{arch}"
        build_data["tag"] = f"py3-none-{tag}"
        build_data["pure_python"] = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_env(self, source_code: Path, source_prefetch: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["CODESERVER_SOURCE_CODE"] = str(source_code)
        env["CODESERVER_SOURCE_PREFETCH"] = str(source_prefetch)
        env.setdefault("HOME", "/root")
        return env

    def _shell(self, cmd: str, *, env: dict[str, str] | None = None) -> None:
        self._log(f"  $ {cmd[:120]}{'...' if len(cmd) > 120 else ''}")
        result = subprocess.run(
            ["bash", "-c", cmd],
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed (exit {result.returncode}): {cmd[:200]}"
            )

    def _log(self, msg: str) -> None:
        sys.stderr.write(f"[odh-codeserver] {msg}\n")
        sys.stderr.flush()
