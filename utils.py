import gspread
from oauth2client.service_account import ServiceAccountCredentials

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

def create_row_for_google_sheet(run_number, start_date, run_type, voltages):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEET_CREDENTIALS_FILENAME, GOOGLE_SHEET_SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME)
        page = sheet.get_worksheet(3) # starts from 0
        column_names = page.row_values(2)
    except Exception as e:
        column_names = ['Run', 'Date', 'Type', 'Time', 'Vmesh Left (V)', 'Eg-mm (V/cm*bar)', 'Vgem(top-bott) (V)',
                        'Vgembottom', 'Vgemtop', 'Vlastring', 'Ec-g(V/cm*bar)', 'Vcathode (V)', 'Ec-mm (V/cm*bar)',
                        'Vmesh Rigth (V)', 'Pressure (bar)', 'Flow (ln/h)', 'Gain (FEC units)', 'Shaping time (FEC units)',
                        'Clock (FEC units/MHz)', 'Threshold_North (daq+thr)', 'Threshold_South (daq+thr)',
                        'Trigg_delay (hexad/decimal)', 'trip info', 'Notes',
                        ]
        print(f"Error, {e}, while fetching column names from Google Sheet. Using default column names")
    column_names = [c.replace(' ', '').lower() for c in column_names]
    row = ['' for _ in range(len(column_names))]
    row[0] = run_number
    row[1] = start_date
    row[2] = run_type
    for ch, v in voltages.items():
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

    