import os
import threading
import tarfile
import tempfile

import sublime
import sublime_plugin

from .core import scpfolder
from .core.progress import Progress
from .core import task
from .core.display import (
        SCPCopyDirListener,
        SCPCopyFileListener,
        SCPCopyTarListener,
        SCPLsDirListener,
        SCPMkDirListener,
        SCPRemoveListener
    )

TEMPLATE = """
{
    // remote host name or IP address
    "host": "192.168.0.1",
    "port": 22,
    "user": "guest",
    "passwd": "guest",
    // remote path to use as root
    "path": "/home/guest"
}
""".lstrip()


class _ScpWindowCommand(sublime_plugin.WindowCommand):

    def is_visible(self, paths=None):
        """Menu item is visible, if connection is established."""
        return any(
            scpfolder.is_connected(path)
            for path in self.ensure_paths(paths)
        )

    def ensure_paths(self, paths):
        """If no path was provided, use active view's file name."""
        if paths:
            return paths
        view = self.window.active_view()
        name = view.file_name() if view else None
        return [name] if name and os.path.exists(name) else []


class ScpMapToRemoteCommand(_ScpWindowCommand):

    def is_visible(self, paths=None):
        """Menu is visible if no mapping exists already."""
        return not any(
            scpfolder.root_dir(path)
            for path in self.ensure_paths(paths)
        )

    def run(self, paths=None):
        for path in self.ensure_paths(paths):
            self.window.run_command("open_file", {
                "file": os.path.join(path, ".scp"), "contents": TEMPLATE})
            self.window.active_view().assign_syntax("JSON.sublime-syntax")


class ScpConnectCommand(_ScpWindowCommand):

    def __init__(self, window):
        super().__init__(window)
        self.thread = None

    def is_enabled(self, paths=None):
        """Disable command while connection is being established."""
        return not self.thread

    def is_visible(self, paths=None):
        """Menu item is visible if mapping exists but offline."""
        return any(
            scpfolder.root_dir(path) and not scpfolder.is_connected(path)
            for path in self.ensure_paths(paths)
        )

    def run(self, paths=None):

        def executor():
            with Progress("Connecting...") as progress:
                if all(scpfolder.connect(path) for path in self.ensure_paths(paths)):
                    progress.done("SCP: connected!")
                else:
                    progress.done("SCP: Connection failed!")
            self.thread = None

        self.thread = threading.Thread(target=executor)
        self.thread.start()


class ScpDisconnectCommand(_ScpWindowCommand):

    def run(self, paths=None):
        for path in self.ensure_paths(paths):
            scpfolder.disconnect(path)


class ScpCancelCommand(_ScpWindowCommand):

    def is_enabled(self, paths=None):
        """Enable command if an operation is in progress."""
        return task.busy()

    def run(self, paths=None):
        """Abort all queued and active opera"""
        task.cancel_all()


class ScpGetCommand(_ScpWindowCommand):

    def run(self, paths=None):
        file_listener = SCPCopyFileListener()
        dir_listener = SCPCopyDirListener()
        dirnames = set()

        for path in self.ensure_paths(paths):
            try:
                if os.path.isfile(path):
                    # ensure local directory exists if the first file
                    # of a directory is copied
                    dirname = os.path.dirname(path)
                    if dirname not in dirnames:
                        dirnames.add(dirname)
                        os.makedirs(dirname, exist_ok=True)
                    scpfolder.connection(path).getfile(path, file_listener)
                else:
                    scpfolder.connection(path).getdir(path, dir_listener)
            except scpfolder.SCPNotConnectedError:
                pass
            except Exception as error:
                sublime.error_message(str(error))


class ScpPutCommand(_ScpWindowCommand):

    def run(self, paths=None):
        groups = {}
        for path in self.ensure_paths(paths):
            # simple ignored handling to protect some special dirs/files
            if os.path.basename(path) in ('.scp', '.git'):
                continue
            try:
                conn = scpfolder.connection(path)
                if conn.is_root(path):
                    files = (
                        os.path.join(path, f)
                        for f in os.listdir(path)
                        if f not in ('.', '..', '.scp', '.git')
                    )
                    groups.setdefault(conn, []).extend(files)
                else:
                    groups.setdefault(conn, []).append(path)
            except scpfolder.SCPNotConnectedError:
                pass

        def tarfilter(tarinfo):
            tarinfo.uid = tarinfo.gid = 0
            tarinfo.uname = tarinfo.gname = "root"
            return tarinfo

        listener = SCPCopyFileListener()
        for conn, paths in groups.items():

            file, tmpfile = tempfile.mkstemp(prefix='scp_')
            os.close(file)

            with tarfile.open(tmpfile, "w:gz") as tar:
                for path in paths:
                    tar.add(path, arcname=os.path.relpath(path, conn.root), filter=tarfilter)
            conn.puttar(tmpfile, listener)


class ScpDelCommand(_ScpWindowCommand):

    def run(self, paths=None):
        remove_listener = SCPRemoveListener()
        for path in self.ensure_paths(paths):
            try:
                scpfolder.connection(path).remove(path, remove_listener)
            except scpfolder.SCPNotConnectedError:
                pass
            except Exception as error:
                sublime.error_message(str(error))


class ScpEventListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        view.window().run_command("scp_put")
