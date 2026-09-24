import functools


def write_command(method):
    """
    Decorator for the DeviceGUI methods that write to the device (setpoints, relays...).

    When the GUI has been created in read-only mode (self.read_only is True) the
    command is not sent and a warning is logged instead. The control widgets of a
    read-only GUI should also be disabled, this is the last line of defence.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if getattr(self, "read_only", False):
            self.logger.warning(f"Read-only mode: command '{method.__name__}' ignored")
            return None
        return method(self, *args, **kwargs)
    return wrapper
