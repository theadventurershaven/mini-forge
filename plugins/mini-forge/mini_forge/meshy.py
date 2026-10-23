"""Meshy REST client with a per-job credit ledger.

Every paid call writes a `submitted` row (with the task id) to `<job>/logs/credits.jsonl` as soon
as Meshy accepts it, and a cost row when it finishes. If a run is interrupted, recover the task
from the ledger with `poll()`; never resubmit a paid task that may already have been accepted.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import httpx

from .config import Settings

API = "https://api.meshy.ai"
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELED", "EXPIRED"}
I23D = "/openapi/v1/image-to-3d"

# List prices for estimates only (check https://docs.meshy.ai before relying on them).
PRICE = {"image-to-3d": 20, "high-resolution": 5, "analyze": 0, "repair": 10}
IMAGE_TO_IMAGE_PRICE = {"nano-banana": 3, "nano-banana-2": 6, "nano-banana-pro": 9, "gpt-image-2": 12}


class MeshyError(RuntimeError):
    pass


class Ledger:
    def __init__(self, job_dir: Path):
        self.path = Path(job_dir) / "logs" / "credits.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    @property
    def total(self) -> int:
        return sum(int(r.get("credits") or 0) for r in self.rows())

    def tasks(self, op: str | None = None) -> dict[str, dict]:
        """Latest row per task id."""
        latest: dict[str, dict] = {}
        for r in self.rows():
            if r.get("task_id") and (op is None or r.get("op") == op):
                latest[r["task_id"]] = r
        return latest

    @property
    def unresolved(self) -> set[str]:
        return {t for t, r in self.tasks().items() if r.get("credits") is None}

    def record(self, op: str, task_id: str | None, credits: int | None, **extra: Any) -> None:
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "op": op, "task_id": task_id, "credits": credits, **extra}
        with self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")


class Meshy:
    def __init__(self, ledger: Ledger, api_key: str | None = None, timeout: float = 60.0):
        key = api_key or Settings.load().meshy_api_key
        if not key:
            raise MeshyError("MESHY_API_KEY is not set (run `mini-forge setup`)")
        self.http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
        self.ledger = ledger
        self.raw_log = ledger.path.parent / "meshy_raw.jsonl"

    def _log_raw(self, kind: str, payload: Any) -> None:
        # Requests can hold the reference picture as a data URI and responses hold signed asset
        # URLs: keep this file private.
        with self.raw_log.open("a") as f:
            f.write(json.dumps({"ts": time.time(), "kind": kind, "payload": payload}, default=str) + "\n")

    def balance(self) -> int:
        r = self.http.get("/openapi/v1/balance")
        r.raise_for_status()
        return int(r.json()["balance"])

    def _post(self, path: str, body: dict) -> str:
        r = self.http.post(path, json=body)
        logged = {k: (v if not str(v).startswith("data:") else "<data uri>") for k, v in body.items()}
        self._log_raw(f"POST {path}", {"request": logged, "status": r.status_code, "response": r.text[:2000]})
        if r.status_code >= 400:
            raise MeshyError(f"POST {path} -> {r.status_code}: {r.text[:500]}")
        data = r.json()
        task_id = data.get("result") or data.get("id")
        if not task_id:
            raise MeshyError(f"no task id in response: {data}")
        return task_id

    def poll(self, path: str, task_id: str, interval: float = 5.0, timeout: float = 1800.0) -> dict:
        deadline, last = time.time() + timeout, -1
        while time.time() < deadline:
            r = self.http.get(f"{path}/{task_id}")
            if r.status_code >= 400:
                raise MeshyError(f"GET {path}/{task_id} -> {r.status_code}: {r.text[:300]}")
            data = r.json()
            status, progress = data.get("status"), data.get("progress", 0)
            if progress != last:
                print(f"  {path.rsplit('/', 1)[-1]} {task_id[:8]} {status} {progress}%", flush=True)
                last = progress
            if status in TERMINAL:
                self._log_raw(f"DONE {path}", data)
                if status != "SUCCEEDED":
                    raise MeshyError(f"task {task_id} {status}: {data.get('task_error') or data.get('error')}")
                data["_task_id"] = task_id
                return data
            time.sleep(interval)
        raise MeshyError(f"task {task_id} still running after {timeout:.0f}s; recover it later with its id")

    def _charged(self, op: str, path: str, body: dict, estimate: int) -> dict:
        before = self.balance()
        task_id = self._post(path, body)
        params = {k: v for k, v in body.items() if k not in ("image_url", "image_urls", "reference_image_urls")}
        self.ledger.record(op, task_id, None, status="submitted", estimate=estimate, balance_before=before, params=params)
        try:
            data = self.poll(path, task_id)
        except BaseException as exc:
            self.ledger.record(op, task_id, None, status="interrupted", error=type(exc).__name__)
            raise
        return self.settle(op, task_id, data, before, estimate)

    def settle(self, op: str, task_id: str, data: dict, before: int | None, estimate: int) -> dict:
        """Record the cost of a finished task: Meshy's own figure, else the balance change."""
        after = None
        try:
            after = self.balance()
        except (httpx.HTTPError, KeyError, ValueError):
            print(f"warning: balance unavailable after task {task_id}; cost taken from Meshy's report", flush=True)
        reported = data.get("consumed_credits")
        delta = max(before - after, 0) if before is not None and after is not None else None
        cost = int(reported) if isinstance(reported, (int, float)) else delta
        self.ledger.record(op, task_id, cost, status="completed" if cost is not None else "cost_unknown",
                           reported=reported, delta=delta, estimate=estimate, balance_after=after)
        data["_task_id"], data["_cost"] = task_id, cost
        return data

    @staticmethod
    def image_to_data_uri(path: Path) -> str:
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"

    def download(self, url: str, dest: Path) -> Path:
        """Download to a temporary name and rename only when complete."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        with httpx.stream("GET", url, timeout=300.0, follow_redirects=True) as r:
            r.raise_for_status()
            with part.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        if part.stat().st_size == 0:
            raise MeshyError(f"empty download for {dest.name}")
        part.replace(dest)
        return dest

    # ---- operations ----------------------------------------------------------------------
    @staticmethod
    def image_to_3d_estimate(geometry_resolution: str | None = "4k") -> int:
        return PRICE["image-to-3d"] + (PRICE["high-resolution"] if geometry_resolution in ("2k", "4k") else 0)

    def image_to_3d(self, image: str, ai_model: str = "meshy-7.1", geometry_resolution: str | None = "4k") -> dict:
        """Untextured triangle mesh. Remeshing is off so the original generated geometry is kept."""
        body: dict[str, Any] = {"image_url": image, "ai_model": ai_model, "should_texture": False,
                                "target_formats": ["glb"], "origin_at": "bottom", "topology": "triangle",
                                "should_remesh": False}
        if geometry_resolution:
            body["geometry_resolution"] = geometry_resolution
        return self._charged("image-to-3d", I23D, body, self.image_to_3d_estimate(geometry_resolution))

    def image_to_image(self, prompt: str, references: list[str], ai_model: str = "nano-banana-pro") -> dict:
        """Edit or restyle from 1-5 reference images. Prompt limit is 600 characters."""
        if not 2 <= len(prompt) <= 600:
            raise MeshyError(f"image-to-image prompt must be 2-600 characters, got {len(prompt)}")
        body = {"ai_model": ai_model, "prompt": prompt, "reference_image_urls": references}
        return self._charged("image-to-image", "/openapi/v1/image-to-image", body, IMAGE_TO_IMAGE_PRICE.get(ai_model, 12))

    def analyze(self, input_task_id: str, printer_type: str | None = "fdm",
                print_height_mm: float | None = None) -> dict:
        """Free. With a printer type and height Meshy also reports walls thinner than its minimum
        (FDM 1.0 mm) in `printability.thin_walls`. Advisory: fine nozzles print thinner relief."""
        body: dict[str, Any] = {"input_task_id": input_task_id}
        if printer_type:
            body["printer_type"] = printer_type
        if print_height_mm:
            body["intended_print_height_mm"] = print_height_mm
        return self._charged("analyze", "/openapi/v1/print/analyze", body, 0)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def thin_walls(analyze_result: dict) -> Any:
    p = analyze_result.get("printability") or analyze_result.get("result") or {}
    return p.get("thin_walls") if isinstance(p, dict) else None
