# Consecutive failed reads that a device (or one of its channels) is allowed before
# the failure is reported. A single timeout every few hours is normal and solves
# itself, and at the usual read_loop_time this still reports a real outage in a
# few seconds. Configurable at run time from the advanced options menu.
DEFAULT_READ_FAILURES_TO_WARN = 3


class ReadFailureMixin:
    """
    Tolerance to transient read failures and alarm transitions logging for DeviceGUIs.

    Put it before DeviceGUI in the bases of the GUI class and call
    add_read_failures_config_param() from create_gui(), so that the number of
    tolerated failures shows up in the advanced options menu.
    """

    def add_read_failures_config_param(self, default=DEFAULT_READ_FAILURES_TO_WARN):
        # create_gui() is called by DeviceGUI.__init__ after config_params is built
        # and before the read loop starts, so this is where an extra parameter can
        # join the ones offered by the advanced options menu.
        self.config_params.setdefault("read_failures_to_warn", default)

    @property
    def read_failures(self):
        """Consecutive failed reads, per key (e.g. a channel name, None for the device)."""
        return self.__dict__.setdefault("_read_failures", {})

    def read_failures_to_warn(self):
        return max(1, int(self.config_params.get("read_failures_to_warn",
                                                 DEFAULT_READ_FAILURES_TO_WARN)))

    def handle_read_failure(self, key, message):
        """
        Count a failed read and report it only once it has persisted.

        The first failures are only recorded at debug level, where they do not reach
        the Slack/Mattermost handlers. Once the same key has failed
        'read_failures_to_warn' reads in a row the problem is real and gets logged as
        a warning, once, until it recovers.

        Returns True when the failure has lasted long enough to be published as a
        failed reading; while it returns False the caller keeps the last values.
        """
        failures = self.read_failures.get(key, 0) + 1
        self.read_failures[key] = failures
        to_warn = self.read_failures_to_warn()

        if failures < to_warn:
            self.logger.debug(f"{message} (failure {failures} of {to_warn}, tolerated)")
            return False
        if failures == to_warn:
            self.logger.warning(f"{message} (failed {failures} reads in a row)")
        else:
            self.logger.debug(message) # already warned about this one
        return True

    def handle_read_recovery(self, key, message):
        """Report a key that reads again, if it was warned about."""
        failures = self.read_failures.pop(key, 0)
        if failures >= self.read_failures_to_warn():
            self.logger.info(f"{message} after {failures} failed reads")
        elif failures:
            self.logger.debug(f"{message} after {failures} failed reads")

    def log_alarm_transition(self, was_active, active, raised_message, cleared_message):
        """
        Log an alarm that has just been raised (critical) or cleared (info).

        Only the transitions are logged: the critical records are forwarded to
        Slack/Mattermost, so logging on every read while an alarm is standing would
        flood those channels.
        """
        if bool(active) == bool(was_active):
            return
        if active:
            self.logger.critical(raised_message)
        else:
            self.logger.info(cleared_message)
