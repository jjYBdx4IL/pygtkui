# encoding: utf-8
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox
import tkinter as tk

from windows_toasts import Toast, WindowsToaster

LAPPDATA_PATH = Path(os.environ.get('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local')))
CFG_DIR_PATH = LAPPDATA_PATH / 'py_apps' / 'github_update_checker'


class GithubUpdateChecker:
    _instance = None

    @classmethod
    def get_instance(cls):
        return cls._instance

    def __init__(self, github_id, app_name, current_version, db_conn:sqlite3.Connection|None=None, root:tk.Tk|None=None,
                 toaster:WindowsToaster|None=None, check_frequency:int=7*86400, toast_interval:int=86400, min_check_interval:int=86400):
        if GithubUpdateChecker._instance is not None:
            raise RuntimeError("GithubUpdateChecker is a singleton. Use get_instance().")
        GithubUpdateChecker._instance = self

        if not github_id:
            raise ValueError("github_id is required")
        if not app_name:
            raise ValueError("app_name is required")
        if not current_version:
            raise ValueError("current_version is required")

        self.github_id = github_id
        self.app_name = app_name
        self.current_version = current_version
        self.root = root
        self.toaster = toaster
        self.check_frequency = check_frequency
        self.toast_interval = toast_interval
        self.min_check_interval = min_check_interval
        self.own_conn = False
        
        self.last_check = 0.0
        self.last_toast = 0.0
        self.cached_version = ""
        self._is_checking = False
        self._timer_id = None

        if db_conn is None:
            CFG_DIR_PATH.mkdir(parents=True, exist_ok=True)
            db_path = CFG_DIR_PATH / f"{self.github_id.replace('/', '_')}.db"
            self.db_conn:sqlite3.Connection = sqlite3.connect(db_path, check_same_thread=False)
            self.own_conn = True
        else:
            self.db_conn:sqlite3.Connection = db_conn
            
        self._init_db()

    def __del__(self):
        if self.own_conn and self.db_conn:
            try:
                self.db_conn.close()
            except Exception:
                pass

    def _init_db(self):
        with self.db_conn:
            self.db_conn.execute("CREATE TABLE IF NOT EXISTS update_checker (id INTEGER PRIMARY KEY, last_check REAL, last_toast REAL, cached_version TEXT)")
            self.db_conn.execute("INSERT OR IGNORE INTO update_checker (id, last_check, last_toast, cached_version) VALUES (1, 0, 0, '')")
            row = self.db_conn.execute("SELECT last_check, last_toast, cached_version FROM update_checker WHERE id=1").fetchone()
            if row:
                self.last_check, self.last_toast, self.cached_version = row

    def save_state(self):
        with self.db_conn:
            self.db_conn.execute("UPDATE update_checker SET last_check=?, last_toast=?, cached_version=? WHERE id=1", 
                         (self.last_check, self.last_toast, self.cached_version))

    @staticmethod
    def is_newer(remote_ver, local_ver):
        try:
            p1 = [int(x) for x in remote_ver.split('.')]
            p2 = [int(x) for x in local_ver.split('.')]
            return p1 > p2
        except:
            return remote_ver != local_ver

    def fetch_latest_release_info(self, timeout=10):
        url = f"https://api.github.com/repos/{self.github_id}/releases/latest"
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode())
            tag = data.get("tag_name", "")
            html_url = data.get("html_url", "")
            remote_ver = tag.lstrip("v")
            if not tag or not html_url or not remote_ver:
                raise ValueError("Invalid release data")
            logging.debug(f"Fetched latest release info: tag={tag}, html_url={html_url}, remote_ver={remote_ver}")
            return data, remote_ver, html_url, tag

    def show_toast_if_needed(self, toast_interval, toaster: WindowsToaster|None = None) -> bool:
        if self.cached_version and self.cached_version != "ERROR":
            if time.time() > self.last_toast + toast_interval:
                self.last_toast = time.time()
                self.save_state()
                try:
                    data = json.loads(self.cached_version)
                    tag = data.get("tag_name", "")
                    html_url = data.get("html_url", "")
                    self._emit_toast(tag, html_url, toaster)
                    return True
                except Exception as e:
                    logging.error(f"Failed to show update toast: {e}")
        return False

    @staticmethod
    def _emit_toast(tag, html_url, toaster: WindowsToaster|None):
        if not toaster:
            return
        toast = Toast()
        toast.text_fields = ["Update Available", f"New version {tag} is available."]
        def on_activated(_):
            webbrowser.open(html_url)

        toast.on_activated = on_activated
        toaster.show_toast(toast)

    def check_now_interactive(self, root_tk):
        def task():
            try:
                data, remote_ver, html_url, tag = self.fetch_latest_release_info()
                if self.is_newer(remote_ver, self.current_version):
                    toaster = WindowsToaster(self.app_name)
                    root_tk.after(0, lambda: self._emit_toast(tag, html_url, toaster))
                else:
                    root_tk.after(0, lambda: messagebox.showinfo(self.app_name, f"You are up to date (Version {self.current_version})."))
            except Exception as e:
                logging.error(f"Update check failed: {e}")
                err_msg = str(e)
                root_tk.after(0, lambda: messagebox.showerror("Error", f"Update check failed: {err_msg}"))

        threading.Thread(target=task, daemon=True).start()

    def start(self):
        if self._timer_id is None and self.root is not None:
            self._timer_id = self.root.after(1000, self._periodic_check_loop)

    def stop(self):
        if self._timer_id is not None and self.root is not None:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None

    def _periodic_check_loop(self):
        if not self.root:
            return

        now = time.time()
        next_wake_time = now + 3600 # Default 1 hour
        
        try:
            check_ival = self.check_frequency if self.cached_version != "ERROR" else self.min_check_interval
            next_check = self.last_check + check_ival
            
            
            if now > next_check and not self._is_checking:
                self.check_in_background()
            elif next_check < next_wake_time:
                next_wake_time = next_check
            
            self.show_toast_if_needed(self.toast_interval, self.toaster)
            
            if self.cached_version and self.cached_version != "ERROR":
                next_toast = self.last_toast + self.toast_interval
                if next_toast < next_wake_time:
                    next_wake_time = next_toast
        except Exception as e:
            logging.error(f"Update checker loop error: {e}")
            next_wake_time = now + 60

        delay = int((next_wake_time - now) * 1000)
        if delay < 1000: delay = 1000
        self._timer_id = self.root.after(delay, self._periodic_check_loop)

    def check_in_background(self):
        if self._is_checking: return
        self._is_checking = True
        
        def task():
            if self.cached_version and self.cached_version != "ERROR":
                try:
                    data = json.loads(self.cached_version)
                    tag = data.get("tag_name", "")
                    remote_ver = tag.lstrip("v")
                    if self.is_newer(remote_ver, self.current_version):
                        logging.debug("Skipping update check, cached version is already newer.")
                        self._is_checking = False
                        return
                except Exception as e:
                    logging.warning(f"Could not parse cached version, proceeding with fetch: {e}")

            try:
                data, remote_ver, html_url, tag = self.fetch_latest_release_info()
                def on_success():
                    self.last_check = time.time()
                    self.cached_version = json.dumps(data) if self.is_newer(remote_ver, self.current_version) else ""
                    self.save_state()
                    self._is_checking = False
                if self.root: self.root.after(0, on_success)
            except Exception as e:
                logging.error(f"Update check failed: {e}")
                def on_fail():
                    self.last_check = time.time()
                    self.cached_version = "ERROR"
                    self.save_state()
                    self._is_checking = False
                if self.root: self.root.after(0, on_fail)
        
        threading.Thread(target=task, daemon=True).start()
