import os
import subprocess
import sys

from . import task

class SCPException(Exception):
    pass


class SCPNotConnectedError(SCPException):
    pass


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

        # connection test using sync silent task to read the server time
        if task.Task(self.plink + ["date"]).run() != 0:
            raise SCPNotConnectedError("SCP connection failed!")

    def scp_url(self, remote):
        return "%s@%s:%s" % (self.user, self.host, remote)

    def remove(self, remote, listener):
        if isinstance(remote, str):
            remote = [remote]
        args = self.plink + ["rm -r %s;" % r for r in remote]
        task.call(args, listener, self.root)

    def mkdir(self, remote, listener):
        if isinstance(remote, str):
            remote = [remote]
        args = self.plink + ["mkdir -p %s;" % r for r in remote]
        task.call(args, listener, self.root)

    def lsdir(self, remote, listener):
        args = self.pscp + ["-ls", self.scp_url(remote)]
        task.call(args, listener, self.root)

    def putdir(self, local, remote, listener):
        args = self.pscp + ["-r", local, self.scp_url(remote)]
        task.call(args, listener, self.root)

    def getdir(self, remote, local, listener):
        args = self.pscp + ["-r", self.scp_url(remote), local]
        task.call(args, listener, self.root)

    def putfile(self, local, remote, listener):
        args = self.pscp + ["-q", local, self.scp_url(remote)]
        task.call(args, listener, self.root)

    def getfile(self, remote, local, listener):
        args = self.pscp + ["-q", self.scp_url(remote), local]
        task.call(args, listener, self.root)

    def putpaths(self, paths, remote, listener):
        """Copy a list of local files and directories to server.

        Arguments:
            path (iterable):
                An iterable with the paths of all
                local files and dirs to copy.
            remote (string):
                The destination remote directory path
                to copy all files ad dirs to.
            listener (TaskListener):
                An callback class which displays
                the output of the SCP process.
        """
        args = self.pscp + ["-r"] + paths + [self.scp_url(remote)]
        task.call(args, listener, self.root)
