"""Run integration tests against a disposable, loopback-only PostgreSQL on Windows.

Downloads vendor binaries into an ignored directory; never installs a system service.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".test-postgres"
URL = "https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64-binaries.zip"


def run(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=ROOT, check=True, creationflags=subprocess.CREATE_NO_WINDOW, **kwargs
    )


def main() -> int:
    if os.name != "nt":
        raise SystemExit("En otros sistemas configura TEST_DATABASE_URL y ejecuta pytest")
    WORK.mkdir(exist_ok=True)
    archive = WORK / "postgresql.zip"
    pg = WORK / "pgsql"
    if not (pg / "bin" / "pg_ctl.exe").exists():
        if not archive.exists():
            print("Descargando binarios oficiales PostgreSQL para pruebas locales...", flush=True)
            with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                if name.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                    target = (WORK / name).resolve()
                    if not target.is_relative_to(WORK.resolve()):
                        raise ValueError("Ruta inválida dentro del archivo PostgreSQL")
                    source.extract(name, WORK)
    data = WORK / "data"
    if not (data / "PG_VERSION").exists():
        run(
            str(pg / "bin" / "initdb.exe"),
            "-D",
            str(data),
            "-U",
            "test_halloween",
            "-A",
            "trust",
            "--encoding=UTF8",
            "--no-locale",
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    ctl = str(pg / "bin" / "pg_ctl.exe")
    run(
        ctl,
        "-D",
        str(data),
        "-l",
        str(WORK / "postgres.log"),
        "-o",
        f"-h 127.0.0.1 -p {port}",
        "-w",
        "start",
    )
    try:
        env = dict(
            os.environ,
            TEST_DATABASE_URL=f"postgresql://test_halloween@127.0.0.1:{port}/postgres?sslmode=disable",
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sys.argv[1:]],
            cwd=ROOT,
            env=env,
        )
        return result.returncode
    finally:
        run(ctl, "-D", str(data), "-m", "fast", "-w", "stop")


if __name__ == "__main__":
    raise SystemExit(main())
