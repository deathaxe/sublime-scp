import traceback

from queue import Empty
from queue import Queue
from threading import Thread


class Task(object):

    """
    Task runs a python function `target` when called.
    """

    def __init__(self, target, *args):
        """Initialize the Task object."""
        self.target = target
        self.args = args

    def run(self):
        self.target(self, *self.args)


class TaskQueue(Thread):

    """
    A background thread to starts all queued processes one after another.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.queue = Queue()
        self.active_task = None

    def __del__(self):
        self.running = False

    def call(self, task):
        self.queue.put(task)

    def cancel_all(self):
        try:
            while not self.Empty():
                self.queue.get_nowait()
                self.queue.task_done()
        except Empty:
            pass

    def busy(self):
        result = False
        with self._block:
            result = self.active_task is not None
        return result

    def run(self):
        self.running = True
        while self.running:
            task = self.queue.get()
            with self._block:
                self.active_task = task
            try:
                task.run()
            except:
                traceback.print_exc()
            finally:
                self.queue.task_done()
                with self._block:
                    self.active_task = None


## [ default task queue ] ####################################################


_tasks = TaskQueue()
_tasks.start()


def busy():
    return _tasks.busy()


def call_task(task):
    _tasks.call(task)
    return task


def call_func(func, *args):
    return call_task(Task(func, *args))


def cancel_all():
    _tasks.cancel_all()
