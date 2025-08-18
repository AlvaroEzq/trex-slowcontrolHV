import datetime as dt
import os
import logging
import queue
import threading
import requests
import json

LOG_DIR = "logs"
SLACK_WEBHOOK_URL = "" # add here the webkook url
MATTERMOST_WEBHOOK_URL = ""

def create_directory_recursive(path):
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        print(f"Error occurred while creating directory '{path}': {e}")

def get_path_from_date(dt_obj):
    return LOG_DIR + "/" + dt_obj.strftime("%Y/%m/%d")
def get_full_filename_from_date(dt_obj, suffix="", extension="dat"):
    path = get_path_from_date(dt_obj)
    return f"{path}/{dt_obj.strftime('%Y%m%d')}_{suffix}.{extension}"

class ThreadedHandler(logging.Handler):
    def __init__(self):
        self.log_queue = queue.Queue()
        super().__init__()
        self.worker = threading.Thread(target=self._process_queue)
        self.worker.daemon = True  # Ensures the thread exits with the main program
        self.worker.start()

    def emit(self, record):
        # Add the log record to the queue
        self.log_queue.put(record)

    def logging_logic(self, log_message):
        raise NotImplementedError

    def _process_queue(self):
        while True:
            log_message = self.log_queue.get()
            if log_message is None:  # Sentinel to shut down the thread
                break
            self.logging_logic(log_message)

    def close(self):
        self.log_queue.put(None)  # Send sentinel
        self.worker.join()  # Wait for the thread to finish
        super().close()

class SlackHandler(ThreadedHandler):

    LEVEL_EMOJIS = {
        logging.DEBUG: ":bug:",
        logging.INFO: ":information_source:",
        logging.WARNING: ":warning:",
        logging.ERROR: ":red_circle::exclamation:",
        logging.CRITICAL: ":rotating_light::exclamation:"
    }

    def __init__(self, webhook_url:str):
        super().__init__()
        self.webhook_url = webhook_url
    
    def logging_logic(self, record):
        try:
            # Enviar mensaje a Slack
            message = record.getMessage()
            log_level = record.levelno
            emoji = self.LEVEL_EMOJIS.get(log_level, "") + " "
            slack_data = {'text': f"{emoji}{message}"}
            requests.post(self.webhook_url, data=json.dumps(slack_data), headers={'Content-Type': 'application/json'})
        except Exception as e:
            print(e)
    """
    def __repr__(self):
        return f"{self.__class__.__name__}({self.webhook_url})"
    """


class MattermostHandler(ThreadedHandler):
    LEVEL_EMOJIS = {
        logging.DEBUG: ":bug:",
        logging.INFO: ":information_source:",
        logging.WARNING: ":warning:",
        logging.ERROR: ":red_circle::exclamation:",
        logging.CRITICAL: ":rotating_light::exclamation:"
    }

    LEVEL_COLORS = {
        #logging.WARNING: "#FFD700",   # gold
        logging.ERROR: "#FF6347",     # tomato red
        logging.CRITICAL: "#DC143C"   # crimson
    }

    def __init__(self, webhook_url: str):
        super().__init__()
        self.webhook_url = webhook_url

    def logging_logic(self, record):
        try:
            message = record.getMessage()
            log_level = record.levelno
            emoji = self.LEVEL_EMOJIS.get(log_level, "") + " "
            text = f"{emoji}{message}"

            mm_data = {}

            # For WARNING/ERROR/CRITICAL, use attachment with background color
            if record.levelno in self.LEVEL_COLORS:
                mm_data["attachments"] = [{
                    "fallback": message,
                    "color": self.LEVEL_COLORS[record.levelno],
                    "text": text
                }]
            else:
                mm_data["text"] = text

            response = requests.post(
                self.webhook_url,
                data=json.dumps(mm_data),
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code != 200:
                print(f"Mattermost webhook failed: {response.status_code}, {response.text}")

        except Exception as e:
            print(f"Error sending message to Mattermost: {e}")

# Custom handler for logging to a Text widget
class TextWidgetHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        log_entry = self.format(record)
        # use after() to avoid segmentation faults
        if self.text_widget:
            self.text_widget.after(0, self._write_log, log_entry)

    def _write_log(self, log_entry):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", log_entry + "\n")
        self.text_widget.configure(state="disabled")
        self.text_widget.see("end")
    """
    def __repr__(self):
        return f"{self.__class__.__name__}({self.text_widget})"
    """

def configure_basic_logger(logger_name:str, log_level=logging.DEBUG):
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    logger = configure_slack_logger(
        logger_name,
        log_filename=f"{LOG_DIR}/slack_{logger_name}.log",
        slack_webhook_url=SLACK_WEBHOOK_URL,
        log_level=logging.WARNING
    )
    logger = configure_mattermost_logger(
        logger_name,
        log_filename=f"{LOG_DIR}/mattermost_{logger_name}.log",
        mattermost_webhook_url=MATTERMOST_WEBHOOK_URL,
        log_level=logging.WARNING
    )
    logger = configure_streamer_logger(
        logger_name,
        log_filename=f"{LOG_DIR}/stream_{logger_name}.log",
        log_level=logging.DEBUG
    )

    return logger

def configure_slack_logger(logger_name:str, log_filename:str, slack_webhook_url:str, log_level=logging.ERROR):
    logger = logging.getLogger(logger_name)
    # logger.setLevel(logging.DEBUG)
    if slack_webhook_url:
        slack_handler = SlackHandler(slack_webhook_url)
        slack_handler.setLevel(log_level)
        file_slack_handler = logging.FileHandler(log_filename)
        file_slack_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        file_slack_handler.setLevel(slack_handler.level)
        logger.addHandler(slack_handler)
        logger.addHandler(file_slack_handler)
    return logger

def configure_mattermost_logger(logger_name:str, log_filename:str, mattermost_webhook_url:str, log_level=logging.ERROR):
    logger = logging.getLogger(logger_name)
    # logger.setLevel(logging.DEBUG)
    if mattermost_webhook_url:
        mattermost_handler = MattermostHandler(mattermost_webhook_url)
        mattermost_handler.setLevel(log_level)
        file_mattermost_handler = logging.FileHandler(log_filename)
        file_mattermost_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        file_mattermost_handler.setLevel(mattermost_handler.level)
        logger.addHandler(mattermost_handler)
        logger.addHandler(file_mattermost_handler)
    return logger

def configure_streamer_logger(logger_name:str, text_widget=None, log_filename:str=None, log_level=logging.DEBUG):
    logger = logging.getLogger(logger_name)
    # logger.setLevel(logging.DEBUG)
    if text_widget:
        text_handler = TextWidgetHandler(text_widget)
        text_handler.setLevel(log_level)
        logger.addHandler(text_handler)
    else:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        logger.addHandler(stream_handler)

    if log_filename:
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(file_handler)
    return logger

def get_children_loggers(parent_name, include_parent=False):
    """
    Get all direct child loggers of a given logger name. Method made for compatibility with Python<3.12
    which does not have the logging.Logger.getChildren() method.
    
    :param parent_name: The name of the parent logger.
    :param include_parent: Whether to include the parent logger in the list of children.
    :return: A list of child logger names.
    """
    parent_logger = logging.getLogger(parent_name)
    children = []
    if include_parent:
        children.append(parent_logger)
    try:
        c = parent_logger.getChildren() # Python>=3.12
        children.extend(c)
    except AttributeError:
        all_loggers = logging.Logger.manager.loggerDict
        children_names = [
            name for name in all_loggers
            if name.startswith(f"{parent_name}.") and name != parent_name
        ]
        c = {logging.getLogger(name) for name in children_names}
        children.extend(c)

    return children


def get_level_names():
    """
    Retrieve all logging level names from the `logging` module. Method made for compatibility with Python<3.11

    :return: A list of level names.
    """
    try:
        return list(logging.getLevelNamesMapping().keys()) # Python>=3.11
    except AttributeError:
        return list(logging._nameToLevel.keys())
    return []

class State:
    def __init__(self, vmon=0, imon=0, stat=None):
        if stat is None:
            stat = {}
        self.time = dt.datetime.now()
        self.vmon = imon
        self.imon = vmon
        self.stat = stat
    
    def set_state(self, vmon, imon, stat):
        self.time = dt.datetime.now()
        self.vmon = vmon
        self.imon = imon
        self.stat = stat

    def __str__(self):
        return "vmon: {:.2f}V, imon: {:.2f}uA, stat: {}".format(self.vmon, self.imon, self.stat)

    def print_state(self):
        print("Time:", self.time.strftime("%Y-%m-%d %H:%M:%S"))
        print("vmon: {:.2f}V, imon: {:.2f}uA, stat: {}".format(self.vmon, self.imon, self.stat))

    def write_to_file(self, filename, delimiter=' ', precision_vmon=1, precision_imon=3):
        create_directory_recursive(filename)
        if not os.path.isfile(filename):
            try:
                # create the file if it does not exist
                with open(filename, 'w') as file:
                    file.write('Time' + delimiter + 'Vmon(V)' + delimiter + 'Imon(uA)' + '\n')
                print("Writing to new file:", filename)
            except:
                print("Invalid file or directory:", filename)

        with open(filename, 'a') as file:
            file.write(f"{self.time.strftime('%Y-%m-%d %H:%M:%S')}{delimiter}{self.vmon:.{precision_vmon}f}{delimiter}{self.imon:.{precision_imon}f}\n")

    def assign(self, other):
        self.time = other.time
        self.vmon = other.vmon
        self.imon = other.imon
        self.stat = other.stat

    def __eq__(self, other):
        return all([self.time == other.time, self.vmon == other.vmon, self.imon == other.imon, self.stat == other.stat])
    
    def __ne__(self, other):
        return not self.__eq__(other)

class ChannelState:
    def __init__(self, name="", ch=None, diff_vmon=0.5, diff_imon=0.01, precision_vmon=1, precision_imon=3):
        self.channel = ch
        self.channel_name = name

        self.current = State()
        self.previous = State()
        self.last_saved = State()

        self.diff_vmon = diff_vmon
        self.diff_imon = diff_imon
        self.precision_vmon = precision_vmon
        self.precision_imon = precision_imon

    def __str__(self):
        return self.channel_name + ": " + str(self.current)

    def set_state(self, state):
        '''
        if not state: # avoid using this as it should use the device lock
            time = dt.datetime.now()
            vmon = self.channel.vmon
            imon = self.channel.imon
            stat = self.channel.stat
            state = State(time, vmon, imon, stat)
        '''
        self.previous.assign(self.current)
        self.current.assign(state)

    def set_state(self, vmon, imon, stat=None):
        if stat is None:
            stat = {}
        self.previous.assign(self.current)
        self.current.set_state(vmon, imon, stat)

    def print(self):
        print(self.channel_name)
        print("Time:", self.current.time.strftime("%Y-%m-%d %H:%M:%S"))
        print(self.current)

    def is_different(self):
        return (abs(self.current.vmon - self.last_saved.vmon) >= self.diff_vmon) or (abs(self.current.imon - self.last_saved.imon) >= self.diff_imon)

    def save_state(self, force=False, save_previous=True):
        filename = get_full_filename_from_date(self.current.time, suffix=self.channel_name.replace(" ", ""))
        if self.is_different() or force:
            if self.last_saved != self.previous and save_previous:
                self.previous.write_to_file(filename, precision_vmon=self.precision_vmon, precision_imon=self.precision_imon)
            self.current.write_to_file(filename, precision_vmon=self.precision_vmon, precision_imon=self.precision_imon)
            self.last_saved.assign(self.current)


