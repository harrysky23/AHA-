"""Track owned descendants by PID + creation time, including detached Chrome."""
import os
import signal
import threading
import time

import psutil


class ProcessTree:
    def __init__(self, pid):
        self.pid = pid
        self.known = {}
        try:
            self.root = psutil.Process(pid)
        except psutil.NoSuchProcess:
            self.root = None

    def capture(self):
        if self.root is None:
            return
        try:
            for process in [self.root, *self.root.children(recursive=True)]:
                self.known[(process.pid, process.create_time())] = process
        except psutil.NoSuchProcess:
            pass

    def stop(self):
        # Freeze the parent before discovering/killing children so it cannot
        # launch another FFmpeg/browser between discovery and termination.
        if self.root is not None and self.root.pid != os.getpid():
            try:
                self.root.suspend()
            except psutil.NoSuchProcess:
                pass
        for _ in range(5):
            count = len(self.known)
            self.capture()
            for process in self.known.values():
                if process.pid != os.getpid():
                    try:
                        process.suspend()
                    except psutil.NoSuchProcess:
                        pass
            if len(self.known) == count:
                break
        for process in reversed(list(self.known.values())):
            try:
                process.kill()  # psutil checks PID reuse before sending signals.
            except psutil.NoSuchProcess:
                pass
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _, alive = psutil.wait_procs(list(self.known.values()), timeout=3)
        return not any(p.is_running() and p.status() != psutil.STATUS_ZOMBIE for p in alive)


def watch_parent(parent_pid: int):
    """Stop owned descendants after abrupt API/CLI parent death (including macOS)."""
    def watch():
        tree = ProcessTree(os.getpid())
        while True:
            tree.capture()
            if os.getppid() != parent_pid:
                tree.stop()
                os._exit(1)
            time.sleep(.2)
    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread
