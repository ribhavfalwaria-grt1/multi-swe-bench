import re
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


_KNOWN_SUBLIBS = {
    "storage",
    "bigtable",
    "spanner",
    "pubsub",
    "bigquery",
    "iam",
    "logging",
}


def _detect_sublibs(pr: PullRequest) -> str:
    """Return a comma-separated list of GOOGLE_CLOUD_CPP_ENABLE values
    derived from the files touched by fix_patch + test_patch."""
    sublibs: set[str] = set()
    for patch in (pr.fix_patch, pr.test_patch):
        for line in patch.splitlines():
            if not line.startswith("diff --git"):
                continue
            path = line.split(" b/")[-1]
            parts = path.split("/")
            # google/cloud/<sublib>/...
            if len(parts) >= 4 and parts[0] == "google" and parts[1] == "cloud":
                candidate = parts[2]
                if candidate in _KNOWN_SUBLIBS:
                    sublibs.add(candidate)

    if not sublibs:
        # Fallback: build the defaults that cover common/internal
        return "storage,bigtable,spanner,pubsub"

    return ",".join(sorted(sublibs))


def _detect_test_targets(pr: PullRequest) -> list[str]:
    """Return list of *_test basenames from test_patch (without .cc)."""
    targets: list[str] = []
    for line in pr.test_patch.splitlines():
        if line.startswith("diff --git"):
            path = line.split(" b/")[-1]
            fname = path.split("/")[-1]
            if fname.endswith("_test.cc"):
                name = fname[:-3]  # strip .cc
                if name not in targets:
                    targets.append(name)
    return targets


# ===========================================================================
# Base Image — installs OS packages + builds all heavy C++ deps from source.
#
# Dependency chain (built from source on Ubuntu 22.04):
#   abseil-cpp -> protobuf -> gRPC -> google-cloud-cpp
# Plus: nlohmann-json, libcurl, openssl, c-ares, re2
#
# We pin compatible versions that work across the 2020-2025 PR range.
# ===========================================================================
class GoogleCloudCppImageBase(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Union[str, "Image"]:
        return "ubuntu:22.04"

    def image_tag(self) -> str:
        return "base"

    def workdir(self) -> str:
        return "base"

    def files(self) -> list[File]:
        return []

    def dockerfile(self) -> str:
        image_name = self.dependency()
        if isinstance(image_name, Image):
            image_name = image_name.image_full_name()

        if self.config.need_clone:
            code = (
                f"RUN git clone https://github.com/{self.pr.org}/{self.pr.repo}.git"
                f" /home/{self.pr.repo}"
            )
        else:
            code = f"COPY {self.pr.repo} /home/{self.pr.repo}"

        return f"""FROM {image_name}

{self.global_env}

WORKDIR /home/
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# ── OS packages ──────────────────────────────────────────────────────────
RUN apt-get update && apt-get --no-install-recommends install -y \\
        apt-transport-https apt-utils automake build-essential \\
        ca-certificates cmake curl git gcc g++ \\
        libc-ares-dev libc-ares2 libcurl4-openssl-dev libre2-dev \\
        libssl-dev m4 make ninja-build pkg-config tar wget \\
        zlib1g-dev && \\
    rm -rf /var/lib/apt/lists/*

# ── Abseil ───────────────────────────────────────────────────────────────
RUN mkdir -p /tmp/abseil && cd /tmp/abseil && \\
    curl -fsSL https://github.com/abseil/abseil-cpp/archive/20230802.1.tar.gz | \\
        tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release \\
          -DCMAKE_CXX_STANDARD=17 \\
          -DABSL_BUILD_TESTING=OFF \\
          -DBUILD_SHARED_LIBS=yes \\
          -S . -B cmake-out && \\
    cmake --build cmake-out -- -j "$(nproc)" && \\
    cmake --build cmake-out --target install && \\
    ldconfig && rm -rf /tmp/abseil

# ── Protobuf ─────────────────────────────────────────────────────────────
RUN mkdir -p /tmp/protobuf && cd /tmp/protobuf && \\
    curl -fsSL https://github.com/protocolbuffers/protobuf/archive/v25.1.tar.gz | \\
        tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release \\
          -DCMAKE_CXX_STANDARD=17 \\
          -DBUILD_SHARED_LIBS=yes \\
          -Dprotobuf_BUILD_TESTS=OFF \\
          -Dprotobuf_ABSL_PROVIDER=package \\
          -S . -B cmake-out && \\
    cmake --build cmake-out -- -j "$(nproc)" && \\
    cmake --build cmake-out --target install && \\
    ldconfig && rm -rf /tmp/protobuf

# ── nlohmann-json ────────────────────────────────────────────────────────
RUN mkdir -p /tmp/json && cd /tmp/json && \\
    curl -fsSL https://github.com/nlohmann/json/archive/v3.11.3.tar.gz | \\
        tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release \\
          -DBUILD_SHARED_LIBS=yes \\
          -DJSON_BuildTests=OFF \\
          -S . -B cmake-out && \\
    cmake --build cmake-out --target install && \\
    ldconfig && rm -rf /tmp/json

# ── gRPC ─────────────────────────────────────────────────────────────────
RUN mkdir -p /tmp/grpc && cd /tmp/grpc && \\
    curl -fsSL https://github.com/grpc/grpc/archive/v1.60.0.tar.gz | \\
        tar -xzf - --strip-components=1 && \\
    cmake -DCMAKE_BUILD_TYPE=Release \\
          -DCMAKE_CXX_STANDARD=17 \\
          -DBUILD_SHARED_LIBS=yes \\
          -DgRPC_INSTALL=ON \\
          -DgRPC_BUILD_TESTS=OFF \\
          -DgRPC_ABSL_PROVIDER=package \\
          -DgRPC_CARES_PROVIDER=package \\
          -DgRPC_PROTOBUF_PROVIDER=package \\
          -DgRPC_RE2_PROVIDER=package \\
          -DgRPC_SSL_PROVIDER=package \\
          -DgRPC_ZLIB_PROVIDER=package \\
          -S . -B cmake-out && \\
    cmake --build cmake-out -- -j "$(nproc)" && \\
    cmake --build cmake-out --target install && \\
    ldconfig && rm -rf /tmp/grpc

# ── Clone repository ─────────────────────────────────────────────────────
{code}

{self.clear_env}

"""


# ===========================================================================
# PR Image — checks out the base commit, copies patches + shell scripts.
# ===========================================================================
class GoogleCloudCppImageDefault(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> Image:
        return GoogleCloudCppImageBase(self.pr, self._config)

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def files(self) -> list[File]:
        sublibs = _detect_sublibs(self.pr)

        return [
            File(".", "fix.patch", f"{self.pr.fix_patch}"),
            File(".", "test.patch", f"{self.pr.test_patch}"),
            File(
                ".",
                "check_git_changes.sh",
                """\
#!/bin/bash
set -e

if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  echo "check_git_changes: Not inside a git repository"
  exit 1
fi

if [[ -n $(git status --porcelain) ]]; then
  echo "check_git_changes: Uncommitted changes"
  exit 1
fi

echo "check_git_changes: No uncommitted changes"
exit 0
""",
            ),
            File(
                ".",
                "prepare.sh",
                """\
#!/bin/bash
set -e

cd /home/{repo}
git reset --hard
bash /home/check_git_changes.sh
git checkout {sha}
bash /home/check_git_changes.sh

mkdir -p build
""".format(repo=self.pr.repo, sha=self.pr.base.sha),
            ),
            File(
                ".",
                "run.sh",
                """\
#!/bin/bash
set -e

cd /home/{repo}/build
cmake -DCMAKE_BUILD_TYPE=Debug \\
      -DCMAKE_CXX_STANDARD=17 \\
      -DBUILD_TESTING=ON \\
      -DGOOGLE_CLOUD_CPP_ENABLE={sublibs} \\
      -DGOOGLE_CLOUD_CPP_ENABLE_EXAMPLES=OFF \\
      ..
cmake --build . -- -j "$(nproc)"
ctest --output-on-failure
""".format(repo=self.pr.repo, sublibs=sublibs),
            ),
            File(
                ".",
                "test-run.sh",
                """\
#!/bin/bash
set -e

cd /home/{repo}
git apply --whitespace=nowarn /home/test.patch
cd build
cmake -DCMAKE_BUILD_TYPE=Debug \\
      -DCMAKE_CXX_STANDARD=17 \\
      -DBUILD_TESTING=ON \\
      -DGOOGLE_CLOUD_CPP_ENABLE={sublibs} \\
      -DGOOGLE_CLOUD_CPP_ENABLE_EXAMPLES=OFF \\
      ..
cmake --build . -- -j "$(nproc)"
ctest --output-on-failure
""".format(repo=self.pr.repo, sublibs=sublibs),
            ),
            File(
                ".",
                "fix-run.sh",
                """\
#!/bin/bash
set -e

cd /home/{repo}
git apply --whitespace=nowarn /home/test.patch /home/fix.patch
cd build
cmake -DCMAKE_BUILD_TYPE=Debug \\
      -DCMAKE_CXX_STANDARD=17 \\
      -DBUILD_TESTING=ON \\
      -DGOOGLE_CLOUD_CPP_ENABLE={sublibs} \\
      -DGOOGLE_CLOUD_CPP_ENABLE_EXAMPLES=OFF \\
      ..
cmake --build . -- -j "$(nproc)"
ctest --output-on-failure
""".format(repo=self.pr.repo, sublibs=sublibs),
            ),
        ]

    def dockerfile(self) -> str:
        image = self.dependency()
        name = image.image_name()
        tag = image.image_tag()

        copy_commands = ""
        for file in self.files():
            copy_commands += f"COPY {file.name} /home/\n"

        prepare_commands = "RUN bash /home/prepare.sh"

        return f"""FROM {name}:{tag}

{self.global_env}

{copy_commands}

{prepare_commands}

{self.clear_env}

"""


# ===========================================================================
# Instance — orchestrates test runs and parses Google Test / CTest output.
# ===========================================================================
@Instance.register("googleapis", "google-cloud-cpp")
class GoogleCloudCpp(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return GoogleCloudCppImageDefault(self.pr, self._config)

    def run(self, run_cmd: str = "") -> str:
        if run_cmd:
            return run_cmd
        return "bash /home/run.sh"

    def test_patch_run(self, test_patch_run_cmd: str = "") -> str:
        if test_patch_run_cmd:
            return test_patch_run_cmd
        return "bash /home/test-run.sh"

    def fix_patch_run(self, fix_patch_run_cmd: str = "") -> str:
        if fix_patch_run_cmd:
            return fix_patch_run_cmd
        return "bash /home/fix-run.sh"

    def parse_log(self, test_log: str) -> TestResult:
        """Parse CTest + Google Test output.

        CTest output lines look like:
            1/50 Test  #1: storage_client_test ................   Passed    0.42 sec
            2/50 Test  #2: storage_retry_test .................***Failed    0.05 sec

        We also handle the verbose ``ctest --output-on-failure`` summary
        block that lists failed tests::

            The following tests FAILED:
                 2 - storage_retry_test (Failed)
        """
        passed_tests: set[str] = set()
        failed_tests: set[str] = set()
        skipped_tests: set[str] = set()

        # CTest one-liner patterns
        re_pass = re.compile(
            r"^\s*\d+/\d+\s+Test\s+#\d+:\s+(.*?)\s+\.+\s+Passed", re.IGNORECASE
        )
        re_fail = re.compile(
            r"^\s*\d+/\d+\s+Test\s+#\d+:\s+(.*?)\s+\.+\*\*\*(?:Failed|Not Run)",
            re.IGNORECASE,
        )
        re_skip = re.compile(
            r"^\s*\d+/\d+\s+Test\s+#\d+:\s+(.*?)\s+\.+\*\*\*Skipped",
            re.IGNORECASE,
        )
        # Fallback: "The following tests FAILED:" summary block
        re_summary_fail = re.compile(r"^\s+\d+\s+-\s+(.*?)\s+\(Failed\)", re.IGNORECASE)

        in_failed_block = False
        for line in test_log.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            m_pass = re_pass.match(line)
            if m_pass:
                passed_tests.add(m_pass.group(1).strip())
                continue

            m_fail = re_fail.match(line)
            if m_fail:
                failed_tests.add(m_fail.group(1).strip())
                continue

            m_skip = re_skip.match(line)
            if m_skip:
                skipped_tests.add(m_skip.group(1).strip())
                continue

            if "The following tests FAILED:" in line:
                in_failed_block = True
                continue

            if in_failed_block:
                m_sf = re_summary_fail.match(line)
                if m_sf:
                    failed_tests.add(m_sf.group(1).strip())
                elif stripped and not stripped.startswith("Errors while running"):
                    # Still in the block
                    pass
                else:
                    in_failed_block = False

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
