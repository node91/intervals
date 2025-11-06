import requests
import json
import os
import threading
import time
from datetime import date
from tkinter import Tk, Label, Entry, Button, StringVar
from pystray import Icon, MenuItem, Menu
from PIL import Image

# Configuration
ICON_PATH = 'intervals.ico'
REFRESH_INTERVAL = 600  # seconds
SETTINGS_FILE = "settings.json"

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

def apply_window_icon(window):
    try:
        window.iconbitmap(ICON_PATH)
    except Exception as e:
        print(f"Failed to set window icon: {e}")

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

class TrayApp:
    def __init__(self, client: IntervalsClient, icon_path: str):
        self.client = client
        self.icon_path = icon_path
        self.icon = None
        self._stats_window = None
        self._last_click = 0  # track last click time

    def _show_popup(self):
        if self._stats_window and self._stats_window.winfo_exists():
            self._stats_window.lift()
            return

        root = Tk()
        self._stats_window = root
        root.title("Intervals Stats")
        root.geometry("230x180")
        apply_window_icon(root)

        stats = self.client.fetch_today_stats()
        label = Label(root, text=stats, justify="left", font=("Consolas", 10))
        label.pack(padx=10, pady=10)

        def on_close():
            self._stats_window = None
            root.destroy()
        root.protocol("WM_DELETE_WINDOW", on_close)

        root.mainloop()

    def _refresh_loop(self):
        while True:
            if self.icon:
                self.icon.title = self.client.fetch_today_stats()
            time.sleep(REFRESH_INTERVAL)

    def refresh_stats(self):
        if self.icon:
            self.icon.title = self.client.fetch_today_stats()

    def _on_click(self, icon, item=None):
        # detect double click: two clicks within 0.4s
        now = time.time()
        if now - self._last_click < 0.4:
            threading.Thread(target=self._show_popup, daemon=True).start()
        self._last_click = now

    def run(self):
        try:
            tray_image = Image.open(self.icon_path)
        except Exception as e:
            print(f"Failed to load tray icon: {e}")
            tray_image = Image.new("RGB", (64, 64), color="gray")

        settings_window = SettingsWindow(self.client, self)

        self.icon = Icon(
            "Intervals",
            tray_image,
            menu=Menu(
                MenuItem("Stats", self._on_click, default=True),
                MenuItem("Settings", lambda: threading.Thread(target=settings_window.show, daemon=True).start()),
                MenuItem("Exit", lambda icon: icon.stop())
            )
        )

        threading.Thread(target=self._refresh_loop, daemon=True).start()
        self.icon.run()

class SettingsWindow:
    def __init__(self, client: IntervalsClient, app: TrayApp):
        self.client = client
        self.app = app

    def show(self):
        root = Tk()
        root.title("Settings")
        root.geometry("300x250")
        apply_window_icon(root)

        Label(root, text="Username:").pack(pady=(10, 0))
        api_var = StringVar(value=self.client.username)
        Entry(root, textvariable=api_var, width=40).pack()

        Label(root, text="API Key:").pack(pady=(10, 0))
        pass_var = StringVar(value=self.client.password)
        Entry(root, textvariable=pass_var, width=40).pack()

        Label(root, text="Athlete ID:").pack(pady=(10, 0))
        athlete_var = StringVar(value=self.client.athlete_id)
        Entry(root, textvariable=athlete_var, width=40).pack()

        def save():
            self.client.username = api_var.get()
            self.client.password = pass_var.get()
            self.client.athlete_id = athlete_var.get()
            save_settings(self.client.username, self.client.password, self.client.athlete_id)
            self.app.refresh_stats()
            root.destroy()

        Button(root, text="Save", command=save).pack(pady=20)
        root.mainloop()

if __name__ == "__main__":
    settings = load_settings()
    client = IntervalsClient(
        settings["username"],
        settings["password"],
        settings["athlete_id"]
    )
    app = TrayApp(client, ICON_PATH)
    app.run()
