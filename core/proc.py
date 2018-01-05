import os
import subprocess
import sys
import threading


class ProcessListener(object):

    def on_data(self, proc, data):
        pass

    def on_error(self, proc, data):
        pass

    def on_finished(self, proc):
        pass


class AsyncProcess(object):
    """
    Encapsulates subprocess.Popen, forwarding stdout to a supplied
    ProcessListener (on a separate thread)
    """

    def __init__(self, cmd, listener=None, env=None):

        self.listener = listener

        # Hide the console window on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        if env:
            proc_env = os.environ.copy()
            proc_env.update(env)
            for k, v in proc_env.items():
                proc_env[k] = os.path.expandvars(v)
        else:
            proc_env = None

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            startupinfo=startupinfo,
            env=proc_env,
            universal_newlines=True)

        if self.listener:
            if self.proc.stdout:
                threading.Thread(target=self.read_stdout).start()

            if self.proc.stderr:
                threading.Thread(target=self.read_stderr).start()

    def kill(self):
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

    def read_stdout(self):
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

    def read_stderr(self):
        try:
            online = True
            while online:
                data = self.proc.stderr.readline(2**16)
                online = bool(data)
                if online:
                    self.listener.on_error(self, data)
        finally:
            self.proc.stderr.close()
