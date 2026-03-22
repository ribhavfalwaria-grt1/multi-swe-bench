import re
from typing import Optional

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest

FILTER_SCRIPT = """\
import sys
import re

patch_file = sys.argv[1]
output_file = sys.argv[2]

with open(patch_file, 'r', errors='replace') as f:
    content = f.read()

starts = [m.start() for m in re.finditer(r'^diff --git ', content, re.MULTILINE)]
parts = []
for i, s in enumerate(starts):
    end = starts[i + 1] if i + 1 < len(starts) else len(content)
    parts.append(content[s:end])

filtered = []
for part in parts:
    if not part.strip():
        continue
    if 'GIT binary patch' in part or 'Binary files' in part:
        continue
    first_line = part.split('\\n')[0]
    if re.search(
        r'\\.(png|jpg|jpeg|gif|ico|bin|woff|woff2|eot|ttf|otf|zip|gz|tar|svg|jar|class|war|ear)$',
        first_line, re.IGNORECASE):
        continue
    filtered.append(part)

with open(output_file, 'w') as f:
    f.write(''.join(filtered))
"""

# Script to remove bintray plugin (causes build failure due to JCenter shutdown)
REMOVE_BINTRAY_SCRIPT = """\
#!/bin/bash
cd /home/testcontainers-java
# Remove bintray plugin references that cause "http-builder:0.7.2 not found"
sed -i '/com.jfrog.bintray/d' build.gradle 2>/dev/null || true
sed -i '/bintray.gradle/d' build.gradle 2>/dev/null || true
sed -i '/bintrayUpload/d' build.gradle 2>/dev/null || true
# Also remove from subproject build files
find . -name "build.gradle" -exec sed -i '/com.jfrog.bintray/d' {} \\; 2>/dev/null || true
find . -name "build.gradle" -exec sed -i '/bintray/d' {} \\; 2>/dev/null || true
"""


class ImageDefault(Image):
    def __init__(self, pr: PullRequest, config: Config):
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    @property
    def config(self) -> Config:
        return self._config

    def dependency(self) -> str:
        return "ubuntu:22.04"

    def image_prefix(self) -> str:
        return "envagent"

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def files(self) -> list[File]:
        repo_name = self.pr.repo
        return [
            File(".", "fix.patch", f"{self.pr.fix_patch}"),
            File(".", "test.patch", f"{self.pr.test_patch}"),
            File(".", "filter_binary_patch.py", FILTER_SCRIPT),
            File(".", "remove_bintray.sh", REMOVE_BINTRAY_SCRIPT),
            File(
                ".",
                "run.sh",
                """#!/bin/bash
cd /home/{repo}
bash /home/remove_bintray.sh
export TESTCONTAINERS_RYUK_DISABLED=true
export TESTCONTAINERS_CHECKS_DISABLE=true
./gradlew :testcontainers:test --no-daemon -x javadoc 2>&1 || true
""".format(repo=repo_name),
            ),
            File(
                ".",
                "test-run.sh",
                """#!/bin/bash
cd /home/{repo}
bash /home/remove_bintray.sh

python3 /home/filter_binary_patch.py /home/test.patch /tmp/test_filtered.patch

if ! git apply --whitespace=nowarn /tmp/test_filtered.patch 2>/dev/null; then
    if ! git apply --whitespace=nowarn --3way /tmp/test_filtered.patch 2>/dev/null; then
        git apply --whitespace=nowarn --reject /tmp/test_filtered.patch 2>/dev/null || true
    fi
fi

export TESTCONTAINERS_RYUK_DISABLED=true
export TESTCONTAINERS_CHECKS_DISABLE=true
./gradlew :testcontainers:test --no-daemon -x javadoc 2>&1 || true
""".format(repo=repo_name),
            ),
            File(
                ".",
                "fix-run.sh",
                """#!/bin/bash
cd /home/{repo}
bash /home/remove_bintray.sh

python3 /home/filter_binary_patch.py /home/test.patch /tmp/test_filtered.patch
python3 /home/filter_binary_patch.py /home/fix.patch /tmp/fix_filtered.patch

if ! git apply --whitespace=nowarn /tmp/test_filtered.patch 2>/dev/null; then
    if ! git apply --whitespace=nowarn --3way /tmp/test_filtered.patch 2>/dev/null; then
        git apply --whitespace=nowarn --reject /tmp/test_filtered.patch 2>/dev/null || true
    fi
fi

if ! git apply --whitespace=nowarn /tmp/fix_filtered.patch 2>/dev/null; then
    if ! git apply --whitespace=nowarn --3way /tmp/fix_filtered.patch 2>/dev/null; then
        git apply --whitespace=nowarn --reject /tmp/fix_filtered.patch 2>/dev/null || true
    fi
fi

export TESTCONTAINERS_RYUK_DISABLED=true
export TESTCONTAINERS_CHECKS_DISABLE=true
./gradlew :testcontainers:test --no-daemon -x javadoc 2>&1 || true
""".format(repo=repo_name),
            ),
        ]

    def dockerfile(self) -> str:
        copy_commands = ""
        for file in self.files():
            copy_commands += f"COPY {file.name} /home/\n"

        dockerfile_content = """\
# syntax=docker/dockerfile:1.6
FROM ubuntu:22.04

ARG TARGETARCH
ARG REPO_URL="https://github.com/{pr.org}/{pr.repo}.git"
ARG BASE_COMMIT
ARG http_proxy=""
ARG https_proxy=""
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG no_proxy="localhost,127.0.0.1,::1"
ARG NO_PROXY="localhost,127.0.0.1,::1"
ARG CA_CERT_PATH="/etc/ssl/certs/ca-certificates.crt"
ARG JDK_PKG="openjdk-8-jdk"

ENV DEBIAN_FRONTEND=noninteractive \\
    LANG=C.UTF-8 \\
    LC_ALL=C.UTF-8 \\
    TZ=UTC \\
    http_proxy=${{http_proxy}} \\
    https_proxy=${{https_proxy}} \\
    HTTP_PROXY=${{HTTP_PROXY}} \\
    HTTPS_PROXY=${{HTTPS_PROXY}} \\
    no_proxy=${{no_proxy}} \\
    NO_PROXY=${{NO_PROXY}} \\
    SSL_CERT_FILE=${{CA_CERT_PATH}} \\
    REQUESTS_CA_BUNDLE=${{CA_CERT_PATH}} \\
    CURL_CA_BUNDLE=${{CA_CERT_PATH}} \\
    JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \\
    TESTCONTAINERS_RYUK_DISABLED=true \\
    TESTCONTAINERS_CHECKS_DISABLE=true

LABEL org.opencontainers.image.title="{pr.org}/{pr.repo}" \\
      org.opencontainers.image.description="{pr.org}/{pr.repo} Docker image" \\
      org.opencontainers.image.source="https://github.com/{pr.org}/{pr.repo}" \\
      org.opencontainers.image.authors="https://www.ethara.ai/"

RUN mkdir -p /etc/pki/tls/certs /etc/pki/ca-trust/extracted/pem /etc/ssl/certs && \\
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt && \\
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem && \\
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/ca-bundle.pem && \\
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/cacert.pem && \\
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem && \\
    ln -sf /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-bundle.crt

RUN apt-get update && apt-get install -y --no-install-recommends \\
    git curl python3 ca-certificates docker.io ${{JDK_PKG}} \\
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-${{TARGETARCH}}
ENV PATH=$JAVA_HOME/bin:$PATH
RUN ln -sf /usr/lib/jvm/java-8-openjdk-$(dpkg --print-architecture) /usr/lib/jvm/java-8-openjdk-${{TARGETARCH}} 2>/dev/null || true

WORKDIR /home/
COPY fix.patch /home/
COPY test.patch /home/
COPY remove_bintray.sh /home/
RUN git clone "${{REPO_URL}}" /home/{pr.repo}

WORKDIR /home/{pr.repo}
RUN git reset --hard
RUN git fetch origin ${{BASE_COMMIT}} 2>/dev/null || git fetch --unshallow 2>/dev/null || true
RUN git checkout ${{BASE_COMMIT}}

RUN bash /home/remove_bintray.sh
RUN ./gradlew --no-daemon dependencies 2>/dev/null || true

{copy_commands}
CMD ["/bin/bash"]
"""
        return dockerfile_content.format(pr=self.pr, copy_commands=copy_commands)


@Instance.register("testcontainers", "testcontainers_java_gradle_jdk8")
class TESTCONTAINERS_JAVA_GRADLE_JDK8(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return ImageDefault(self.pr, self._config)

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

    def volumes(self):
        return {"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}}

    def parse_log(self, test_log: str) -> TestResult:
        passed_tests = set()
        failed_tests = set()
        skipped_tests = set()

        passed_res = [
            re.compile(r"^> Task :(\S+)$"),
            re.compile(r"^> Task :(\S+) UP-TO-DATE$"),
            re.compile(r"^(.+ > .+) PASSED$"),
        ]

        failed_res = [
            re.compile(r"^> Task :(\S+) FAILED$"),
            re.compile(r"^(.+ > .+) FAILED$"),
        ]

        skipped_res = [
            re.compile(r"^> Task :(\S+) SKIPPED$"),
            re.compile(r"^> Task :(\S+) NO-SOURCE$"),
            re.compile(r"^(.+ > .+) SKIPPED$"),
        ]

        for line in test_log.splitlines():
            for passed_re in passed_res:
                m = passed_re.match(line)
                if m and m.group(1) not in failed_tests:
                    passed_tests.add(m.group(1))

            for failed_re in failed_res:
                m = failed_re.match(line)
                if m:
                    failed_tests.add(m.group(1))
                    if m.group(1) in passed_tests:
                        passed_tests.remove(m.group(1))

            for skipped_re in skipped_res:
                m = skipped_re.match(line)
                if m:
                    skipped_tests.add(m.group(1))

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
