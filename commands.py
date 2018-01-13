import os
import tarfile
import tempfile
import threading

import sublime
import sublime_plugin

from .core import commonpath
from .core import scpfolder
from .core import task
from .core.progress import Progress

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

    def run(self, paths=None):
        task.call_func(self.executor, self.ensure_paths(paths))

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
        self.thread = task.call_func(self.executor, self.ensure_paths(paths))

    def executor(self, task, paths, on_data):
        with Progress("Connecting...") as progress:
            if all(scpfolder.connect(path) for path in paths):
                progress.done("SCP: connected!")
            else:
                progress.done("SCP: Connection failed!")
        self.thread = None


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

    def executor(self, task, paths, on_data):
        dirnames = set()
        for path in paths:
            self.get(path)

    def get(self, path):
        try:
            if os.path.isfile(path):
                # ensure local directory exists if the first file
                # of a directory is copied
                dirname = os.path.dirname(path)
                if dirname not in dirnames:
                    dirnames.add(dirname)
                    os.makedirs(dirname, exist_ok=True)
                scpfolder.connection(path).getfile(path)
            else:
                # todo: use gettree via tar
                scpfolder.connection(path).getdir(path)
        except scpfolder.SCPNotConnectedError:
            pass


class ScpPutCommand(_ScpWindowCommand):

    def executor(self, task, paths, on_data):
        groups = {}
        for path in paths:
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

        for conn, paths in groups.items():
            if len(paths) == 1 and os.path.isfile(paths[0]):
                # use simple upload for single files
                conn.putfile(paths[0])
                msg = "SCP: %s pushed!" % paths[0]
                print(msg)
                sublime.status_message(msg)
            else:
                # use tarfile upload for multiple files and dirs
                self.puttree(conn, paths)

    def puttree(self, conn, paths):
        """
        Put several folders and files to the remote host.

        Uploading many files via scp is horribly slow. To work around that
        the following steps are performed:
        1. Pack all files given via `paths` into a single tar-file with
           relative paths based on the mapped folder.
        2. Upload the tar-file to the remote's /tmp/ folder.
        3. Untar the file on the remote host and delete it.
        """
        source_dir = commonpath.most(paths)
        target_dir = conn.to_remote_path(source_dir)

        # built temporary local tar-file
        file, local_tmp = tempfile.mkstemp(prefix="scp_")
        os.close(file)

        with tarfile.open(local_tmp, "w") as tar:

            def tarfilter(tarinfo):
                tarinfo.uid = tarinfo.gid = 0
                tarinfo.uname = tarinfo.gname = "root"
                return tarinfo

            for path in paths:
                tar.add(
                    path,
                    arcname=os.path.relpath(path, source_dir),
                    filter=tarfilter
                )

        try:
            # upload using pscp
            remote_tmp = "/tmp/" + os.path.basename(local_tmp)
            super(conn.__class__, conn).putfile(local_tmp, remote_tmp)
            # untar on remote host
            conn.plink(
                "tar -C {0} -xf {1}; rm {1}".format(target_dir, remote_tmp))

            msg = "SCP: %s pushed!" % source_dir
            print(msg)
            sublime.status_message(msg)

        finally:
            # remove local archive
            os.remove(local_tmp)


class ScpDelCommand(_ScpWindowCommand):

    def executor(self, task, paths, on_data):
        for path in paths:
            try:
                scpfolder.connection(path).remove(path)
            except scpfolder.SCPNotConnectedError:
                pass


class ScpEventListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        view.window().run_command("scp_put")
