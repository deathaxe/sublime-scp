import json
import os
import subprocess
import threading

import sublime
import sublime_plugin


def scp_root_dir(file_name):
    if file_name:
        path, name = file_name, "."
        while path and name and name != ".scp":
            if path and os.path.exists(os.path.join(path, ".scp")):
                return path
            path, name = os.path.split(path)
    return None


def call(args, on_done, on_error):

    def run():
        try:
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            else:
                startupinfo = None
            proc = subprocess.Popen(args=filter(None, args), stderr=subprocess.PIPE, startupinfo=startupinfo)
            proc.wait()
            error = proc.stderr.read().decode('utf-8').replace("\r", "").strip()
            if proc.returncode or error:
                raise ValueError("[Error %d] %s" % (proc.returncode, error))
            on_done()
        except Exception as e:
            on_error(e)

    threading.Thread(target=run).start()


class SCPClient:

    def __init__(self, path):

        self.plink = "plink.exe"
        self.pscp = "pscp.exe"

        self.root = scp_root_dir(path)
        if not self.root:
            raise ValueError("Not within a mapped folder")
        with open(os.path.join(self.root, ".scp")) as file:
            client = json.load(file)
            self.host = client["host"]
            self.port = client.get("port", 22)
            self.user = client.get("user", "guest")
            self.agent = client.get("agent", False)
            self.passwd = client.get("passwd", "")
            self.remote_path = client.get("path", "/")

    def to_remote_path(self, path):
        remote_path = os.path.join(
            self.remote_path, os.path.relpath(path, self.root)
        ).replace("\\", "/")
        if ".." in remote_path:
            raise ValueError("Invalid path!")
        return remote_path

    def to_scp_url(self, path):
        return "%s@%s:%s" % (self.user, self.host, self.to_remote_path(path))

    def auth(self):
        return ["-agent"] if self.agent else ["-pw", self.passwd]

    def execute(self, args, on_done, on_error):
        call([self.plink, "%s@%s:%d" % (self.user, self.host, self.port)] +
             self.auth() + args,
             on_done, on_error)

    def mkdir(self, path):
        def on_done():
            sublime.status_message("Created %s" % self.to_remote_path(path))

        def on_error(msg):
            sublime.error_message(msg)

        self.execute(["mkdir", "-p", self.to_remote_path(path)], on_done, on_error)

    def put(self, file_name):

        def on_done():
            sublime.status_message("Uploaded %s" % file_name)

        def on_error(msg):
            sublime.error_message(str(msg))

        call([self.pscp, "-scp", "-batch", "-q"] +
             self.auth() +
             [file_name, self.to_scp_url(file_name)],
             on_done, on_error)

    def get(self, file_name):

        def on_done():
            sublime.status_message("Downloaded %s" % file_name)

        def on_error(msg):
            sublime.error_message(msg)

        call([self.pscp, "-scp", "-batch", "-q"] +
             self.auth() +
             [self.to_scp_url(file_name), file_name],
             on_done, on_error)


class ScpMkFileDir(sublime_plugin.TextCommand):

    def is_enabled(self):
        return bool(scp_root_dir(self.view.file_name()))

    def run(self, edit):
        file_name = self.view.file_name()
        if file_name and os.path.isfile(file_name):
            try:
                path = os.path.dirname(file_name)
                client = SCPClient(path)
                client.mkdir(path)
            except Exception as error:
                sublime.error_message(str(error))


class ScpPutFile(sublime_plugin.TextCommand):

    def is_enabled(self):
        return bool(scp_root_dir(self.view.file_name()))

    def run(self, edit):
        file_name = self.view.file_name()
        if file_name and os.path.isfile(file_name):
            try:
                client = SCPClient(os.path.dirname(file_name))
                client.put(file_name)
            except Exception as error:
                sublime.error_message(str(error))


class ScpGetFile(sublime_plugin.TextCommand):

    def is_enabled(self):
        return bool(scp_root_dir(self.view.file_name()))

    def run(self, edit):
        file_name = self.view.file_name()
        if file_name and os.path.isfile(file_name):
            try:
                client = SCPClient(os.path.dirname(file_name))
                client.get(file_name)
            except Exception as error:
                sublime.error_message(str(error))


class ScpEventListener(sublime_plugin.EventListener):

    def on_post_save(self, view):
        if view.settings().get("scp_auto_upload"):
            view.run_command("scp_put_file")
