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
        self.proc = None  # active process
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
        return subprocess.Popen(
            args=args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            universal_newlines=True)

    def plink(self, *args):
        """Run remote shell command using plink.

        :param args:
            The command line to execute on the remote host.

        :returns:
            The output of the command execution.

        :raises:
            `CalledProcessError` if an error occured with executing plink.
            `SCPCommandError` if plink returns nonzero exit code or
            stdout is empty but stderr contains error message.
        """
        try:
            self.proc = self.exec(self._plink + list(args))
            out, err = self.proc.communicate()
            if self.proc.returncode or err and not out:
                raise SCPCommandError(err)
            return out
        finally:
            self.proc = None

    def pscp(self, *args, on_progress=None):
        """Run a pscp command.

        :param args:
            The `source` files/paths and the `destination`

        :raises:
            `CalledProcessError` if an error occured with executing plink.
            `SCPCommandError` if pscp returns nonzero exit code.
        """
        try:
            self.proc = self.exec(self._pscp + list(args))
            if callable(on_progress):
                while True:
                    data = self.proc.stdout.readline(2**16)
                    if not bool(data):
                        return

                    # Parse scp's output to get current file name being transfered.
                    # cp1250.py   | 4 kB |   4.0 kB/s | ETA: 00:00:02 |  29%
                    try:
                        file, percent = re.match(r'\s*(\w+).+?(\d+)%', data).groups()
                    except (AttributeError, ValueError):
                        pass
                    else:
                        on_progress(file, percent)

            self.proc.wait()
            if self.proc.returncode:
                raise SCPCommandError(self.proc.stderr.read())

        finally:
            self.proc = None

    def abort(self):
        if self.proc:
            self.proc.terminate()

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

    def putfile(self, local, remote, on_progress=None):
        self.pscp(local, self.scp_url(remote), on_progress=on_progress)

    def getfile(self, remote, local, on_progress=None):
        self.pscp(self.scp_url(remote), local, on_progress=on_progress)
