from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one patch target in {path}, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "drive/scripts/yzu_cluster/worker_control.py",
    '''    def upload_artifact(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
        content: bytes,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self._claim_for_attempt(job_id, worker_id, attempt)
        safe_name = Path(str(name or "")).name
        if not safe_name or safe_name != name or safe_name in {".", ".."}:
            raise ValueError("artifact name must be a plain filename")
        if len(content) > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        digest = hashlib.sha256(content).hexdigest()
        expected = str(expected_sha256 or "").strip().lower()
        if expected and not hmac.compare_digest(expected, digest):
            raise ValueError("artifact sha256 does not match request proof")

        destination = self.orchestrator.jobs_root / job_id / "remote_artifacts" / safe_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.write_bytes(content)
        temporary.replace(destination)
        try:
            relative = destination.relative_to(self.orchestrator.repo_root)
        except ValueError as exc:
            destination.unlink(missing_ok=True)
            raise ValueError("artifact destination is outside the repository") from exc
        return {
            "artifact": str(relative),
            "name": safe_name,
            "bytes": len(content),
            "sha256": digest,
            "worker_id": worker_id,
            "attempt": attempt,
        }
''',
    '''    def prepare_artifact_upload(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
    ) -> tuple[Path, Path, str]:
        self._claim_for_attempt(job_id, worker_id, attempt)
        safe_name = Path(str(name or "")).name
        if not safe_name or safe_name != name or safe_name in {".", ".."}:
            raise ValueError("artifact name must be a plain filename")
        destination = self.orchestrator.jobs_root / job_id / "remote_artifacts" / safe_name
        try:
            destination.relative_to(self.orchestrator.repo_root)
        except ValueError as exc:
            raise ValueError("artifact destination is outside the repository") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{safe_name}.{worker_id}.{attempt}.part")
        return destination, temporary, safe_name

    def commit_artifact_upload(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
        temporary: Path,
        size: int,
        digest: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        destination, expected_temporary, safe_name = self.prepare_artifact_upload(
            job_id,
            worker_id=worker_id,
            attempt=attempt,
            name=name,
        )
        if temporary.resolve() != expected_temporary.resolve():
            raise ValueError("artifact temporary path does not match the execution attempt")
        if size > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        expected = str(expected_sha256 or "").strip().lower()
        if expected and not hmac.compare_digest(expected, digest):
            raise ValueError("artifact sha256 does not match request proof")
        if not temporary.is_file() or temporary.stat().st_size != size:
            raise ValueError("artifact upload is incomplete")
        os.replace(temporary, destination)
        relative = destination.relative_to(self.orchestrator.repo_root)
        return {
            "artifact": str(relative),
            "name": safe_name,
            "bytes": size,
            "sha256": digest,
            "worker_id": worker_id,
            "attempt": attempt,
        }

    def upload_artifact(
        self,
        job_id: str,
        *,
        worker_id: str,
        attempt: int,
        name: str,
        content: bytes,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        _, temporary, _ = self.prepare_artifact_upload(
            job_id,
            worker_id=worker_id,
            attempt=attempt,
            name=name,
        )
        if len(content) > self.max_artifact_bytes:
            raise ValueError(f"artifact exceeds {self.max_artifact_bytes} byte limit")
        digest = hashlib.sha256(content).hexdigest()
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            return self.commit_artifact_upload(
                job_id,
                worker_id=worker_id,
                attempt=attempt,
                name=name,
                temporary=temporary,
                size=len(content),
                digest=digest,
                expected_sha256=expected_sha256,
            )
        finally:
            temporary.unlink(missing_ok=True)
''',
)

replace_once(
    "drive/scripts/yzu_cluster/worker_control.py",
    '''        content = await request.body()
        return invoke(
            control.upload_artifact,
            job_id,
            worker_id=x_yzu_worker_id,
            attempt=x_yzu_attempt,
            name=name,
            content=content,
            expected_sha256=x_content_sha256,
        )
''',
    '''        _, temporary, _ = invoke(
            control.prepare_artifact_upload,
            job_id,
            worker_id=x_yzu_worker_id,
            attempt=x_yzu_attempt,
            name=name,
        )
        total = 0
        digest_builder = hashlib.sha256()
        try:
            with temporary.open("wb") as handle:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > control.max_artifact_bytes:
                        raise HTTPException(status_code=413, detail="artifact exceeds configured byte limit")
                    digest_builder.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            return invoke(
                control.commit_artifact_upload,
                job_id,
                worker_id=x_yzu_worker_id,
                attempt=x_yzu_attempt,
                name=name,
                temporary=temporary,
                size=total,
                digest=digest_builder.hexdigest(),
                expected_sha256=x_content_sha256,
            )
        finally:
            temporary.unlink(missing_ok=True)
''',
)
