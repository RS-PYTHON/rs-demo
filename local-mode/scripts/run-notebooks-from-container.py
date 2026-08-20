#!/usr/bin/env python3

# Copyright 2023-2026 Airbus, CS Group
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Uses an example of Multiprocessing.Pool from claude.ai with:
  - a max number of parallel worker processes
  - workers that die automatically if the main process is killed (even -9)
  - full stack traces printed for failed tasks, without stopping the pool
  - periodic status reporting of running / finished / failed tasks
  - a final summary at the end
"""

import ctypes
import fnmatch
import multiprocessing as mp
import os
import platform
import signal
import subprocess
import threading
import time
import traceback
from pathlib import Path

# This script is run from the ci/cd
os.environ["RSPY_FROM_CICD"] = "1"

OUTPUT_DIR = "/tmp/notebook-outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_WORKERS = 10  # max concurrent subprocesses
STATUS_INTERVAL = 5  # print status every n seconds

HOME = Path.home()


class Notebook:
    """Notebook file attributes"""

    def __init__(self, path: Path):
        path = path.absolute()
        self.path: str = str(path)
        self.dirname: str = str(path.parent)
        self.filename: str = str(path.name)
        self.relative: str = str(path.relative_to(HOME))


def print_bullet(input: list[str] | set[str] | dict[str, any]) -> str:
    """Print a dict with bullet points"""
    if not input:
        return "(none)"
    if isinstance(input, dict):
        input = dict(sorted(input.items()))
        l = [f"{key} -> {value}" for key, value in input.items()]
    else:
        l = list(input)
    return "\n  - ".join([""] + l)


# --------------------------------------------------------------------------
# 1. Make workers die if the parent dies unexpectedly (e.g. `kill -9`)
# --------------------------------------------------------------------------
def _die_with_parent():
    """
    Daemon=True (which Pool sets by default) only cleans up workers on a
    *normal* interpreter exit of the parent. If the parent is SIGKILL'd,
    daemon status is not enough and children become orphans.

    On Linux we can ask the kernel to deliver SIGKILL to this process
    when its parent dies, via prctl(PR_SET_PDEATHSIG). There's no
    equivalent syscall on macOS/Windows; this is a best-effort hook.
    """
    if platform.system() == "Linux":
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            PR_SET_PDEATHSIG = 1
            libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
        except Exception:
            pass


def _worker_init():
    _die_with_parent()
    # Let the main process handle Ctrl+C / signals; workers just ignore it.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


# --------------------------------------------------------------------------
# 2. Wrap the task so a failure carries a *full* formatted traceback string.
#    (An exception object pickled back to the parent normally shows the
#    traceback of where it was *re-raised* in the pool machinery, not the
#    original one — so we capture the text ourselves inside the worker.)
# --------------------------------------------------------------------------
class TaskError(Exception):
    def __init__(self, task_id, original_repr, tb_text):
        self.task_id = task_id
        self.original_repr = original_repr
        self.tb_text = tb_text
        super().__init__(f"Task {task_id} failed: {original_repr}")

    def __reduce__(self):
        # Needed so multiprocessing can pickle/unpickle this exception
        # across the process boundary (custom __init__ args otherwise
        # get lost and unpickling raises a TypeError).
        return (self.__class__, (self.task_id, self.original_repr, self.tb_text))


def _run_task(task_id, func, args, kwargs):
    try:
        result = func(*args, **kwargs)
        return task_id, result
    except Exception as e:
        raise TaskError(task_id, repr(e), traceback.format_exc())


# --------------------------------------------------------------------------
# 3. The actual work function
# --------------------------------------------------------------------------
def do_work(notebook: Notebook) -> str:
    try:
        start_time = time.time()

        outname = notebook.relative.replace("/", "__")
        cmd = ["papermill", notebook.filename, f"{OUTPUT_DIR}/{outname}"]
        print(f"'{" ".join(cmd)}'", flush=True)
        subprocess.check_output(cmd, cwd=notebook.dirname, stderr=subprocess.STDOUT)

        # Return execution time in seconds
        return f"{time.time() - start_time:.2f}s"

    except subprocess.CalledProcessError as exc:
        last_line = "\n".join(exc.output.decode("utf-8").strip().splitlines()[-1:])
        raise RuntimeError(last_line) from exc


# --------------------------------------------------------------------------
# 4. PoolRunner: submits tasks, tracks state, prints status periodically
# --------------------------------------------------------------------------
class PoolRunner:
    def __init__(self, max_workers, status_interval):
        self.max_workers = max_workers
        self.status_interval = status_interval
        self.lock = threading.Lock()
        self.running = set()  # task_id
        self.finished = {}  # task_id -> result
        self.failed = {}  # task_id -> TaskError
        self._stop_monitor = threading.Event()

    def _on_success(self, task_id):
        def cb(result):
            _, value = result
            with self.lock:
                self.running.remove(task_id)
                self.finished[task_id] = value

        return cb

    def _on_error(self, task_id):
        def cb(exc):
            with self.lock:
                self.running.remove(task_id)
                self.failed[task_id] = exc
            # Print the full original stack trace, but keep going.
            if isinstance(exc, TaskError):
                print(f"\n[TASK {task_id} FAILED]\n{exc.tb_text}", flush=True)
            else:
                # Fallback: some other unexpected pickling/dispatch error.
                traceback.print_exception(type(exc), exc, exc.__traceback__)

        return cb

    def _monitor(self):
        while not self._stop_monitor.wait(self.status_interval):
            with self.lock:
                running = print_bullet(self.running)
                finished = print_bullet(self.finished)
                failed = print_bullet(self.failed)
            print(
                f"\n--- status ---\n"
                f"running : {running}\n"
                f"finished: {finished}\n"
                f"failed  : {failed}\n"
                f"--------------",
                flush=True,
            )

    def run(self, notebooks: list[Notebook]):
        monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        monitor_thread.start()

        try:
            with mp.Pool(processes=self.max_workers, initializer=_worker_init) as pool:
                async_results = []
                for notebook in notebooks:
                    task_id = notebook.relative
                    with self.lock:
                        self.running.add(task_id)  # notebook
                    ar = pool.apply_async(
                        _run_task,
                        args=(task_id, do_work, (notebook,), {}),
                        callback=self._on_success(task_id),
                        error_callback=self._on_error(task_id),
                    )
                    async_results.append(ar)

                pool.close()
                pool.join()  # waits for everything, including callbacks in flight
        finally:
            self._stop_monitor.set()
            monitor_thread.join()

        return self.finished, self.failed


# --------------------------------------------------------------------------
# 5. Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":

    # All demo notebooks, sorted by name
    notebooks_dir = HOME / "notebooks"
    files = sorted(
        p
        for p in notebooks_dir.rglob("*.ipynb")
        if p.is_file() and ".ipynb_checkpoints" not in p.parts
    )
    notebooks = [Notebook(f) for f in files]

    # Ignore these notebooks
    with open("/scripts/ignored-notebooks.txt") as file:
        all_ignored = [line.strip() for line in file]  # these lines have wildcards
    # Only keep these which are actual notebook relative paths, with wildcard matching
    relatives = [n.relative for n in notebooks]
    ignored = sum(
        [fnmatch.filter(relatives, i) for i in all_ignored], []
    )  # sum will flatten the 2D list
    notebooks = [n for n in notebooks if n.relative not in ignored]

    runner = PoolRunner(max_workers=MAX_WORKERS, status_interval=STATUS_INTERVAL)
    finished, failed = runner.run(notebooks)

    print("\n=== FINAL SUMMARY ===")
    print(f"Finished ({len(finished)}): {print_bullet(finished)}")
    print(f"Ignored ({len(ignored)}): {print_bullet(ignored)}")
    print(f"Failed   ({len(failed)}): {print_bullet(failed)}")
