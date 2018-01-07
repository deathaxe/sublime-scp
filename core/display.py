import re
import sys

from . import task


class SCPTaskListener(task.TaskListener):
    """
    The basic SCP task listener class.

    Runs within the TaskQueue thread context.
    """

    def on_finished(self, task):
        msg = "Failed!" if task.exit_code() else "OK"
        print(msg)


class SCPCopyDirListener(SCPTaskListener):
    """
    The SCP copy directory listener class.

    Runs within the TaskQueue thread context.
    """

    def __init__(self):
        self.file = None
        super().__init__()

    def on_start(self, task):
        msg = "SCP copy %s --> %s ... " % (task.cmd[-2], task.cmd[-1])
        print(msg)

    def on_data(self, task, data):
        """
        Parse scp's output to get current file name being transfered.

        Example:
        cp1250.py                 | 4 kB |   4.0 kB/s | ETA: 00:00:02 |  29%

        """
        # empty line
        if data in (None, '', '\n'):
            return

        file, _ = re.split(r'\s*\|\s*', data, 1)
        if file and file != self.file:
            if self.file:
                print("Done!")
            self.file = file
            sys.stdout.write("%s ... " % file)


class SCPCopyFileListener(SCPTaskListener):
    """
    The SCP copy single file listener class.

    Runs within the TaskQueue thread context.
    """

    def on_start(self, task):
        msg = "SCP copy %s --> %s ... " % (task.cmd[-2], task.cmd[-1])
        sys.stdout.write(msg)


class SCPLsDirListener(SCPTaskListener):
    """
    The SCP list directory listener class.

    Runs within the TaskQueue thread context.
    """

    def __init__(self):
        super().__init__()
        self.data = ""

    def on_data(self, task, data):
        self.data += data

    def on_finished(self, task):
        print(self.data)


class SCPMkDirListener(SCPTaskListener):
    """
    The SCP make remote path listener class.

    Runs within the TaskQueue thread context.
    """

    def on_start(self, task):
        msg = "SCP mkdir %s ... " % task.cmd[-1]
        sys.stdout.write(msg)


class SCPRemoveListener(SCPTaskListener):
    """
    The SCP remove remote path listener class.

    Runs within the TaskQueue thread context.
    """

    def on_start(self, task):
        msg = "SCP remove %s ... " % task.cmd[-1]
        sys.stdout.write(msg)
