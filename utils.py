import gspread
from oauth2client.service_account import ServiceAccountCredentials
from logger import LOG_DIR

GOOGLE_SHEET_SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
GOOGLE_SHEET_CREDENTIALS_FILENAME = "trex-slowcontrolHV-credentials.json"
GOOGLE_SHEET_NAME = "TREX-DM run lists"
def append_row_to_google_sheet(row, worksheet_number=3):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS_FILENAME, GOOGLE_SHEET_SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME)
        page = sheet.get_worksheet(worksheet_number) # starts from 0
        result = page.append_row(row, value_input_option='USER_ENTERED', table_range='A5')
        print(f"Row appended in range {result['updates']['updatedRange']}")
    except Exception as e:
        print(f"Error while appending row to Google Sheet: {e}")
    finally:
        with open(LOG_DIR + "/run_list.txt", "a") as file:
            file.write(str(row))

def create_row_for_google_sheet(run_number, start_date, run_type, other_columns):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS_FILENAME, GOOGLE_SHEET_SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME)
        page = sheet.get_worksheet(3) # starts from 0
        column_names = page.row_values(2)
    except Exception as e:
        column_names = ['Run', 'Date', 'Type', 'Time', 'Vmesh Left (V)', 'Eg-mm (V/cm*bar)', 'Vgem(top-bott) (V)',
                        'Vgembottom', 'Vgemtop', 'Vlastring', 'Ec-g(V/cm*bar)', 'Vcathode (V)', 'Ec-mm (V/cm*bar)',
                        'Vmesh Right (V)', 'Pressure (bar)', 'Flow (ln/h)', 'Gain (FEC units)', 'Shape time (FEC units)',
                        'Clock (FEC units/MHz)', 'Threshold Left (daq+thr)', 'Multiplicity Left', 'Threshold Right (daq+thr)',
                        'Multiplicity Right', 'Trigg_delay (hexad/decimal)', 'trip info', 'Notes',
                        ]
        print(f"Error, {e}, while fetching column names from Google Sheet. Using default column names")
    column_names = [c.replace(' ', '').lower() for c in column_names]
    row = ['' for _ in range(len(column_names))]
    row[0] = run_number
    row[1] = start_date
    row[2] = run_type
    for ch, v in other_columns.items():
        ch = ch.replace(' ', '').lower()
        column_found = False
        for column in column_names:
            if ch in column:
                row[column_names.index(column)] = v
                column_found = True
                break
        if not column_found:
            print(f"Column for channel {ch} not found in Google Sheet")
    return row

def get_last_run_number_from_google_sheet(worksheet_number=3):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS_FILENAME, GOOGLE_SHEET_SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME)
        page = sheet.get_worksheet(worksheet_number) # starts from 0
        column_values = page.col_values(1)  # 1 refers to column A (run number)
        run_numbers = [val for val in column_values if val]
        print(f"Last run number from Google Sheet: {run_numbers[-1]}")
        return run_numbers[-1]
    except Exception as e:
        print(f"Error while fetching last run number from Google Sheet: {e}")
        return -1

    class GoogleSheetClient:
        def __init__(self, scope, credentials_filename, sheet_name):
            self.scope = scope
            self.credentials_filename = credentials_filename
            self.sheet_name = sheet_name
            self.client = None
            self.sheet = None
        
        def __enter__(self):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_filename, self.scope)
                self.client = gspread.authorize(creds)
                self.sheet = self.client.open(self.sheet_name)
                return self.sheet
            except Exception as e:
                print(f"Error while connecting to Google Sheet: {e}")
                return None
        
        def __exit__(self, exc_type, exc_value, traceback):
            pass

import requests
import json
import os
import datetime as dt
def write_to_log_file(message:str, log_filename:str, print_message:bool=True):
    if print_message:
        print(message)
    if log_filename:
        filename = LOG_DIR + "/" + log_filename
        if not os.path.isfile(filename):
            try:
                # create the file if it does not exist
                with open(filename, 'w') as file:
                    pass
                print("Writing to new file:", filename)
            except:
                raise Exception("Invalid file or directory:", filename)

        with open(filename, 'a') as file:
            time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(time + " " + message + '\n')

def send_slack_message(message:str, log_filename="", print_message=True):
    #### webhook to Alvaro chat
    webhook_url = ""
    #### webhook to trex-operations channel
    #webhook_url = ""
    write_to_log_file(message, log_filename, print_message=print_message)
    write_to_log_file(message, "slack.log", print_message=False) # always write to slack.log too
    slack_data = {'text': message}
    try:
        requests.post(webhook_url, data=json.dumps(slack_data), headers={'Content-Type': 'application/json'})
    except Exception as e:
        print(e)
