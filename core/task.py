import os
import queue
import subprocess
import sys
import threading


class TaskListener(object):

    def on_start(self, task):
        """Task process is started."""
        pass

    def on_data(self, task, data):
        """Got data from stdout."""
        pass

    def on_finished(self, task):
        """Task process finished."""
        pass


class BaseTask(object):

    def run(self):
        pass

    def kill(self):
        pass

    def poll(self):
        pass

    def exit_code(self):
        pass

    def send(self, data):
        pass


class FuncTask(BaseTask):

    """
    FuncTask runs a python function `target` when called.
    """

    def __init__(self, target, *args, listener=None):
        """Initialize the FuncTask object."""
        assert target
        self.target = target
        self.args = args
        self.listener = listener
        self.result = None

    def run(self):
        if self.listener:
            self.listener.on_start(self)

            def on_data(data):
                self.listener.on_data(self, data)
            self.result = self.target(self, *self.args, on_data=on_data)
            self.listener.on_finished(self)
        else:
            def on_data(data):
                pass
            self.result = self.target(self, *self.args, on_data=on_data)

    def poll(self):
        return self.result is None

    def exit_code(self):
        return self.result


class ProcTask(BaseTask):

    """
    Task is a class to encapsulate a queued subprocess call.
    It is designed to be run from within the TaskQueue thread.
    """

    def __init__(self, cmd, listener=None, cwd=None, env=None):
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.listener = listener
        self.proc = None

    def run(self):
        # Hide the console window on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        if self.env:
            proc_env = os.environ.copy()
            proc_env.update(self.env)
            for k, v in proc_env.items():
                proc_env[k] = os.path.expandvars(v)
        else:
            proc_env = None

        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            cwd=self.cwd,
            env=proc_env,
            universal_newlines=True)

        if not self.listener:
            return self.exit_code()

        self.listener.on_start(self)

        try:
            online = True
            while online:
                data = self.proc.stdout.readline(2**16)
                online = bool(data)
                if online:
                    self.listener.on_data(self, data)
        finally:
            self.proc.stdout.close()
            self.listener.on_finished(self)

    def kill(self):
        if not self.proc:
            return 0
        self.proc.terminate()
        return self.exit_code()

    def poll(self):
        return self.proc.poll() is None

    def exit_code(self):
        self.proc.wait()
        return self.proc.returncode

    def send(self, data):
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except BrokenPipeError as err:
            self.kill()


class TaskQueue(threading.Thread):

    """
    A background thread to starts all queued processes one after another.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.queue = queue.Queue()
        self.active_task = None

    def __del__(self):
        self.running = False

    def call(self, task):
        self.queue.put(task)

    def cancel_all(self):
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
        except queue.Empty:
            pass
        with self._block:
            if self.active_task:
                self.active_task.kill()

    def busy(self):
        result = False
        with self._block:
            result = self.active_task is not None
        return result

    def run(self):
        self.running = True
        while self.running:
            task = self.queue.get()
            with self._block:
                self.active_task = task
            try:
                task.run()
            finally:
                self.queue.task_done()
                with self._block:
                    self.active_task = None


## [ default task queue ] ####################################################


_tasks = TaskQueue()
_tasks.start()


def busy():
    return _tasks.busy()


def call_task(task):
    _tasks.call(task)
    return task


def call_func(func, *args, listener=None):
    return call_task(FuncTask(func, *args, listener=listener))


def call_proc(cmd, listener=None, cwd=None, env=None):
    return call_task(ProcTask(cmd, listener, cwd, env))


def cancel_all():
    _tasks.cancel_all()


