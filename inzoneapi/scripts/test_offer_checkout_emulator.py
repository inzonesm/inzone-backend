"""Run isolated real-Firestore tests: python .../test_offer_checkout_emulator.py /path/emulator.jar."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        raise SystemExit('Supply a locally installed Firestore emulator JAR path')
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryFile(mode='w+') as log:
        emulator = subprocess.Popen(['java', '-jar', str(Path(sys.argv[1]).resolve()),
                                     '--host=127.0.0.1', f'--port={port}',
                                     '--project_id=demo-inzone-checkout'], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if emulator.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Emulator startup timed out')
            env = dict(os.environ, FIRESTORE_EMULATOR_HOST=f'127.0.0.1:{port}',
                       PYTHONPATH=str(root / 'inzoneapi'), no_grpc_proxy='127.0.0.1,localhost',
                       NO_PROXY='127.0.0.1,localhost', no_proxy='127.0.0.1,localhost')
            return subprocess.run([sys.executable, '-m', 'unittest', 'discover',
                                   '-s', 'inzoneapi/tests', '-p', 'test_offer_checkout.py', '-v'],
                                  cwd=root, env=env, timeout=180).returncode
        finally:
            if emulator.poll() is None:
                emulator.terminate()
                try:
                    emulator.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    emulator.kill()
                    emulator.wait()


if __name__ == '__main__':
    raise SystemExit(main())
