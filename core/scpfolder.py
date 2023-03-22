import os
import re
import sys

from fnmatch import fnmatch

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
                root,
            )
            self.remote_dir = client.get("dir", "/")
            self.files_pattern = client.get("files", [])
            self.dirs_mapping = client.get("dirmap", {})
            self.path_map = client.get("mappings", [])
            self.debug = client.get("debug", False)

    def to_remote_path(self, path):
        rel_path = self.relpath(path)
        if rel_path.startswith(".."):
            raise ValueError("Invalid path!")

        if self.debug:
            print(path, "-->", rel_path)

        rel_path = rel_path.replace("\\", "/")

        if os.path.isfile(path):
            if not any(fnmatch(rel_path, p) for p in self.files_pattern):
                raise ValueError("Not a handled file!")
            dirname, filename = os.path.split(rel_path)
        else:
            dirname, filename = rel_path, ""
        for source, target in self.dirs_mapping.items():
            if re.match(source, dirname):
                result = re.sub(source, target, rel_path)
                result = os.path.normpath(os.path.join(self.remote_dir, result, filename))
                result = result.replace("\\", "/")
                if self.debug:
                    print("  ->", result)
                return result

        # path not found in dirmap, don't translate path
        result = os.path.normpath(os.path.join(self.remote_dir, rel_path))
        result = result.replace("\\", "/")
        if self.debug:
            print("  ==", result)
        return result

    def relpath(self, path):
        return os.path.relpath(path, self.root)

    def is_root(self, path):
        return self.relpath(path) == "."

    def is_child(self, path):
        return not self.relpath(path).startswith("..")

    def rename(self, path, newpath):
        return super().rename(self.to_remote_path(path), self.to_remote_path(newpath))

    def remove(self, path):
        return super().remove(self.to_remote_path(path))

    def mkdir(self, path):
        return super().mkdir(self.to_remote_path(path))

    def lsdir(self, path):
        return super().lsdir(self.to_remote_path(path))

    def putfile(self, path):
        return super().putfile(path, self.to_remote_path(path))

    def getfile(self, path):
        return super().getfile(self.to_remote_path(path), path)
