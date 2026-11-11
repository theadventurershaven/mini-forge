"""Optional Bambu Lab LAN printing: status, upload (FTPS), start, watch, camera frame.

Needs the printer on the same network with LAN Only Mode and Developer Mode switched on (on the
printer's screen, under the Wi-Fi/network settings). Without Developer Mode, status and upload
work but starting a print is refused with HMS 0500_0500_0001_0007.

Keep one connection at a time. Many overlapping sessions (status polling, camera, other apps)
have wedged a printer's network module until a power cycle.
"""

from __future__ import annotations

import ftplib
import json
import math
import re
import socket
import ssl
import struct
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client as mqtt

from .config import BED_TYPES, Settings


class PrinterError(RuntimeError):
    pass


def plate_nozzle(package: Path) -> float:
    """Nozzle diameter the package was sliced for; requires exactly one plate."""
    with zipfile.ZipFile(package) as z:
        plates = [n for n in z.namelist() if re.fullmatch(r"Metadata/plate_\d+\.gcode", n)]
        if plates != ["Metadata/plate_1.gcode"]:
            raise PrinterError("expected one sliced plate (Metadata/plate_1.gcode)")
        with z.open(plates[0]) as g:
            values = {line.split(b"=", 1)[1].strip().strip(b'"').decode() for line in g if line.startswith(b"; nozzle_diameter = ")}
    if len(values) != 1:
        raise PrinterError(f"cannot read one nozzle size from the package: {values}")
    return float(values.pop())


class _ImplicitFTPS(ftplib.FTP_TLS):
    """Bambu printers use implicit FTPS on port 990."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, v):
        if v is not None and not isinstance(v, ssl.SSLSocket):
            v = self.context.wrap_socket(v)
        self._sock = v


def _tls() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # the printer uses a self-signed certificate
    return ctx


@dataclass
class Status:
    state: str
    job: str
    percent: int
    remaining_min: int
    layer: int
    total_layers: int
    nozzle_diameter: str
    part_fan: str
    print_error: int
    hms: list
    slot_present: dict[int, bool]

    @property
    def idle(self) -> bool:
        return self.state in ("IDLE", "FINISH", "FAILED")

    def summary(self) -> str:
        return (f"{self.state} job={self.job!r} {self.percent}% layer {self.layer}/{self.total_layers} "
                f"{self.remaining_min} min left | nozzle {self.nozzle_diameter} mm | part fan {self.part_fan} | "
                f"error={self.print_error} hms={len(self.hms)}")


class Printer:
    def __init__(self, settings: Settings | None = None):
        self.settings = s = settings or Settings.load()
        if not s.printer_configured():
            raise PrinterError("printer not configured: set PRINTER_HOST, PRINTER_SERIAL and PRINTER_ACCESS_CODE")
        self.host, self.serial, self.code = s.printer_host, s.printer_serial, s.printer_access_code

    def _session(self, request: dict | None, wait_s: float, want_reply: str | None = None) -> tuple[dict, dict | None]:
        state: dict = {}
        reply: dict | None = None

        def on_connect(c, u, f, rc, props=None):
            c.subscribe(f"device/{self.serial}/report")
            c.publish(f"device/{self.serial}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
            if request:
                c.publish(f"device/{self.serial}/request", json.dumps(request))

        def on_message(c, u, msg):
            nonlocal reply
            p = (json.loads(msg.payload).get("print") or {})
            if want_reply and p.get("command") == want_reply and "result" in p:
                reply = p
            state.update({k: v for k, v in p.items() if k != "command"})

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"mini-forge-{int(time.time())}", protocol=mqtt.MQTTv311)
        c.username_pw_set("bblp", self.code)
        c.tls_set_context(_tls())
        c.tls_insecure_set(True)
        c.on_connect, c.on_message = on_connect, on_message
        c.connect(self.host, 8883, keepalive=30)
        c.loop_start()
        t0 = time.time()
        try:
            while time.time() - t0 < wait_s:
                time.sleep(0.5)
                if want_reply and reply is not None and "gcode_state" in state:
                    break
                if not want_reply and "gcode_state" in state and "ams" in state and time.time() - t0 > 3:
                    break
        finally:
            c.loop_stop()
            c.disconnect()
        return state, reply

    def status(self) -> Status:
        st, _ = self._session(None, wait_s=12)
        if not st.get("gcode_state"):
            raise PrinterError("no status report from the printer (check LAN mode, address and access code)")
        return status_from(st)

    def monitor(self, max_s: float, check_s: float = 30, full_s: float = 300):
        """Yield (status report, seconds since the printer last reported) every check_s seconds,
        over one MQTT connection kept open for the whole watch.

        The printer pushes changes on its own once subscribed, so only a full report ("pushall")
        is requested, at the start and then every full_s seconds. Reconnecting and requesting a
        full report every 90 s was in use when a P1S froze mid-print twice with no error; the
        same file printed fine with two status reads in total.
        """
        state: dict = {}
        heard = {"t": 0.0}
        pushed = {"t": 0.0}

        def pushall(c):
            c.publish(f"device/{self.serial}/request", json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
            pushed["t"] = time.time()

        def on_connect(c, u, f, rc, props=None):
            c.subscribe(f"device/{self.serial}/report")
            if time.time() - pushed["t"] >= full_s:
                pushall(c)

        def on_message(c, u, msg):
            state.update({k: v for k, v in (json.loads(msg.payload).get("print") or {}).items() if k != "command"})
            heard["t"] = time.time()

        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"mini-forge-watch-{int(time.time())}", protocol=mqtt.MQTTv311)
        c.username_pw_set("bblp", self.code)
        c.tls_set_context(_tls())
        c.tls_insecure_set(True)
        c.reconnect_delay_set(10, 120)
        c.on_connect, c.on_message = on_connect, on_message
        c.connect(self.host, 8883, keepalive=60)
        c.loop_start()
        t0 = time.time()
        try:
            while time.time() - t0 < max_s:
                time.sleep(check_s)
                if c.is_connected() and time.time() - pushed["t"] >= full_s:
                    pushall(c)
                yield dict(state), (time.time() - heard["t"] if heard["t"] else None)
        finally:
            c.loop_stop()
            c.disconnect()

    def upload(self, local: Path) -> int:
        f = _ImplicitFTPS(context=_tls())
        f.connect(self.host, 990, timeout=180)
        try:
            f.login("bblp", self.code)
            f.prot_p()
            try:
                f.cwd("/cache")
            except ftplib.error_perm:
                f.mkd("/cache")
                f.cwd("/cache")
            # The printer never completes the TLS shutdown on the data channel, so storbinary
            # hangs; send the data by hand and skip the unwrap.
            f.voidcmd("TYPE I")
            conn = f.transfercmd(f"STOR {local.name}")
            conn.settimeout(180)
            with local.open("rb") as fh:
                while chunk := fh.read(1 << 14):
                    conn.sendall(chunk)
            conn.close()
            f.voidresp()
            size = f.size(local.name)
        finally:
            f.close()
        if size != local.stat().st_size:
            raise PrinterError(f"stored size {size} differs from local {local.stat().st_size}")
        return size

    def start(self, remote_name: str) -> dict:
        _, bed = BED_TYPES[self.settings.bed]
        slot = self.settings.ams_slot
        req = {"print": {
            "sequence_id": str(int(time.time()) % 100000), "command": "project_file",
            "param": "Metadata/plate_1.gcode", "project_id": "0", "profile_id": "0", "task_id": "0",
            "subtask_id": "0", "subtask_name": remote_name.removesuffix(".gcode.3mf"),
            "url": f"file:///sdcard/cache/{remote_name}", "md5": "", "timelapse": False,
            "bed_type": bed, "bed_levelling": True, "flow_cali": False, "vibration_cali": False,
            "layer_inspect": False, "use_ams": slot > 0}}
        if slot > 0:
            req["print"]["ams_mapping"] = [slot - 1]
        _, reply = self._session(req, wait_s=25, want_reply="project_file")
        if reply is None:
            raise PrinterError("the printer did not acknowledge the start; check Developer Mode and HMS before retrying")
        if reply.get("result") != "success":
            raise PrinterError(f"start refused: {reply}")
        return reply

    def pause(self) -> dict | None:
        return self._session({"print": {"sequence_id": "1", "command": "pause", "param": ""}}, 8, "pause")[1]

    def camera_frame(self, dest: Path, skip: int = 4) -> Path:
        """One JPEG from the chamber camera (P1/A1 series, TLS port 6000)."""
        with _tls().wrap_socket(socket.socket(), server_hostname=self.host) as c:
            c.settimeout(15)
            c.connect((self.host, 6000))
            c.sendall(struct.pack("<IIII", 64, 0x3000, 0, 0) + b"bblp".ljust(32, b"\0") + self.code.encode().ljust(32, b"\0"))

            def read(n: int) -> bytes:
                b = b""
                while len(b) < n:
                    chunk = c.recv(n - len(b))
                    if not chunk:
                        raise PrinterError("camera stream closed")
                    b += chunk
                return b
            frame = b""
            for _ in range(skip + 1):  # the first frames can be stale
                size = struct.unpack("<I", read(16)[:4])[0]
                if not 0 < size < 3_000_000:
                    raise PrinterError("unexpected camera frame size")
                frame = read(size)
        if not frame.startswith(b"\xff\xd8"):
            raise PrinterError("camera returned something other than a JPEG")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(frame)
        return dest


def status_from(st: dict) -> Status:
    """Status from a merged printer report."""
    bits = int(str((st.get("ams") or {}).get("tray_exist_bits", "0")), 16)
    return Status(
        state=st.get("gcode_state", "UNKNOWN"), job=st.get("subtask_name", ""),
        percent=int(st.get("mc_percent") or 0), remaining_min=int(st.get("mc_remaining_time") or 0),
        layer=int(st.get("layer_num") or 0), total_layers=int(st.get("total_layer_num") or 0),
        nozzle_diameter=str(st.get("nozzle_diameter", "?")), part_fan=str(st.get("cooling_fan_speed", "?")),
        print_error=int(st.get("print_error") or 0), hms=st.get("hms") or [],
        slot_present={i + 1: bool(bits >> i & 1) for i in range(16)})


def preflight(printer: Printer, package: Path) -> Status:
    """Refuse to print unless the printer is idle, error-free, has the package's nozzle and filament."""
    st = printer.status()
    problems = []
    if not st.idle:
        problems.append(f"printer is {st.state}, not idle")
    if st.print_error or st.hms:
        problems.append(f"printer reports error {st.print_error} / HMS {st.hms}")
    need = plate_nozzle(package)
    try:
        if not math.isclose(float(st.nozzle_diameter), need):
            problems.append(f"installed nozzle {st.nozzle_diameter} mm, package needs {need:g} mm")
    except ValueError:
        problems.append("printer did not report its nozzle size")
    slot = printer.settings.ams_slot
    if slot > 0 and not st.slot_present.get(slot):
        problems.append(f"AMS slot {slot} reports no filament")
    if problems:
        raise PrinterError("; ".join(problems))
    return st
