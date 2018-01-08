import os
import re
import subprocess
import sys

from . import task

class SCPException(Exception):
    pass


class SCPNotConnectedError(SCPException):
    pass


class SCPClient(object):

    def __init__(self, host, port=22, user=None, passwd=None, hostkey=None, root=None):
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
        self.plink = ["plink", "%s@%s:%d" % (user, host, port)]
        # add password to command line arguments
        if passwd:
            self.pscp.extend(["-pw", passwd])
            self.plink.extend(["-pw", passwd])
        # add hostkey to command line arguments
        self.hostkey = hostkey
        if hostkey not in (None, "", "*"):
            args = ["-hostkey", hostkey]
            self.pscp.extend(args)
            self.plink.extend(args)
        # connection test using sync silent task to read the server time
        conn = task.Task(self.plink + ["date"])
        while True:
            conn.run()
            # got time
            self.conn_time = conn.proc.stdout.read()
            if self.conn_time:
                return True
            # check error message
            error_message = conn.proc.stderr.read()
            if not error_message:
                raise SCPNotConnectedError("SCP connection failed!")
            # try to find hostkey in error message
            match = re.search(
                r'((?:[0-9a-f]{2}:){15,}[0-9a-f]{2})', error_message)
            if not match:
                raise SCPNotConnectedError("SCP connection failed!")
            # hostkey auto-acceptance not set
            if self.hostkey != "*":
                raise SCPNotConnectedError(
                    "SCP invalid fingerprint %s!" % match.group(1))
            self.hostkey = match.group(1)
            print("SCP using unknown host fingerprint", self.hostkey)
            args = ["-hostkey", self.hostkey]
            self.pscp.extend(args)
            self.plink.extend(args)
            conn.cmd = self.plink + ["date"]

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
