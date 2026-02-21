# encoding: utf-8
import tkinter as Tk


class Tools:
    @staticmethod
    def center_window(win:Tk.Tk, width, height):
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 3
        win.lift()
        win.grab_set()
        win.focus_force()
        win.geometry(f'{width}x{height}+{x}+{y}')
