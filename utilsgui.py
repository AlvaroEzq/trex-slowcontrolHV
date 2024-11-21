import tkinter as tk
import re

def enable_children(parent, enabled=True):
    for child in parent.winfo_children():
        wtype = child.winfo_class()
        # print(wtype)
        if wtype not in ('Frame', 'Labelframe', 'TFrame', 'TLabelframe'):
            child.configure(state=tk.NORMAL if enabled else tk.DISABLED)
        else:
            enable_children(child, enabled)

def validate_numeric_entry_input(new_value):
    # Allow only if the input matches the regex for a decimal number
    if re.match(r"^\d*\.?\d*$", new_value):
        return True
    return False

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.label = None  # To reference the Label for updating its text

        self.widget.bind("<Enter>", lambda _: self.show_tooltip())
        self.widget.bind("<Leave>", lambda _: self.hide_tooltip())

    def show_tooltip(self):
        if self.tooltip:  # Tooltip is already being shown
            self.label.config(text=self.text)  # Just update the text
        else:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
            self.tooltip = tk.Toplevel(self.widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")

            self.label = tk.Label(
                self.tooltip,
                text=self.text,
                background="light goldenrod",
                relief="solid",
                borderwidth=1,
                font=("Arial", 10),
            )
            self.label.pack()

    def hide_tooltip(self):
        if self.tooltip:
            self.tooltip.destroy()
        self.tooltip = None
        self.label = None  # Reset the reference to the label

    def change_text(self, text):
        self.text = text
        if self.tooltip:  # If the tooltip is visible, update its text
            self.label.config(text=self.text)

class PrintLogger(object):

    def __init__(self, textbox):  # pass reference to text widget
        self.textbox = textbox

    def write(self, text):
        # Use of after() is needed to prevent segmentation faults
        self.textbox.after(0, self._append_text, text)

    def _append_text(self, text):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def flush(self): # needed
        pass
