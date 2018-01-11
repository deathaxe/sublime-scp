import os
import re
import subprocess
import sys

import sublime

from .scpclient import SCPClient
from .scpclient import SCPException
from .scpclient import SCPNotConnectedError

connections = []


class SCPFolderError(SCPException):
    pass


def connect(path):
    try:
        return connection(path)
    except SCPNotConnectedError:
        try:
            if sys.platform == "win32":
                client = SCPFolder(path.lower())
            else:
                client = SCPFolder(path)
            connections.append(client)
            return client
        except SCPException:

            return False


def disconnect(path):
    try:
        while True:
            connections.remove(connection(path))
    except (IndexError, SCPException):
        pass


def connection(path):
    if path:
        p = path.lower() if sys.platform == "win32" else path
        for client in connections:
            if p.startswith(client.root):
                return client
    raise SCPNotConnectedError("No SCP connection for %s!" % path)


def is_connected(path):
    if path:
        p = path.lower() if sys.platform == "win32" else path
        for client in connections:
            if p.startswith(client.root):
                return True
    return False


def root_dir(file_name):
    if file_name:
        path, name = file_name, "."
        while path and name and name != ".scp":
            if path and os.path.exists(os.path.join(path, ".scp")):
                return path
            path, name = os.path.split(path)
    return False


class SCPFolder(SCPClient):

    def __init__(self, path):
        root = root_dir(path)
        if not root:
            raise SCPFolderError("Not within a mapped folder")
        with open(os.path.join(root, ".scp")) as file:
            client = sublime.decode_value(file.read())
            SCPClient.__init__(
                self,
                client["host"],
                client.get("port", 22),
                client.get("user", "guest"),
                client.get("passwd", None),
                client.get("hostkey", None),
                root
            )
            self.remote_path = client.get("path", "/")

    def to_remote_path(self, path):
        if self.is_root(path):
            return self.remote_path
        remote_path = os.path.join(
            self.remote_path, os.path.relpath(path, self.root)
        ).replace("\\", "/")
        if ".." in remote_path:
            raise ValueError("Invalid path!")
        return remote_path

    def relpath(self, path):
        return os.path.relpath(path, self.root)

    def is_root(self, path):
        return os.path.relpath(path, self.root) == '.'

    def is_child(self, path):
        return not self.relpath(path).startswith("..")

    def remove(self, path, listener):
        super().remove(self.to_remote_path(path), listener)

    def mkdir(self, path, listener):
        super().mkdir(self.to_remote_path(path), listener)

    def lsdir(self, path, listener):
        super().lsdir(self.to_remote_path(path), listener)

    def putfile(self, path, listener):
        super().putfile(path, self.to_remote_path(path), listener)

    def getfile(self, path, listener):
        super().getfile(self.to_remote_path(path), path, listener)

    def putdir(self, path, listener):
        parent = os.path.dirname(path)
        super().putdir(path, self.to_remote_path(parent), listener)

    def getdir(self, path, listener):
        parent = os.path.dirname(path)
        super().getdir(self.to_remote_path(path), parent, listener)

    def putpaths(self, paths, listener):
        """
        Put several folders and files to the remote host.

        The following steps are performed:
        1. The `paths` are grouped by single directories as a single `pscp`
           call has only one destination argument.
        2. The remote paths are created with a single mkdir command to ensure
           all destinations exist on the host before trying to copy files.
        3. The sub directories and files for each remote path are pushed
           separately as this is the way pscp can handle them only.
        """

        # group by remote path
        groups = {}
        for p in paths:
            if os.path.isfile(p):
                remote = self.to_remote_path(os.path.dirname(p))
            else:
                remote = self.to_remote_path(p)
            groups.setdefault(remote, []).append(self.relpath(p))

        # create remote directories
        super().mkdir([p for p in sorted(groups)], None)

        # push each directory to remote
        for remote, local in groups.items():
            super().putpaths(local, remote, listener)
