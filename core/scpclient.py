import os
import re
import subprocess
import sys


class SCPException(Exception):
    pass


class SCPNotConnectedError(SCPException):
    pass


class SCPCommandError(SCPException):
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
        self._pscp = ["pscp", "-scp", "-batch"]
        self._plink = ["plink", "%s@%s:%d" % (user, host, port)]
        # add password to command line arguments
        if passwd:
            self._pscp.extend(["-pw", passwd])
            self._plink.extend(["-pw", passwd])
        # add hostkey to command line arguments
        self.hostkey = hostkey
        if hostkey not in (None, "", "*"):
            args = ["-hostkey", hostkey]
            self._pscp.extend(args)
            self._plink.extend(args)
        # connection test using sync silent task to read the server time
        while True:
            try:
                self.conn_time = self.plink("date")
                return
            except SCPCommandError as err:
                # try to find hostkey in error message
                match = re.search(r'((?:[0-9a-f]{2}:){15,}[0-9a-f]{2})', str(err))
                if not match:
                    raise SCPNotConnectedError("SCP: connection failed!")
                # hostkey auto-acceptance not set
                if self.hostkey != "*":
                    raise SCPNotConnectedError(
                        "SCP: invalid fingerprint %s!" % match.group(1))
                self.hostkey = match.group(1)
                print("SCP: using unknown host fingerprint", self.hostkey)
                args = ["-hostkey", self.hostkey]
                self._pscp.extend(args)
                self._plink.extend(args)

    def scp_url(self, remote):
        return "%s@%s:%s" % (self.user, self.host, remote)

    def exec(self, args):
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
        return proc.returncode, out, err

    def plink(self, *args):
        code, out, err = self.exec(self._plink + list(args))
        if code or err:
            raise SCPCommandError(err)
        return out

    def pscp(self, *args):
        code, out, err = self.exec(self._pscp + list(args))
        if code or err:
            raise SCPCommandError(err)

    def remove(self, remote):
        if isinstance(remote, str):
            return self.plink("rm -r %s" % remote)
        return self.plink(";".join(["rm -r %s" % r for r in remote]))

    def mkdir(self, remote):
        if isinstance(remote, str):
            return self.plink("mkdir -p %s" % remote)
        return self.plink(";".join(["mkdir -p %s" % r for r in remote]))

    def lsdir(self, remote):
        return self.pscp("-ls", self.scp_url(remote))

    def putfile(self, local, remote):
        return self.pscp("-q", local, self.scp_url(remote))

    def getfile(self, remote, local):
        return self.pscp("-q", self.scp_url(remote), local)
