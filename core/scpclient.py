import os
import re
import subprocess
import sys

import sublime
import sublime_plugin

from .proc import ProcessListener
from .proc import AsyncProcess


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


class SCPCopyFileProcess(AsyncProcess, ProcessListener):

    def __init__(self, cmd, env=None):
        AsyncProcess.__init__(self, cmd, self, env)

    def on_finished(self, proc):
        msg = "Failed!" if proc.exit_code() else "Done!"
        print(msg)


class SCPCopyDirProcess(SCPCopyFileProcess):

    def __init__(self, cmd, env=None):
        self.file = None
        SCPCopyFileProcess.__init__(self, cmd, env)

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


class SCPClient:

    def __init__(self, host, port=22, user="guest", passwd=None):
        self.proc = None
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
        if self.proc is not None:
            self.proc.kill()
            self.proc = None

    def server_time(self):
        args = self.plink + ["date"]
        out, err, ret = exec(args)
        if ret:
            return None
        return out

    def remove(self, remote):
        args = self.plink + ["rm", "-r", remote]
        sys.stdout.write("SCP delete %s ... " % remote)
        self.proc = SCPCopyDirProcess(args)

    def mkdir(self, remote):
        args = self.plink + ["mkdir", "-p", remote]
        sys.stdout.write("SCP mkdir %s ... " % remote)
        self.proc = SCPCopyDirProcess(args)

    def lsdir(self, remote):
        args = self.pscp + ["-ls", self._to_scp_url(remote)]
        out, err, ret = exec(args)
        return out

    def putdir(self, local, remote):
        args = self.pscp + ["-r", local, self._to_scp_url(remote)]
        sys.stdout.write("SCP put %s --> %s ... " % (local, remote))
        self.proc = SCPCopyDirProcess(args)

    def getdir(self, remote, local):
        args = self.pscp + ["-r", self._to_scp_url(remote), local]
        sys.stdout.write("SCP get %s --> %s ... " % (remote, local))
        self.proc = SCPCopyDirProcess(args)

    def putfile(self, local, remote):
        args = self.pscp + ["-q", local, self._to_scp_url(remote)]
        sys.stdout.write("SCP put %s --> %s ... " % (local, remote))
        self.proc = SCPCopyFileProcess(args)

    def getfile(self, remote, local):
        args = self.pscp + ["-q", self._to_scp_url(remote), local]
        sys.stdout.write("SCP get %s --> %s ... " % (remote, local))
        self.proc = SCPCopyFileProcess(args)
