import re
from collections import defaultdict
import paramiko
import requests

def parse_prometheus_metrics(metrics_data):
    """
    Parses Prometheus metrics text into a structured dictionary.
    
    Args:
    metrics_data (str): The raw metrics data as a string.
    
    Returns:
    dict: A dictionary where keys are metric names, and values contain type, help, and metric values.
    """
    
    metrics = defaultdict(lambda: {"type": None, "help": None, "values": {}})
    current_metric = None
    
    # Regex patterns to match various parts of the metrics
    help_pattern = re.compile(r'^# HELP (\S+) (.+)')
    type_pattern = re.compile(r'^# TYPE (\S+) (\S+)')
    metric_value_pattern = re.compile(r'^(\S+?)(?:\{([^}]+)\})?\s+([\d\.NaN]+)')
    for line in metrics_data.splitlines():
        # Skip empty lines
        if not line.strip():
            continue
        
        # Match HELP lines
        help_match = help_pattern.match(line)
        if help_match:
            current_metric = help_match.group(1)
            metrics[current_metric]["help"] = help_match.group(2)
            continue
        
        # Match TYPE lines
        type_match = type_pattern.match(line)
        if type_match:
            current_metric = type_match.group(1)
            metrics[current_metric]["type"] = type_match.group(2)
            continue
        
        # Match metric value lines
        metric_value_match = metric_value_pattern.match(line)
        if metric_value_match:
            metric_name = metric_value_match.group(1)
            labels = metric_value_match.group(2)
            value = metric_value_match.group(3)
            
            # Convert value to float if possible, otherwise leave it as a string (e.g., for 'Nan')
            try:
                value = float(value)
            except ValueError:
                pass
            
            # Store the metric values with labels (or None if no labels)
            metrics[metric_name]["values"][labels] = value
    
    return dict(metrics)

# Example usage:
metrics_data = """
# HELP exposer_transferred_bytes_total Transferred bytes to metrics services
# TYPE exposer_transferred_bytes_total counter
exposer_transferred_bytes_total 0
# HELP exposer_scrapes_total Number of times metrics were scraped
# TYPE exposer_scrapes_total counter
exposer_scrapes_total 0
# HELP exposer_request_latencies Latencies of serving scrape requests, in microseconds
# TYPE exposer_request_latencies summary
exposer_request_latencies_count 0
exposer_request_latencies_sum 0
exposer_request_latencies{quantile="0.5"} 1
exposer_request_latencies{quantile="0.9"} 2
exposer_request_latencies{quantile="0.99"} 3
# HELP uptime_seconds Uptime in seconds (since the start of the program)
# TYPE uptime_seconds gauge
uptime_seconds 0
# HELP free_disk_space_gb Free disk space in gigabytes
# TYPE free_disk_space_gb gauge
free_disk_space_gb{path="/"} 76.87284469604492
# HELP daq_speed_mb_per_sec_now DAQ speed in megabytes per second
# TYPE daq_speed_mb_per_sec_now gauge
daq_speed_mb_per_sec_now 0
# HELP daq_speed_events_per_sec_now DAQ speed in events per second
# TYPE daq_speed_events_per_sec_now gauge
daq_speed_events_per_sec_now 0
# HELP daq_frames_queue_fill_level_now DAQ frames queue fill level (0 - empty - good, 1 - full - bad)
# TYPE daq_frames_queue_fill_level_now gauge
daq_frames_queue_fill_level_now 0
# HELP run_number Run number
# TYPE run_number gauge
run_number 0
# HELP number_of_events Number of events processed
# TYPE number_of_events gauge
number_of_events 0
# HELP number_of_signals_in_last_event Number of signals in last event
# TYPE number_of_signals_in_last_event gauge
number_of_signals_in_last_event 0
"""

"""
parsed_metrics = parse_prometheus_metrics(metrics_data)

# Print the parsed metrics
for metric, info in parsed_metrics.items():
    print(f"Metric: {metric}")
    print(f"  Type: {info['type']}")
    print(f"  Help: {info['help']}")
    for labels, value in info['values'].items():
        print(f"  Labels: {labels} -> Value: {value}")
"""

class SSHConnection:
    def __init__(self, hostname, port, username, password=None, key_filename=None):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.client = paramiko.SSHClient()

    def __enter__(self):
        try:
            # Load system host keys and set policy to auto add unknown hosts
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Attempt to connect to the SSH server
            self.client.connect(self.hostname, port=self.port, username=self.username, password=self.password)
            return self.client

        except Exception as e:
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        # Close the connection
        self.client.close()

class MetricsFetcher:
    def __init__(self, url):
        self.url = url
        self.metrics = None

    def fetch_metrics(self):
        response = requests.get(self.url)
        response.raise_for_status()
        self.metrics = parse_prometheus_metrics(response.text)
    
    def get_metric(self, metric_name, labels=None):
        if self.metrics is None:
            self.fetch_metrics()
        
        if metric_name not in self.metrics:
            raise ValueError(f"Metric '{metric_name}' not found in the fetched metrics.")
        
        metric_info = self.metrics[metric_name]
        if labels is None:
            return metric_info['values'].get(None, metric_info['values'])
        
        return metric_info['values'].get(labels, f"No value found for labels '{labels}'")
    
    def get_metrics_list(self):
        if self.metrics is None:
            self.fetch_metrics()
        
        return list(self.metrics.keys())
    
    def get_metrics(self):
        if self.metrics is None:
            self.fetch_metrics()
        
        return self.metrics
    
    def get_metric_help(self, metric_name):
        if self.metrics is None:
            self.fetch_metrics()
        
        if metric_name not in self.metrics:
            raise ValueError(f"Metric '{metric_name}' not found in the fetched metrics.")
        
        return self.metrics[metric_name]['help']
    
    def get_metric_type(self, metric_name):
        if self.metrics is None:
            self.fetch_metrics()
        
        if metric_name not in self.metrics:
            raise ValueError(f"Metric '{metric_name}' not found in the fetched metrics.")
        
        return self.metrics[metric_name]['type']
    
    def get_metric_labels(self, metric_name):
        if self.metrics is None:
            self.fetch_metrics()
        
        if metric_name not in self.metrics:
            raise ValueError(f"Metric '{metric_name}' not found in the fetched metrics.")
        
        return list(self.metrics[metric_name]['values'].keys())
    
    def get_metric_value(self, metric_name, labels=None):
        return self.get_metric(metric_name, labels)
    
    def get_filename_metadata(self):
        output_file_labels = self.get_metric_labels("output_root_file_size_mb")
        output_filename = ""
        for lbl in output_file_labels:
            if "filename=" in lbl:
                output_filename = lbl.split("filename=")[1]
                output_filename = output_filename.replace('"', '')
                output_filename = output_filename.split("/")[-1]
                break
        splits_ = output_filename.split("_")
        metadata = {}
        metadata["run_number"] = splits_[0].remove("R")
        metadata["run_type"] = splits_[1]
        

class MetricsFetcherSSH(MetricsFetcher):
    def __init__(self, url, hostname, username, password=None, key_filename=None):
        super().__init__(url)
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.ssh_connection = SSHConnection(self.hostname, 22, self.username, self.password, self.key_filename)

        self.error_output = None
    
    def fetch_metrics(self):
        try:
            with self.ssh_connection as ssh_con:
                # Run the command to fetch the metrics
                stdin, stdout, stderr = ssh_con.exec_command(f"curl -sS {self.url}")
                error_output = stderr.read().decode()
                if error_output:
                    if self.error_output != error_output:
                        print(f"Error: {error_output}. Is feminos-daq running?")
                        self.error_output = error_output
                    self.metrics = None
                response = stdout.read().decode()
                self.metrics = parse_prometheus_metrics(response)
        except Exception as e:
            if self.error_output != str(e):
                print(f"Error connecting to SSH: {e}")
                self.error_output = str(e)
            self.metrics = None

if __name__ == "__main__":
    # Example usage of the MetricsFetcherSSH class
    metrics_fetcher = MetricsFetcherSSH(
                            url="http://localhost:8080/metrics",
                            hostname="192.168.3.80",
                            username="usertrex",
                            key_filename="/home/usertrex/.ssh/id_rsa"
                            )
    metrics_fetcher.fetch_metrics()

    # Get a list of available metrics
    print("Available metrics (SSH):")
    print(metrics_fetcher.get_metrics_list())

