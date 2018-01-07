import subprocess
import sys

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


class SCPClient(object):

    def __init__(self, host, port=22, user="guest", passwd=None, root=None):
        """Initialize an SCPClient object.

        Arguments:
            host (string):
                The SSH/SCP host to connect to
            port (int):
                The port to use for connection (default: 22)
            user (string):
                The user name to use for connection (default "guest")
            passwd (string):
                The optional password to use for connection
            root (string):
                The local root directory for all operations, which is used as
                working directory and base for all relative path calulations.
        """
        self.root = root
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

    def server_time(self):
        args = self.plink + ["date"]
        out, err, ret = exec(args)
        if ret:
            return None
        return out

    def remove(self, remote, listener):
        args = self.plink + ["rm", "-r", remote]
        task.call(args, listener, self.root)

    def mkdir(self, remote, listener):
        args = self.plink + ["mkdir", "-p", remote]
        task.call(args, listener, self.root)

    def lsdir(self, remote, listener):
        args = self.pscp + ["-ls", self._to_scp_url(remote)]
        task.call(args, listener, self.root)

    def putdir(self, local, remote, listener):
        args = self.pscp + ["-r", local, self._to_scp_url(remote)]
        task.call(args, listener, self.root)

    def getdir(self, remote, local, listener):
        args = self.pscp + ["-r", self._to_scp_url(remote), local]
        task.call(args, listener, self.root)

    def putfile(self, local, remote, listener):
        args = self.pscp + ["-q", local, self._to_scp_url(remote)]
        task.call(args, listener, self.root)

    def getfile(self, remote, local, listener):
        args = self.pscp + ["-q", self._to_scp_url(remote), local]
        task.call(args, listener, self.root)
