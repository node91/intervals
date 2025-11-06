import wx
import wx.adv
import threading
import requests
import json
import os
import time
from datetime import date

ICON_PATH = "intervals.ico"
SETTINGS_FILE = "settings.json"
REFRESH_INTERVAL = 600  # seconds

APP_ICON = None  # Will be initialized after wx.App is created

def load_settings():
    defaults = {"username": "API_KEY", "password": "", "athlete_id": "0"}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                return {
                    "username": saved.get("username", defaults["username"]) or defaults["username"],
                    "password": saved.get("password", defaults["password"]),
                    "athlete_id": saved.get("athlete_id", defaults["athlete_id"]) or defaults["athlete_id"]
                }
        except Exception as e:
            print(f"Failed to load settings: {e}")
    return defaults

def save_settings(username, password, athlete_id):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump({
                "username": username,
                "password": password,
                "athlete_id": athlete_id
            }, f)
    except Exception as e:
        print(f"Failed to save settings: {e}")

class IntervalsClient:
    def __init__(self, username, password, athlete_id):
        self.username = username
        self.password = password
        self.athlete_id = athlete_id
        self.base_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness"

    def fetch_today_activity(self):
        today = date.today().isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{self.athlete_id}/events{today}"
        try:
            response = requests.get(url, auth=(self.username, self.password), timeout=10)
            response.raise_for_status()
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0].get("name", "Rest")
            return "Rest"
        except Exception as e:
            print(f"Error fetching activity: {e}")
            return "Rest"

    def fetch_today_stats(self):
        today = date.today().isoformat()
        url = f"{self.base_url}/{today}"
        try:
            response = requests.get(url, auth=(self.username, self.password), timeout=10)
            response.raise_for_status()
            stats = self._parse_stats(response.json())
            activity = self.fetch_today_activity()
            return f"Today: {activity}\n\n{stats}"
        except Exception as e:
            print(f"Error fetching data: {e}")
            return "Failed to fetch data"

    def _parse_stats(self, data):
        ctl = int(data.get('ctl', 0))
        atl = int(data.get('atl', 0))
        form = round(ctl - atl, 2)
        ramp = round(data.get('rampRate', 0), 2)
        hr = int(data.get('restingHR', 0))
        hrv = int(data.get('hrv', 0))
        sleep = int(data.get('sleepScore', 0))
        steps = int(data.get('steps', 0))
        return (
            f"CTL: {ctl}\n"
            f"ATL: {atl}\n"
            f"Form: {form}\n"
            f"Ramp Rate: {ramp}\n"
            f"Resting HR: {hr}\n"
            f"HRV: {hrv}\n"
            f"Sleep Score: {sleep}\n"
            f"Steps: {steps}"
        )

class TrayApp(wx.adv.TaskBarIcon):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.SetIcon(APP_ICON, "Intervals")
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_double_click)
        self.Bind(wx.adv.EVT_TASKBAR_RIGHT_UP, self.on_right_click)
        self._stats_window = None
        self._settings_window = None
        self._start_refresh_thread()

    def CreatePopupMenu(self):
        menu = wx.Menu()
        stats_item = menu.Append(wx.ID_ANY, "Stats")
        settings_item = menu.Append(wx.ID_ANY, "Settings")
        exit_item = menu.Append(wx.ID_EXIT, "Exit")
        self.Bind(wx.EVT_MENU, lambda evt: self.show_stats(), stats_item)
        self.Bind(wx.EVT_MENU, lambda evt: self.show_settings(), settings_item)
        self.Bind(wx.EVT_MENU, lambda evt: wx.CallAfter(wx.GetApp().ExitMainLoop), exit_item)
        return menu

    def on_double_click(self, event):
        self.show_stats()

    def on_right_click(self, event):
        self.PopupMenu(self.CreatePopupMenu())

    def show_stats(self):
        if self._stats_window and self._stats_window.IsShown():
            self._stats_window.Raise()
            return

        stats = self.client.fetch_today_stats()
        self._stats_window = wx.Frame(None, title="Intervals Stats", size=(260, 220))
        self._stats_window.SetIcon(APP_ICON)
        panel = wx.Panel(self._stats_window)
        text = wx.StaticText(panel, label=stats, style=wx.ALIGN_LEFT)
        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        text.SetFont(font)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(text, 1, wx.ALL | wx.EXPAND, 10)
        panel.SetSizer(sizer)
        self._stats_window.Show()

    def show_settings(self):
        if self._settings_window and self._settings_window.IsShown():
            self._settings_window.Raise()
            return

        self._settings_window = wx.Frame(None, title="Settings", size=(300, 250))
        self._settings_window.SetIcon(APP_ICON)
        panel = wx.Panel(self._settings_window)

        vbox = wx.BoxSizer(wx.VERTICAL)

        def add_field(label, value):
            vbox.Add(wx.StaticText(panel, label=label), 0, wx.TOP | wx.LEFT, 10)
            field = wx.TextCtrl(panel, value=value)
            vbox.Add(field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
            return field

        user_field = add_field("Username:", self.client.username)
        pass_field = add_field("API Key:", self.client.password)
        id_field = add_field("Athlete ID:", self.client.athlete_id)

        def on_save(event):
            self.client.username = user_field.GetValue()
            self.client.password = pass_field.GetValue()
            self.client.athlete_id = id_field.GetValue()
            save_settings(self.client.username, self.client.password, self.client.athlete_id)
            self._settings_window.Close()

        save_btn = wx.Button(panel, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, on_save)
        vbox.Add(save_btn, 0, wx.ALL | wx.ALIGN_CENTER, 15)

        panel.SetSizer(vbox)
        self._settings_window.Show()

    def _start_refresh_thread(self):
        def loop():
            while True:
                stats = self.client.fetch_today_stats()
                tooltip = stats.replace("\n", "\n ")
                self.SetIcon(APP_ICON, tooltip)
                time.sleep(REFRESH_INTERVAL)
        threading.Thread(target=loop, daemon=True).start()

class App(wx.App):
    def OnInit(self):
        global APP_ICON
        APP_ICON = wx.Icon(ICON_PATH, wx.BITMAP_TYPE_ICO)

        settings = load_settings()
        client = IntervalsClient(settings["username"], settings["password"], settings["athlete_id"])
        self.tray = TrayApp(client)
        return True

if __name__ == "__main__":
    app = App(False)
    app.MainLoop()
