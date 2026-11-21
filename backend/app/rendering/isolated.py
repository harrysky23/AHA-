"""Only this Docker adapter may execute model-authored TSX."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from threading import Event
from uuid import uuid4

from .core import Budget, RenderError, executable

IMAGE = "aha-remotion-isolated:1"


def run_isolated(mode, budget: Budget, cancel: Event, *, source=None, output=None):
    docker = executable("docker")
    name = f"aha-code-{uuid4().hex}"
    command = [
        docker, "run", "--rm", "--init", "--name", name, "--pull=never", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65532:65532",
        "--cpus=3", "--memory=2g", "--memory-swap=2g", "--pids-limit=384", "--shm-size=256m",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=700m,mode=1777",
    ]
    if source is not None:
        command += ["--mount", f"type=bind,src={Path(source).resolve()},dst=/input,readonly"]
    command += [IMAGE, mode]
    env = {key: os.environ[key] for key in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT") if key in os.environ}
    with tempfile.TemporaryFile(dir=budget.root) as log, tempfile.TemporaryFile(dir=budget.root) as result:
        stream = output.open("xb") if output else result
        try:
            budget.check()
            if cancel.is_set():
                raise RenderError("render_cancelled", "영상 작업을 취소했어요.")
            with subprocess.Popen(command, stdout=stream, stderr=log, stdin=subprocess.DEVNULL, env=env) as proc:
                try:
                    while proc.poll() is None:
                        budget.check()
                        if cancel.wait(.15):
                            raise RenderError("render_cancelled", "영상 작업을 취소했어요.")
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
                        try:
                            removed = subprocess.run([docker, "rm", "-f", name], env=env, capture_output=True, timeout=15)
                            if removed.returncode:
                                listed = subprocess.run(
                                    [docker, "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
                                    env=env, capture_output=True, timeout=10,
                                )
                                if listed.returncode or listed.stdout.strip():
                                    raise RenderError("cleanup_failed", "격리 컨테이너 종료를 확인하지 못했어요.")
                        except (OSError, subprocess.TimeoutExpired):
                            raise RenderError("cleanup_failed", "격리 컨테이너 종료를 확인하지 못했어요.") from None
                if proc.returncode:
                    log.seek(0)
                    try:
                        info = json.loads(log.read(4096))
                        stage, message = info["stage"], info["message"]
                    except (ValueError, TypeError, KeyError):
                        stage, message = "isolated_unavailable", "Docker 엔진 또는 로컬 격리 이미지를 확인해 주세요."
                    if not isinstance(stage, str):
                        stage = "isolated_unavailable"
                    if stage == "validation" and isinstance(message, str):
                        safe = re.fullmatch(r"(?:line \d+: )?(?:TypeScript (?:syntax|type) error TS\d+|Expected export default function Visual with one props parameter|Unsupported syntax [A-Za-z0-9_]+|Only named imports from remotion are allowed|Unsupported Remotion API|Forbidden identifier|External global is forbidden|External references are forbidden|Only numeric indexing is allowed|Use const bindings|Unsupported element|Unsupported JSX attribute|Unsupported function call|Unsupported method call|Unsupported call target|Code is too complex|TypeScript directives are forbidden|CSS time-based motion is forbidden)", message)
                        raise RenderError("code_validation", message if safe else "Code failed static validation")
                    if stage in {"render", "encode"}:
                        safe_errors = {"Stage timed out", "Local stage failed", "Blocked request or incomplete capture", "bundle", "csp", "select", "frames"}
                        detail = message if isinstance(message, str) and message in safe_errors else "Local stage failed"
                        raise RenderError(f"code_{stage}", detail)
                    raise RenderError("isolated_unavailable", "Docker 렌더러를 시작하지 못했어요.")
            budget.check()
            if mode == "check":
                result.seek(0)
                if result.read(100) != b"aha-isolated-v1":
                    raise RenderError("isolated_unavailable", "격리 렌더러 상태 확인에 실패했어요.")
        finally:
            if output:
                stream.close()
