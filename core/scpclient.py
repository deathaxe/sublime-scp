import os
import re
import subprocess
import sys

import sublime
import sublime_plugin

from . import task

def exec(args):
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        startupinfo = None
    proc = subprocess.Popen(
        args=args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        universal_newlines=True)
    out, err = proc.communicate()
    return out, err, proc.returncode


class SCPCommandTask(task.TaskListener):

    def __init__(self, cmd, env=None, msg=None):
        super().__init__()
        self.msg = msg
        task.call(cmd, self, env)

    def on_start(self, proc):
        if self.msg:
            sys.stdout.write(self.msg)

    def on_finished(self, proc):
        msg = "Failed!" if proc.exit_code() else "Done!"
        print(msg)


class SCPLsDirTask(SCPCommandTask):

    def __init__(self, cmd, env=None):
        self.data = ""
        super().__init__(cmd, env)

    def on_data(self, proc, data):
        self.data += data

    def on_finished(self, proc):
        print(self.data)


class SCPCopyFileTask(SCPCommandTask):

    def on_finished(self, proc):
        msg = "Failed!" if proc.exit_code() else "Done!"
        print(msg)


class SCPCopyDirTask(SCPCommandTask):

    def __init__(self, cmd, env=None, msg=None):
        self.file = None
        super().__init__(cmd, env, msg)

    def on_start(self, proc):
        if self.msg:
            print(self.msg)

    def on_data(self, proc, data):
        """
        Parse scp's output to get current file name being transfered.

        Example:
        cp1250.py                 | 4 kB |   4.0 kB/s | ETA: 00:00:02 |  29%

        """
        # empty line
        if data in (None, '', '\n'):
            return

        file, _ = re.split(r'\s*\|\s*', data, 1)
        if file and file != self.file:
            if self.file:
                print("Done!")
            self.file = file
            sys.stdout.write("%s ... " % file)


class SCPClient(object):

    def __init__(self, host, port=22, user="guest", passwd=None):
        self.host = host
        self.port = port
        self.user = user
        self.pscp = ["pscp", "-scp", "-batch"]
        if passwd:
            self.pscp.extend(["-pw", passwd])
        self.plink = ["plink", "%s@%s:%d" % (user, host, port)]
        if passwd:
            self.plink.extend(["-pw", passwd])

        self.conn_time = self.server_time()
        if not self.conn_time:
            raise Exception("SCP connection failed!")

    def _to_scp_url(self, remote):
        return "%s@%s:%s" % (self.user, self.host, remote)

    def cancel(self):
        task.cancel_all()

    def server_time(self):
        args = self.plink + ["date"]
        out, err, ret = exec(args)
        if ret:
            return None
        return out

    def remove(self, remote):
        args = self.plink + ["rm", "-r", remote]
        msg = "SCP delete %s ... " % remote
        SCPCommandTask(args, msg=msg)

    def mkdir(self, remote):
        args = self.plink + ["mkdir", "-p", remote]
        msg = "SCP mkdir %s ... " % remote
        SCPCommandTask(args, msg=msg)

    def lsdir(self, remote):
        args = self.pscp + ["-ls", self._to_scp_url(remote)]
        SCPLsDirTask(args)

    def putdir(self, local, remote):
        args = self.pscp + ["-r", local, self._to_scp_url(remote)]
        msg = "SCP put %s --> %s ... " % (local, remote)
        SCPCopyDirTask(args, msg=msg)

    def getdir(self, remote, local):
        args = self.pscp + ["-r", self._to_scp_url(remote), local]
        msg = "SCP get %s --> %s ... " % (remote, local)
        SCPCopyDirTask(args, msg=msg)

    def putfile(self, local, remote):
        args = self.pscp + ["-q", local, self._to_scp_url(remote)]
        msg = "SCP put %s --> %s ... " % (local, remote)
        SCPCopyFileTask(args, msg=msg)

    def getfile(self, remote, local):
        args = self.pscp + ["-q", self._to_scp_url(remote), local]
        msg = "SCP get %s --> %s ... " % (remote, local)
        SCPCopyFileTask(args, msg=msg)
