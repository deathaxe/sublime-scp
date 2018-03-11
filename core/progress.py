import sublime

class Progress(object):

    def __init__(self, message):
        self.message = message
        self.addend = 1
        self.size = 8
        self.last_view = None
        self.window = None
        self.running = False

    def __enter__(self):
        """Start progress bar."""
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        """Stop progress bar."""
        self.running = False

    def start(self):
        sublime.set_timeout(lambda: self._update(0), 100)
        self.running = True

    def done(self, message):
        """Stop and print finalization message."""
        self.running = False
        self._paint(message)
        sublime.set_timeout(lambda: self._paint(None), 2000)

    def _update(self, i):
        """Update busy indicator and paint it."""
        if not self.running:
            return

        before = i % self.size
        after = (self.size - 1) - before

        self._paint('[%s➖%s] %s' % (' ' * before, ' ' * after, self.message))

        if not after:
            self.addend = -1
        if not before:
            self.addend = 1
        i += self.addend

        sublime.set_timeout(lambda: self._update(i), 100)

    def _paint(self, message):
        """Paint the status bar text."""

        if self.window is None:
            self.window = sublime.active_window()
        active_view = self.window.active_view()

        if self.last_view is not None and active_view != self.last_view:
            self.last_view.erase_status('_scp')
            self.last_view = None

        if message:
            active_view.set_status('_scp', message)
        else:
            active_view.erase_status('_scp')

        if self.last_view is None:
            self.last_view = active_view
