"""Log handling for qCamera."""

import sys
import logging
try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    colorama = None

logger = logging.getLogger('qCamera')
gui_logger = logging.getLogger('GUI')


class LogFormatter(logging.Formatter):
    """Formatter for use with qCamera's logging facilities."""
    DEFAULT_FORMAT = \
        '%(color)s[%(asctime)s] %(levelname)s : %(name)s : %(message)s'
    DEFAULT_COLORS = {
        logging.INFO: 0,  # white
        logging.WARNING: 3,  # yellow
        logging.ERROR: 1,  # red
        logging.DEBUG: 6  # cyan
    }

    def __init__(self, fmt=DEFAULT_FORMAT, colors=DEFAULT_COLORS):
        """Configure a new log formatter.

        Parameters
        ----------
        fmt : str
            Specifies the formatting for the log. Use ``%(color)s`` to
            specify the color to use if you have colorama_ installed.
        colors : dict
            Specifies colors to use for different logging levels. Keys
            should be ``logging`` module constants indicating the
            level (e.g., ``logging.DEBUG``) and values can be any
            valid colorama color specifier.

        .. _colorama: https://pypi.python.org/pypi/colorama

        """
        assert isinstance(fmt, str)
        assert isinstance(colors, dict)

        logging.Formatter.__init__(self)
        self.fmt = fmt
        if colors and colorama:
            self.colors = {levelno: colors[levelno] for levelno in colors}
        else:
            self.colors = {}

    def format(self, record):
        message = record.getMessage()
        record.message = message
        record.asctime = self.formatTime(record)
        if record.levelno in self.colors:
            record.color = self.colors[record.levelno]
        else:
            record.color = ''
        formatted = self.fmt % record.__dict__
        return formatted


def setup_logging(log, level=logging.INFO, stream=True, file=False, color=True):
    """Configure logging with default formatting.

    Keyword arguments
    -----------------
    level : int
        Log level to use.
    stream : bool
        Write logs to a stream.
    file: bool
        TODO: Write logs to a file.
    color : bool
        TODO: Try to use colored output if possible for stream handlers.

    """
    assert level in [0, 10, 20, 30, 40, 50]
    if stream:
        handler = logging.StreamHandler(sys.stdout)
        formatter = LogFormatter()
        handler.setFormatter(formatter)
        log.addHandler(handler)
        log.setLevel(level)
    if file:
        pass  # TODO

if __name__ == "__main__":
    pass
