# encoding: utf-8
import os
import sys
import tkinter as Tk

IS_DEBUGGER_PRESENT = sys.gettrace() is not None or os.environ.get('VSCODE_PID') or 'debugpy' in sys.modules

class Tools:
    @staticmethod
    def center_window(win:Tk.Tk|Tk.Toplevel, width, height):
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 3
        win.lift()
        win.grab_set()
        win.focus_force()
        win.geometry(f'{width}x{height}+{x}+{y}')

    @staticmethod
    def start_log_memory_footprint_timerloop(win:Tk.Tk):
        if not IS_DEBUGGER_PRESENT:
            return

        import psutil
        import logging
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        
        # 1. Resident Memory (Physical RAM)
        # Known as "Working Set" in Windows Task Manager
        rss_mb = mem_info.rss / (1024 * 1024)
        
        # 2. Swapped Memory (Paged to Disk)
        # This is a Windows-specific attribute in psutil
        swapped_mb = mem_info.pagefile / (1024 * 1024)
        
        # 3. Total Committed Memory
        # Known as "Commit Size" or "Private Bytes"
        # This is roughly equivalent to rss + swapped
        total_committed_mb = mem_info.vms / (1024 * 1024)
        
        logging.debug(f"RAM: rss={rss_mb:.2f}/paged={swapped_mb:.2f}/vms={total_committed_mb:.2f} MB")
        win.after(60000, lambda: Tools.start_log_memory_footprint_timerloop(win))
