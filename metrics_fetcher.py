import re
from collections import defaultdict
import paramiko
import requests
import os
import datetime

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


def parse_run_file_by_fem(file_content):
    """ Extracts values from a file content string and organizes them by FEM number.
    Example of file content: the .run file
    Currently it does not support fem * and aget *.
    """
    values_by_fem = {}
    current_fem = None
    multiline_comment = False

    # Split the input string by lines and process each line
    for line in file_content.splitlines():
        # skip comments
        if line.startswith('#'):
            continue
        if line.startswith('/*'):
            multiline_comment = True
            continue
        if line.startswith('*/'):
            multiline_comment = False
            continue
        if multiline_comment:
            continue
        if '#' in line: # remove inline comments
            line = line.split('#')[0]
        
        # Look for lines indicating a new fem (e.g., 'fem X')
        fem_match = re.search(r'fem\s+(\d+)', line)
        if fem_match:
            current_fem = int(fem_match.group(1))  # Get the FEM number
            if current_fem not in values_by_fem:
                values_by_fem[current_fem] = {}  # Initialize the FEM dictionary

        # Look for lines matching 'aget X dac Y'
        aget_match = re.search(r'aget\s+(\d+)\s+dac\s+(\w+)', line)
        if aget_match and current_fem is not None:
            aget_id = int(aget_match.group(1))  # Get AGET number
            dac_value = aget_match.group(2)  # DAC value

            # Initialize dictionary for this AGET if not present
            if aget_id not in values_by_fem[current_fem]:
                values_by_fem[current_fem][aget_id] = {}

            # Store the DAC value
            values_by_fem[current_fem][aget_id]['dac'] = dac_value

        # Look for lines matching 'aget X threshold Y'
        threshold_match = re.search(r'aget\s+(\d+)\s+threshold\s+\*\s+(\w+)', line)
        if threshold_match and current_fem is not None:
            aget_id = int(threshold_match.group(1))
            threshold_value = threshold_match.group(2)

            if aget_id not in values_by_fem[current_fem]:
                values_by_fem[current_fem][aget_id] = {}

            values_by_fem[current_fem][aget_id]['threshold'] = threshold_value

        # Look for lines matching 'mult_thr X Y'
        mult_thr_match = re.search(r'mult_thr\s+(\d+)\s+(\d+)', line)
        if mult_thr_match and current_fem is not None:
            channel_id = int(mult_thr_match.group(1))
            mult_thr_value = mult_thr_match.group(2)

            if channel_id not in values_by_fem[current_fem]:
                values_by_fem[current_fem][channel_id] = {}

            values_by_fem[current_fem][channel_id]['mult_thr'] = mult_thr_value

        # Look for lines matching 'mult_limit X Y'
        mult_limit_match = re.search(r'mult_limit\s+(\d+)\s+(\d+)', line)
        if mult_limit_match and current_fem is not None:
            channel_id = int(mult_limit_match.group(1))
            mult_limit_value = mult_limit_match.group(2)

            if channel_id not in values_by_fem[current_fem]:
                values_by_fem[current_fem][channel_id] = {}

            values_by_fem[current_fem][channel_id]['mult_limit'] = mult_limit_value

    return values_by_fem

def parse_femdaq_config_yaml_file(file_content):
    """
    Parse YAML content from a string into a Python dictionary.

    Args:
        file_content (str): YAML content as a string

    Returns:
        dict: Parsed YAML data
    """

    # just associate the content before : to the valuye afterwards for each line
    info = {}
    for line in file_content.splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            info[key] = value

    return info

def get_loop_time_from_run_file(file_content):
    """ Extracts the loop time in seconds from the run file content string.
    Example of file content: the .run file
    """
    run_loop_time_seconds = -1
    # Look for the line starting with LOOP
    for line in file_content.splitlines():
        if line.startswith('LOOP'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    run_loop_time_seconds = int(parts[1])
                except ValueError:
                    run_loop_time_seconds = -1
            break
    return run_loop_time_seconds

# Usage example
file_content = """
fem 0
aget 0 dac 0x1
aget 0 threshold * 0x8
mult_thr 0 31
mult_limit 0 230
fem 1
aget 1 dac 0x2
aget 1 threshold * 0xA
mult_thr 1 32
mult_limit 1 240
"""  # Example of file content as a string
"""
values_by_fem = parse_run_file_by_fem(file_content)
# Display the extracted values for each FEM
for fem, aget_data in values_by_fem.items():
    print(f'FEM {fem}:')
    for aget_id, params in aget_data.items():
        print(f'  AGET {aget_id}:')
        for param, value in params.items():
            print(f'    {param} = {value}')
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
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            self.metrics = parse_prometheus_metrics(response.text)
        except:
            self.metrics = None    

    def fetch_file_content(self, filename):
        try:
            with open(filename, "r") as file:
                return file.read()
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            return None
    
    def get_file_time(self, filename):
        try:
            timestamp = os.path.getmtime(filename)
            date = datetime.datetime.fromtimestamp(timestamp)
            return date.strftime("%d/%m/%Y %H:%M")
        except Exception as e:
            print(f"Error getting file time for {filename}: {e}")
            return None

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
        if self.metrics is None:
            return []
        return list(self.metrics.keys())
    
    def get_metrics(self):
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

class MetricsFetcherSSH(MetricsFetcher):
    def __init__(self, url, hostname, username, password=None, key_filename=None):
        super().__init__(url)
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.ssh_connection = SSHConnection(self.hostname, 22, self.username, self.password, self.key_filename)

        self.error_output = None
        self.error_ssh_connection = None

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
                    return None
                response = stdout.read().decode()
                self.metrics = parse_prometheus_metrics(response)
        except Exception as e:
            if self.error_ssh_connection != str(e):
                print(f"Error connecting to SSH: {e}")
                self.error_ssh_connection = str(e)
            self.metrics = None
        return self.metrics

    def fetch_file_content(self, filename):
        try:
            with self.ssh_connection as ssh_con:
                with ssh_con.open_sftp() as sftp:
                    with sftp.file(filename, "r") as file:
                        file_content = file.read().decode()
        except Exception as e:
            if self.error_ssh_connection != str(e):
                print(f"Error connecting to SSH: {e}")
                self.error_ssh_connection = str(e)
            file_content = None
        return file_content
    
    def get_file_time(self, filename):
        try:
            with self.ssh_connection as ssh_con:
                with ssh_con.open_sftp() as sftp:
                    timestamp = sftp.stat(filename).st_mtime
                    date = datetime.datetime.fromtimestamp(timestamp)
                    return date.strftime("%d/%m/%Y %H:%M")
        except Exception as e:
            if self.error_ssh_connection != str(e):
                print(f"Error connecting to SSH: {e}")
                self.error_ssh_connection = str(e)
            return None

class DaqMetricsBase:
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.run_file_content = None
    
    def fetch_metrics(self):
        self.fetcher.fetch_metrics()
    
    def get_metric(self, metric_name, labels=None):
        return self.fetcher.get_metric(metric_name, labels)
    
    def get_run_type(self):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_run_number(self):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_run_time_seconds(self):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_run_start_time_string(self, formatting="%d/%m/%Y %H:%M"):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_run_start_time(self):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_rate(self):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_number_of_events(self):
        raise NotImplementedError("Subclasses should implement this method.")
    
    def get_all_metadata(self):
        raise NotImplementedError("Subclasses should implement this method.")


class FeminosDaqMetrics(DaqMetricsBase):
    def __init__(self, fetcher):
        super().__init__(fetcher)

    def get_run_start_time(self):
        run_filename = self.get_filename().replace(".root", ".run")
        return self.fetcher.get_file_time(run_filename)

    def get_run_start_time_string(self, formatting="%d/%m/%Y %H:%M"):
        date = self.get_run_file_time()
        return date.strftime(formatting)
    
    def get_filename(self):
        try:
            output_file_labels = self.fetcher.get_metric_labels("output_root_file_size_mb")
        except ValueError:
            return ""
        output_filename = ""
        for lbl in output_file_labels:
            if "filename=" in lbl:
                output_filename = lbl.split("filename=")[1]
                output_filename = output_filename.replace('"', '')
                break
        return output_filename

    def get_filename_metadata(self):
        try:
            output_file_labels = self.fetcher.get_metric_labels("output_root_file_size_mb")
        except ValueError:
            return {}
        #example: filename="/storage/data//R02450_Calibration37Ar_Vm_270_Vd_90_Pr_1.1_Gain_0x0_Shape_0xF_Clock_0x4.root"}
        output_filename = ""
        for lbl in output_file_labels:
            if "filename=" in lbl:
                output_filename = lbl.split("filename=")[1]
                output_filename = output_filename.replace('"', '')
                output_filename = output_filename.split("/")[-1]
                break
        splits_ = output_filename.split("_")
        metadata = {}
        metadata["run_number"] = splits_[0].replace("R", "")
        metadata["run_type"] = splits_[1]
        # Get the rest of the metadata that should be in pairs with format 'key_value'
        for i in range(2, len(splits_), 2):
            metadata[splits_[i]] = splits_[i+1].replace(".root", "")
        return metadata
    
    def get_all_metadata(self):
        return self.get_filename_metadata()

    def get_run_number(self):
        return self.get_metric("run_number")

    def get_run_type(self):
        return self.get_filename_metadata().get("run_type", "N/A")
    
    def get_rate(self):
        try:
            rate = self.fetcher.get_metric("daq_speed_events_per_sec_now")
            return rate
        except ValueError:
            return None
    
    def get_number_of_events(self):
        try:
            n_events = self.fetcher.get_metric("number_of_events")
            return n_events
        except ValueError:
            return None
    

    def get_run_file_content(self):
        self.fetch_run_file()
        return self.run_file_content

    def get_run_file_values_by_fem(self):
        file_content = self.get_run_file_content()
        if file_content is None:
            return {}
        return parse_run_file_by_fem(file_content)

    def get_run_file_values_for_fem(self, fem_number):
        values_by_fem = self.get_run_file_values_by_fem()
        return values_by_fem.get(fem_number, {})

    def get_run_file_values_for_aget(self, fem_number, aget_number):
        values_by_fem = self.get_run_file_values_by_fem()
        return values_by_fem.get(fem_number, {}).get(aget_number, {})

    def get_total_threshold_for_fem_aget(self, fem_number, aget_number):
        dac = self.get_run_file_values_for_aget(fem_number, aget_number).get('dac', None)
        threshold = self.get_run_file_values_for_aget(fem_number, aget_number).get('threshold', None)
        total_threshold = f"{dac} + {threshold}"
        return total_threshold

    def get_total_multiplicity_for_fem_aget(self, fem_number, aget_number):
        mult_thr = self.get_run_file_values_for_aget(fem_number, aget_number).get('mult_thr', None)
        mult_limit = self.get_run_file_values_for_aget(fem_number, aget_number).get('mult_limit', None)
        total_multiplicity = f"{mult_thr}+{mult_limit}"
        return total_multiplicity
    
    def get_run_time_seconds(self):
        file_content = self.get_run_file_content()
        if file_content is None:
            return -1
        return get_loop_time_from_run_file(file_content)
    
class FemDaqMetrics(DaqMetricsBase):
    def __init__(self, fetcher):
        super().__init__(fetcher)
    
    def get_run_file_time(self):
        run_filename = self.get_filename().replace(".root", ".run")
        return self.fetcher.get_file_time(run_filename)

    def get_run_file_time_string(self, formatting="%d/%m/%Y %H:%M"):
        date = self.get_run_file_time()
        return date.strftime(formatting)
    
    def get_filename(self):
        try:
            output_file_labels = self.fetcher.get_metric_labels("run_filename_info")
        except ValueError:
            return ""
        output_filename = ""
        for lbl in output_file_labels:
            if "filename=" in lbl:
                output_filename = lbl.split("filename=")[1]
                output_filename = output_filename.replace('"', '')
                break
        return output_filename


    def get_filename_metadata(self):
        output_filename = self.get_filename()
        splits_ = output_filename.split("_")
        metadata = {}
        metadata["run_number"] = splits_[0].replace("Run", "")
        metadata["run_tag"] = splits_[1]
        metadata["experiment"] = splits_[2]
        metadata["run_type"] = splits_[3]
        metadata["subrun_number"] = splits_[4]
        return metadata

    def get_run_number(self):
        return self.get_metric("run_number")

    def get_run_type(self):
        return self.get_filename_metadata().get("run_type", "N/A")
    
    def get_rate(self):
        try:
            rate = self.fetcher.get_metric("event_rate")
            return rate
        except ValueError:
            return None
    
    def get_number_of_events(self):
        try:
            n_events = self.fetcher.get_metric("events_total")
            return n_events
        except ValueError:
            return None
    
    def get_run_metadata(self):
        try:
            run_config = self.fetcher.get_metric("run_metadata_info")
            run_config = list(run_config.keys())[0] # run_metadata_info is not well defined as a metric...
            run_config = run_config.split("runName=")[1].replace('"', '')
        except ValueError:
            return ""
        #convert \n to actual newlines
        run_config = run_config.replace("\\n", "\n")
        info = parse_femdaq_config_yaml_file(run_config)
        return info
    
    def get_fems_in_run(self):
        info = self.get_run_metadata()
        return len(info.get("FEM", []))
    
    def get_all_metadata(self):
        metadata = self.get_filename_metadata()
        # add info
        info = self.get_run_metadata() # here there is some redundancy as some info is already in the filename
        for key, value in info.items():
            metadata[key] = value
        return metadata
    
    def get_run_nEvents(self):
        info = self.get_run_metadata()
        return info.get("nEvents", -1)
    
    def get_run_time(self):
        try:
            info = self.get_run_metadata()
            return info.get("time", "")
        except:
            return ""

    def get_run_time_seconds(self):
        time = self.get_run_time() # format should be something like '1h' or '30m' or '45s'
        try:
            if time.endswith('w'):
                time_seconds = int(time[:-1]) * 7 * 24 * 3600
            elif time.endswith('d'):
                time_seconds = int(time[:-1]) * 24 * 3600
            elif time.endswith('h'):
                time_seconds = int(time[:-1]) * 3600
            elif time.endswith('m'):
                time_seconds = int(time[:-1]) * 60
            elif time.endswith('s'):
                time_seconds = int(time[:-1])
            else:
                time_seconds = -1
        except:
            time_seconds = -1
        
        return time_seconds
    
    def get_run_maxFileSize(self):
        info = self.get_run_metadata()
        return info.get("maxFileSize", "")

    def get_run_file_content(self):
        self.fetch_run_file()
        return self.run_file_content

    def get_run_file_content(self):
        runCalibFilename = self.get_filename()
        splits_ = runCalibFilename.split("_")
        split_to_replace = splits_[-1] # the last split should be something like '001.root'
        filename = runCalibFilename.replace(split_to_replace, "FEM0.log") # where the content of runCalib file is dumped
        self.run_file_content = self.fetcher.fetch_file_content(filename)
        return self.run_file_content

    def get_run_file_values_by_fem(self):
        file_content = self.get_run_file_content()
        if file_content is None:
            return {}
        return parse_run_file_by_fem(file_content)

    def get_run_file_values_for_fem(self, fem_number):
        values_by_fem = self.get_run_file_values_by_fem()
        return values_by_fem.get(fem_number, {})

    def get_run_file_values_for_aget(self, fem_number, aget_number):
        values_by_fem = self.get_run_file_values_by_fem()
        return values_by_fem.get(fem_number, {}).get(aget_number, {})

    def get_total_threshold_for_fem_aget(self, fem_number, aget_number):
        dac = self.get_run_file_values_for_aget(fem_number, aget_number).get('dac', None)
        threshold = self.get_run_file_values_for_aget(fem_number, aget_number).get('threshold', None)
        total_threshold = f"{dac} + {threshold}"
        return total_threshold

    def get_total_multiplicity_for_fem_aget(self, fem_number, aget_number):
        mult_thr = self.get_run_file_values_for_aget(fem_number, aget_number).get('mult_thr', None)
        mult_limit = self.get_run_file_values_for_aget(fem_number, aget_number).get('mult_limit', None)
        total_multiplicity = f"{mult_thr}+{mult_limit}"
        return total_multiplicity

if __name__ == "__main__":
    # Example usage of the MetricsFetcherSSH class
    metrics_fetcher = MetricsFetcher(url="http://localhost:8080/metrics")
    metrics_fetcher.fetch_metrics()

    # Get a list of available metrics
    print("Available metrics (SSH):")
    print(metrics_fetcher.get_metrics_list())
