import re
from typing import Optional, Union

from multi_swe_bench.harness.image import Config, File, Image
from multi_swe_bench.harness.instance import Instance, TestResult
from multi_swe_bench.harness.pull_request import PullRequest


# ---------------------------------------------------------------------------
# type-fest: sindresorhus/type-fest
# ---------------------------------------------------------------------------
# Pure TypeScript type utility library. Tests are static type checks via:
#   - tsd (type definition tests on test-d/*.ts files)
#   - tsc (TypeScript compiler check)
#   - node --test (lint-rules/*.test.js, only at PRs >=1265)
#   - node script/test/... (source file extension validator, from PR 264+)
#
# 96 PRs in dataset, range #78 - #1374. All SWE-mode (no number_interval).
# Single node:20 base image works for all PRs (verified: old deps install
# on modern Node).
#
# Verified issues requiring per-PR handling:
#   1. PRs >= 1119: tsd/tsc need --max-old-space-size=6144 (OOM otherwise)
#   2. PRs 1265, 1309: test_patch modifies lint-rules/ only → need node --test
#   3. PR 264: test_patch creates script/test/source-files-extension.js
#      (doesn't exist at base) → must run conditionally after patches
# ---------------------------------------------------------------------------


class TypeFestImageBase(Image):
    """Base image — installs Node 20, clones repo."""

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
        return "node:20"

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
            code = f"RUN git clone https://github.com/{self.pr.org}/{self.pr.repo}.git /home/{self.pr.repo}"
        else:
            code = f"COPY {self.pr.repo} /home/{self.pr.repo}"

        return f"""FROM {image_name}

{self.global_env}

WORKDIR /home/

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y git curl

{code}

{self.clear_env}

"""


# ---------------------------------------------------------------------------
# Instance Image
# ---------------------------------------------------------------------------

# Threshold: PRs >= this need --max-old-space-size=6144 for tsd/tsc.
# Verified: package.json at PR #1119 base already specifies this flag.
_NEEDS_MEMORY_FLAG = 1119


class TypeFestImageDefault(Image):
    """Per-PR instance image. Injects patches and shell scripts tailored
    to the PR's era."""

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
        return TypeFestImageBase(self.pr, self.config)

    def image_tag(self) -> str:
        return f"pr-{self.pr.number}"

    def workdir(self) -> str:
        return f"pr-{self.pr.number}"

    def _tsd_cmd(self) -> str:
        """tsd invocation, with memory flag for modern PRs."""
        if self.pr.number >= _NEEDS_MEMORY_FLAG:
            return "node --max-old-space-size=6144 ./node_modules/.bin/tsd"
        return "npx tsd"

    def _tsc_cmd(self) -> str:
        """tsc invocation, with memory flag for modern PRs."""
        if self.pr.number >= _NEEDS_MEMORY_FLAG:
            return "node --max-old-space-size=6144 ./node_modules/.bin/tsc --noEmit"
        return "npx tsc --noEmit"

    def _extra_test_cmds(self) -> str:
        """Additional test commands needed by specific PRs.

        - node --test: for PRs that modify lint-rules/ files (>=1265 era)
        - node script/test/...: conditional, runs only if the script exists
        """
        cmds = ""

        # Conditional script runner — harmless no-op when file doesn't exist.
        # Needed for PR 264 (test_patch creates it) and PR 906+ (exists at base).
        cmds += """
# Run source-files-extension check if the script exists
if [ -f script/test/source-files-extension.js ]; then
    node script/test/source-files-extension.js 2>&1 || true
fi
"""

        # node --test for lint-rules (only available at PRs with test:linter script)
        if self.pr.number >= 1265:
            cmds += """
# Run Node.js built-in test runner for lint-rules tests
node --test 2>&1 || true
"""

        return cmds

    def _make_run_script(self, patches: str) -> str:
        """Generate a run script with optional patch application.

        Args:
            patches: shell commands to apply patches (empty string for baseline).
        """
        tsd = self._tsd_cmd()
        tsc = self._tsc_cmd()
        extra = self._extra_test_cmds()

        return """#!/bin/bash
set -eo pipefail

cd /home/{repo}
{patches}
# Run tsd (type definition tests) — primary test tool.
# Outputs nothing on success, errors to stderr on failure.
{tsd} 2>&1 || true

# Run tsc (TypeScript compiler check).
# Only meaningful when tsconfig.json exists (PR >=153).
if [ -f tsconfig.json ]; then
    {tsc} 2>&1 || true
fi
{extra}
""".format(
            repo=self.pr.repo,
            patches=patches,
            tsd=tsd,
            tsc=tsc,
            extra=extra,
        )

    def files(self) -> list[File]:
        return [
            File(".", "fix.patch", f"{self.pr.fix_patch}"),
            File(".", "test.patch", f"{self.pr.test_patch}"),
            File(
                ".",
                "check_git_changes.sh",
                """#!/bin/bash
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
                """#!/bin/bash
set -e

cd /home/{repo}
git reset --hard
bash /home/check_git_changes.sh
git checkout {sha}
bash /home/check_git_changes.sh

npm install

""".format(repo=self.pr.repo, sha=self.pr.base.sha),
            ),
            # run.sh — baseline: no patches
            File(".", "run.sh", self._make_run_script("")),
            # test-run.sh — test.patch only
            File(
                ".",
                "test-run.sh",
                self._make_run_script("git apply --whitespace=nowarn /home/test.patch"),
            ),
            # fix-run.sh — test.patch + fix.patch
            File(
                ".",
                "fix-run.sh",
                self._make_run_script(
                    "git apply --whitespace=nowarn /home/test.patch /home/fix.patch"
                ),
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


# ---------------------------------------------------------------------------
# Instance
# ---------------------------------------------------------------------------


@Instance.register("sindresorhus", "type-fest")
class TypeFest(Instance):
    def __init__(self, pr: PullRequest, config: Config, *args, **kwargs):
        super().__init__()
        self._pr = pr
        self._config = config

    @property
    def pr(self) -> PullRequest:
        return self._pr

    def dependency(self) -> Optional[Image]:
        return TypeFestImageDefault(self.pr, self._config)

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
        """Parse combined tsd + tsc + node --test output.

        tsd error format (to stderr, grouped by file):
            test-d/some-type.ts
            ✖  10:20  Argument of type string is not assignable ...

        tsc error format:
            source/some-type.d.ts(10,20): error TS2345: ...

        node --test output (TAP-like):
            ✔ test name (duration)
            ✖ test name (duration)

        node script/test output:
            source/foo.ts extension should be `.d.ts`.
            (exit 1 on failure, no output on success)

        Strategy: parse each error as a unique failed test name keyed by
        file:line:col.  Errors stable across phases (e.g. node_modules/)
        cancel out in the 3-phase diff.  Errors introduced by test.patch
        and removed by fix.patch drive the FAIL→PASS transitions.
        """
        passed_tests: set[str] = set()
        failed_tests: set[str] = set()
        skipped_tests: set[str] = set()

        # Strip ANSI escape codes
        ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
        clean_log = ansi_escape.sub("", test_log)

        # Track tsd file context
        current_tsd_file: str = ""

        # tsd file header: a bare file path on its own line
        re_tsd_file = re.compile(r"^([\w./-]+\.tsx?)$")

        # tsd error: ✖  line:col  message
        re_tsd_error = re.compile(r"^\s*✖\s+(\d+:\d+)\s+(.+)$")

        # tsc error: file(line,col): error TSxxxx: message
        re_tsc_error = re.compile(
            r"^([\w./-]+\.tsx?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)$"
        )

        # tsd summary: N error(s)
        re_tsd_summary = re.compile(r"^\s*(\d+)\s+errors?$")

        # node --test pass/fail (TAP output from Node built-in test runner)
        re_node_test_pass = re.compile(r"^✔\s+(.+?)(?:\s+\(.+\))?\s*$")
        re_node_test_fail = re.compile(r"^✖\s+(.+?)(?:\s+\(.+\))?\s*$")
        # Also handle TAP "ok" / "not ok" format
        re_tap_ok = re.compile(r"^ok\s+\d+\s+-?\s*(.+)$")
        re_tap_not_ok = re.compile(r"^not ok\s+\d+\s+-?\s*(.+)$")

        # source-files-extension script error
        re_ext_error = re.compile(r"^(source/[\w./-]+)\s+extension should be")

        for line in clean_log.splitlines():
            line = line.strip()
            if not line:
                continue

            # tsd file header
            file_match = re_tsd_file.match(line)
            if file_match:
                current_tsd_file = file_match.group(1)
                continue

            # tsd error
            tsd_err = re_tsd_error.match(line)
            if tsd_err:
                loc = tsd_err.group(1)
                if current_tsd_file:
                    failed_tests.add(f"{current_tsd_file}:{loc}")
                else:
                    failed_tests.add(f"tsd:{loc}")
                continue

            # tsc error
            tsc_err = re_tsc_error.match(line)
            if tsc_err:
                filepath = tsc_err.group(1)
                line_no = tsc_err.group(2)
                col = tsc_err.group(3)
                ts_code = tsc_err.group(4)
                failed_tests.add(f"{filepath}({line_no},{col}):{ts_code}")
                continue

            # node --test pass
            m = re_node_test_pass.match(line) or re_tap_ok.match(line)
            if m:
                passed_tests.add(f"node-test:{m.group(1).strip()}")
                continue

            # node --test fail
            m = re_node_test_fail.match(line) or re_tap_not_ok.match(line)
            if m:
                failed_tests.add(f"node-test:{m.group(1).strip()}")
                continue

            # source-files-extension error
            ext_err = re_ext_error.match(line)
            if ext_err:
                failed_tests.add(f"ext-check:{ext_err.group(1)}")
                continue

            # Skip tsd summary lines
            if re_tsd_summary.match(line):
                continue

        # If log has no output at all, the whole run passed.
        if not failed_tests and not passed_tests:
            passed_tests.add("tsd:all")
            passed_tests.add("tsc:all")

        # Ensure no overlap
        passed_tests -= failed_tests
        passed_tests -= skipped_tests
        skipped_tests -= failed_tests

        return TestResult(
            passed_count=len(passed_tests),
            failed_count=len(failed_tests),
            skipped_count=len(skipped_tests),
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            skipped_tests=skipped_tests,
        )
