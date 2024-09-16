import tkinter as tk

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
