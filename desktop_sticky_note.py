import ctypes
import datetime
import json
import time
import traceback
import tkinter as tk
from pathlib import Path
import sys
import winreg
from tkinter import colorchooser, simpledialog
from tkinter import font as tkfont
from ctypes import wintypes


# Win32 constants for SetWindowPos behavior.
HWND_BOTTOM = 1
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512

TRAY_ICON_ID = 1001
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
GWL_WNDPROC = -4

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


def enable_dpi_awareness() -> None:
    # Request modern DPI awareness so Windows doesn't bitmap-scale the app.
    # Bitmap scaling is a common cause of blurry/color-fringed text.
    try:
        user32 = ctypes.windll.user32
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        result = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        if result:
            return
    except Exception:
        pass

    try:
        # Windows 8.1 fallback
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        # Legacy fallback
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", wintypes.BOOL),
        ("SuppressExternalCodecs", wintypes.BOOL),
    ]


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_dir() -> Path:
    d = app_base_dir() / ".desktopStickNote_config"
    d.mkdir(exist_ok=True)
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetFileAttributesW(str(d), 0x2)
        except Exception:
            pass
    return d


def app_storage_path() -> Path:
    return config_dir() / "sticky_note.txt"


def config_storage_path() -> Path:
    return config_dir() / "sticky_note_config.json"


def shade_color(hex_color: str, factor: float = 0.85) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return hex_color
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    red = max(0, min(255, int(red * factor)))
    green = max(0, min(255, int(green * factor)))
    blue = max(0, min(255, int(blue * factor)))
    return f"#{red:02X}{green:02X}{blue:02X}"


def blend_colors(base_hex: str, overlay_hex: str, alpha: float) -> str:
    base = base_hex.lstrip("#")
    overlay = overlay_hex.lstrip("#")
    if len(base) != 6 or len(overlay) != 6:
        return base_hex
    alpha = max(0.0, min(1.0, alpha))

    b_r, b_g, b_b = int(base[0:2], 16), int(base[2:4], 16), int(base[4:6], 16)
    o_r = int(overlay[0:2], 16)
    o_g = int(overlay[2:4], 16)
    o_b = int(overlay[4:6], 16)

    r = int(b_r * (1 - alpha) + o_r * alpha)
    g = int(b_g * (1 - alpha) + o_g * alpha)
    b = int(b_b * (1 - alpha) + o_b * alpha)
    return f"#{r:02X}{g:02X}{b:02X}"


def pick_default_font_family() -> str:
    available = set(tkfont.families())
    # Prioritize smoother UI/CJK-friendly fonts on Windows.
    preferred = [
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI Variable",
        "Segoe UI",
        "Arial",
    ]
    for family in preferred:
        if family in available:
            return family
    return "TkDefaultFont"


class DesktopStickyNoteApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Desktop Sticky Note (Python)")
        self.root.overrideredirect(True)

        self.text_changed = False
        self.file_path = app_storage_path()
        self.config_path = config_storage_path()
        self.logo_png_path = config_dir() / "logo.png"
        self.logo_ico_path = config_dir() / "logo.ico"
        self._register_custom_fonts()
        self.font_family = pick_default_font_family()
        self.font_size = 13
        self.font_color = "#1A1A1A"
        self.background_color = "#FFF8B8"
        self.window_geometry = "420x300+80+80"
        self.startup_enabled = tk.BooleanVar(value=True)
        self.pin_to_top_enabled = tk.BooleanVar(value=False)
        self.tray_icon_enabled = tk.BooleanVar(value=True)
        self.dragger_pinned = tk.BooleanVar(value=False)
        self.show_border = tk.BooleanVar(value=True)
        self.drag_hover_distance = tk.IntVar(value=18)
        self.tab_size = 4
        self.tray_icon_visible = False
        self.tray_hicon = None
        self.tray_hicon_shared = False
        self.load_config()
        self.root.geometry(self.window_geometry)
        self.root.configure(bg=self.background_color)
        self._drag_start_mouse_x = 0
        self._drag_start_mouse_y = 0
        self._drag_start_window_x = 0
        self._drag_start_window_y = 0
        self._is_resizing = False
        self._resize_direction = ""
        self._resize_start_mouse_x = 0
        self._resize_start_mouse_y = 0
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_width = 0
        self._resize_start_height = 0
        self._resize_border = 8
        self._min_width = 260
        self._min_height = 180
        self._keep_on_top_until = 0.0
        self._original_wndproc = None
        self._wndproc_ref = None
        self.selection_color = blend_colors(self.background_color, "#000000", 0.20)
        self._pending_tray_left_click = False
        self._pending_tray_right_click = False
        self._force_hidden_by_tray = False

        self.main_frame = tk.Frame(
            self.root, bg=self.background_color, borderwidth=0, highlightthickness=0
        )
        self.main_frame.pack(fill="both", expand=True)

        self._holder_height = 14
        self._holder_visible = False
        self._holder_hover_zone = self.drag_hover_distance.get()
        self.holder = tk.Canvas(
            self.root,
            width=48,
            height=self._holder_height,
            bg=shade_color(self.background_color, 0.92),
            highlightthickness=0,
            borderwidth=0,
            cursor="fleur",
        )
        self._draw_grip_dots()
        self.holder.place(relx=0.5, y=-self._holder_height, anchor="n")
        self.holder.bind("<ButtonPress-1>", self.start_drag)
        self.holder.bind("<B1-Motion>", self.drag_window)
        self.holder.bind("<ButtonRelease-1>", self.finish_drag)
        self.holder.bind("<Button-3>", self.show_context_menu)
        self.holder.bind("<Enter>", lambda e: self._cancel_holder_hide())
        self.holder.bind("<Leave>", lambda e: None if self.dragger_pinned.get() else self._schedule_holder_hide())
        self.root.bind("<Motion>", self._on_root_motion)

        self.text = tk.Text(
            self.main_frame,
            wrap="word",
            undo=True,
            font=(self.font_family, self.font_size),
            fg=self.font_color,
            bg=self.background_color,
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            highlightcolor=shade_color(self.background_color, 0.65),
            highlightbackground=shade_color(self.background_color, 0.65),
            padx=8,
            pady=8,
            spacing1=1,
            spacing3=2,
            insertwidth=2,
            insertbackground=self.font_color,
            selectbackground=self.selection_color,
            inactiveselectbackground=self.selection_color,
            selectforeground="#111111",
        )
        self.text.pack(side="left", fill="both", expand=True)
        self._apply_tab_size()

        self.text.bind("<<Modified>>", self.on_text_modified)
        self.text.bind("<Button-3>", self.show_context_menu)
        self.text.bind("<Button-1>", self.on_text_left_press)
        self.text.bind("<B1-Motion>", self.on_text_left_drag)
        self.text.bind("<ButtonRelease-1>", self.on_text_left_release)
        self.root.bind("<Button-3>", self.show_context_menu)
        self.root.bind("<FocusIn>", self.defer_bottom_refresh)
        self.root.bind("<Map>", self.defer_bottom_refresh)
        self.root.bind("<Configure>", self.defer_bottom_refresh)
        self.root.bind("<ButtonPress-1>", self.on_resize_press)
        self.root.bind("<B1-Motion>", self.on_resize_drag)
        self.root.bind("<ButtonRelease-1>", self.on_resize_release)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(
            label="Settings\u2026", command=self.open_settings_window
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Exit", command=self.on_close)
        self._settings_win: tk.Toplevel | None = None

        self.install_window_proc_hook()
        self.apply_window_logo()
        self.load_text()
        self.keep_window_bottom()
        self.apply_pin_to_top_state()
        self.apply_startup_state()
        self.update_tray_icon()
        if self.dragger_pinned.get():
            self._show_holder()
        self.apply_border_state()

        # Re-apply bottom z-order regularly so the note stays behind normal windows.
        self.root.after(250, self.bottom_tick)
        # Save shortly after edits.
        self.root.after(600, self.save_tick)
        # Process tray click requests in Tk main thread.
        self.root.after(50, self.process_pending_tray_actions)

    def hwnd(self) -> int:
        return int(self.root.winfo_id())

    def _draw_grip_dots(self) -> None:
        self.holder.delete("dots")
        dot_color = shade_color(self.background_color, 0.55)
        cols, rows = 4, 2
        dot_r = 1.5
        spacing_x, spacing_y = 8, 5
        total_w = (cols - 1) * spacing_x
        total_h = (rows - 1) * spacing_y
        cx = 24
        cy = self._holder_height / 2
        for r in range(rows):
            for c in range(cols):
                x = cx - total_w / 2 + c * spacing_x
                y = cy - total_h / 2 + r * spacing_y
                self.holder.create_oval(
                    x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                    fill=dot_color, outline="", tags="dots",
                )

    def _on_root_motion(self, event: tk.Event) -> None:
        if self._is_resizing:
            return
        direction = self.get_resize_direction(event.x_root, event.y_root)
        self.apply_resize_cursor(direction)
        if self.dragger_pinned.get():
            return
        y_in_window = event.y_root - self.root.winfo_y()
        if y_in_window <= self._holder_hover_zone and not self._holder_visible:
            self._show_holder()
        elif y_in_window > self._holder_hover_zone + self._holder_height + 4:
            if self._holder_visible:
                self._schedule_holder_hide()

    def _show_holder(self) -> None:
        self._holder_visible = True
        self._cancel_holder_hide()
        self._animate_holder(target_y=0)

    def _schedule_holder_hide(self) -> None:
        self._cancel_holder_hide()
        self._holder_hide_id = self.root.after(350, self._hide_holder)

    def _cancel_holder_hide(self) -> None:
        hid = getattr(self, "_holder_hide_id", None)
        if hid:
            self.root.after_cancel(hid)
            self._holder_hide_id = None

    def _hide_holder(self) -> None:
        if self.dragger_pinned.get():
            return
        self._holder_visible = False
        self._animate_holder(target_y=-self._holder_height)

    def _animate_holder(self, target_y: int) -> None:
        info = self.holder.place_info()
        current_y = int(info.get("y", 0))
        if current_y == target_y:
            return
        step = 2 if target_y > current_y else -2
        new_y = current_y + step
        if (step > 0 and new_y > target_y) or (step < 0 and new_y < target_y):
            new_y = target_y
        self.holder.place(relx=0.5, y=new_y, anchor="n")
        if new_y != target_y:
            self.root.after(12, self._animate_holder, target_y)

    def keep_window_bottom(self) -> None:
        if self._force_hidden_by_tray:
            ctypes.windll.user32.SetWindowPos(
                self.hwnd(),
                HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
            )
            ctypes.windll.user32.SetWindowPos(
                self.hwnd(),
                HWND_BOTTOM,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
            )
            return

        if self.pin_to_top_enabled.get():
            ctypes.windll.user32.SetWindowPos(
                self.hwnd(),
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
            )
            return
        if time.monotonic() < self._keep_on_top_until:
            return
        # Ensure the window never remains topmost, then push it to bottom.
        ctypes.windll.user32.SetWindowPos(
            self.hwnd(),
            HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
        )
        ctypes.windll.user32.SetWindowPos(
            self.hwnd(),
            HWND_BOTTOM,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
        )

    def bottom_tick(self) -> None:
        self.keep_window_bottom()
        self.root.after(250, self.bottom_tick)

    def defer_bottom_refresh(self, _event: tk.Event | None = None) -> None:
        self.root.after(1, self.keep_window_bottom)

    def on_text_left_press(self, event: tk.Event) -> str | None:
        self.defer_bottom_refresh()
        return self.on_resize_press(event)

    def on_text_left_drag(self, event: tk.Event) -> str | None:
        if not self._is_resizing:
            return None
        return self.on_resize_drag(event)

    def on_text_left_release(self, event: tk.Event) -> str | None:
        if not self._is_resizing:
            return None
        self.on_resize_release(event)
        return "break"

    def show_context_menu(self, event: tk.Event) -> str:
        self.show_context_menu_at(event.x_root, event.y_root)
        return "break"

    def show_context_menu_at(self, x_root: int, y_root: int) -> None:
        try:
            ctypes.windll.user32.SetForegroundWindow(self.hwnd())
            self.context_menu.tk_popup(x_root, y_root)
        finally:
            # Prevent duplicate/retrigger popup behavior on Windows.
            self.context_menu.grab_release()

    def show_context_menu_from_tray(self) -> None:
        cursor = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
        self.show_context_menu_at(cursor.x, cursor.y)

    def open_settings_window(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        self._settings_win = win
        win.title("Settings")
        win.resizable(False, False)
        win.configure(bg="#F5F5F5")
        win.attributes("-topmost", True)

        pad = {"padx": 12, "pady": 4}
        section_pad = {"padx": 12, "pady": (12, 2)}
        row = 0

        # -- Appearance -------------------------------------------------------
        tk.Label(
            win, text="Appearance", font=("Segoe UI", 10, "bold"),
            bg="#F5F5F5", anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="w", **section_pad)
        row += 1

        tk.Label(win, text="Background color", bg="#F5F5F5").grid(
            row=row, column=0, sticky="w", **pad,
        )
        self._sw_bg_preview = tk.Frame(
            win, width=28, height=18, bg=self.background_color,
            highlightthickness=1, highlightbackground="#999",
        )
        self._sw_bg_preview.grid(row=row, column=1, **pad)
        tk.Button(
            win, text="Pick\u2026", width=6, command=self._sw_pick_bg_color,
        ).grid(row=row, column=2, **pad)
        row += 1

        tk.Label(win, text="Font color", bg="#F5F5F5").grid(
            row=row, column=0, sticky="w", **pad,
        )
        self._sw_fc_preview = tk.Frame(
            win, width=28, height=18, bg=self.font_color,
            highlightthickness=1, highlightbackground="#999",
        )
        self._sw_fc_preview.grid(row=row, column=1, **pad)
        tk.Button(
            win, text="Pick\u2026", width=6, command=self._sw_pick_font_color,
        ).grid(row=row, column=2, **pad)
        row += 1

        # -- Font -------------------------------------------------------------
        tk.Label(
            win, text="Font", font=("Segoe UI", 10, "bold"),
            bg="#F5F5F5", anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="w", **section_pad)
        row += 1

        tk.Label(win, text="Family", bg="#F5F5F5").grid(
            row=row, column=0, sticky="w", padx=12, pady=(4, 0),
        )
        tk.Button(
            win, text="Load .ttf\u2026", width=8, command=self._sw_load_ttf,
        ).grid(row=row, column=2, sticky="e", padx=12, pady=(4, 0))
        row += 1

        font_frame = tk.Frame(win, bg="#F5F5F5")
        font_frame.grid(row=row, column=0, columnspan=3, sticky="we", **pad)
        font_frame.columnconfigure(0, weight=1)

        self._sw_font_search_var = tk.StringVar()
        font_search = tk.Entry(
            font_frame, textvariable=self._sw_font_search_var, width=28,
        )
        font_search.pack(fill="x", pady=(0, 2))
        font_search.insert(0, self.font_family)
        self._sw_font_search_var.trace_add("write", lambda *_: self._sw_filter_fonts())

        list_frame = tk.Frame(font_frame)
        list_frame.pack(fill="x")
        font_scroll = tk.Scrollbar(list_frame, orient="vertical")
        self._sw_font_list = tk.Listbox(
            list_frame, height=6, width=28,
            yscrollcommand=font_scroll.set, exportselection=False,
        )
        font_scroll.configure(command=self._sw_font_list.yview)
        self._sw_font_list.pack(side="left", fill="x", expand=True)
        font_scroll.pack(side="right", fill="y")

        self._sw_all_families = sorted(set(tkfont.families()))
        self._sw_populate_font_list(self._sw_all_families)
        self._sw_select_font_in_list(self.font_family)

        self._sw_font_list.bind("<<ListboxSelect>>", self._sw_on_font_select)
        self._sw_font_list.bind("<MouseWheel>", self._sw_on_font_wheel)
        row += 1

        tk.Label(win, text="Size", bg="#F5F5F5").grid(
            row=row, column=0, sticky="w", **pad,
        )
        self._sw_size_var = tk.IntVar(value=self.font_size)
        size_spin = tk.Spinbox(
            win, from_=8, to=72, width=5, textvariable=self._sw_size_var,
            command=self._sw_apply_font_size,
        )
        size_spin.grid(row=row, column=1, sticky="w", **pad)
        size_spin.bind("<Return>", lambda e: self._sw_apply_font_size())
        row += 1

        tk.Label(win, text="Tab size", bg="#F5F5F5").grid(
            row=row, column=0, sticky="w", **pad,
        )
        self._sw_tab_var = tk.IntVar(value=self.tab_size)
        tab_spin = tk.Spinbox(
            win, from_=1, to=16, width=5, textvariable=self._sw_tab_var,
            command=self._sw_apply_tab_size,
        )
        tab_spin.grid(row=row, column=1, sticky="w", **pad)
        tab_spin.bind("<Return>", lambda e: self._sw_apply_tab_size())
        row += 1

        # -- Behaviour --------------------------------------------------------
        tk.Label(
            win, text="Behaviour", font=("Segoe UI", 10, "bold"),
            bg="#F5F5F5", anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="w", **section_pad)
        row += 1

        tk.Checkbutton(
            win, text="Launch at Windows startup", bg="#F5F5F5",
            variable=self.startup_enabled, command=self.toggle_startup_launch,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        tk.Checkbutton(
            win, text="Pin to top", bg="#F5F5F5",
            variable=self.pin_to_top_enabled, command=self.toggle_pin_to_top,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        tk.Checkbutton(
            win, text="Show taskbar tray icon", bg="#F5F5F5",
            variable=self.tray_icon_enabled, command=self.toggle_tray_icon,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        tk.Checkbutton(
            win, text="Pin drag handle", bg="#F5F5F5",
            variable=self.dragger_pinned, command=self.toggle_dragger_pinned,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        tk.Label(win, text="Drag handle reveal distance", bg="#F5F5F5").grid(
            row=row, column=0, sticky="w", **pad,
        )
        hover_slider = tk.Scale(
            win, from_=5, to=80, orient="horizontal",
            variable=self.drag_hover_distance,
            bg="#F5F5F5", highlightthickness=0, length=140,
            command=lambda _: self._on_hover_distance_changed(),
        )
        hover_slider.grid(row=row, column=1, columnspan=2, sticky="w", **pad)
        row += 1

        tk.Checkbutton(
            win, text="Show border", bg="#F5F5F5",
            variable=self.show_border, command=self.toggle_border,
        ).grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        row += 1

        # Bottom padding
        tk.Frame(win, height=8, bg="#F5F5F5").grid(
            row=row, column=0, columnspan=3,
        )

        win.update_idletasks()
        wx = self.root.winfo_x() + self.root.winfo_width() + 8
        wy = self.root.winfo_y()
        win.geometry(f"+{wx}+{wy}")

    def _sw_pick_bg_color(self) -> None:
        _, color_hex = colorchooser.askcolor(
            color=self.background_color, parent=self._settings_win,
        )
        if not color_hex:
            return
        self.background_color = color_hex
        self.selection_color = blend_colors(self.background_color, "#000000", 0.20)
        self.root.configure(bg=self.background_color)
        self.main_frame.configure(bg=self.background_color)
        self.holder.configure(bg=shade_color(self.background_color, 0.92))
        self._draw_grip_dots()
        self.text.configure(
            bg=self.background_color,
            selectbackground=self.selection_color,
            inactiveselectbackground=self.selection_color,
        )
        self.apply_border_state()
        self._sw_bg_preview.configure(bg=self.background_color)
        self.text_changed = True
        self.save_config()

    def _sw_pick_font_color(self) -> None:
        _, color_hex = colorchooser.askcolor(
            color=self.font_color, parent=self._settings_win,
        )
        if not color_hex:
            return
        self.font_color = color_hex
        self.text.configure(fg=self.font_color, insertbackground=self.font_color)
        self._sw_fc_preview.configure(bg=self.font_color)
        self.text_changed = True
        self.save_config()

    def _sw_populate_font_list(self, families: list[str]) -> None:
        self._sw_font_list.delete(0, "end")
        for f in families:
            self._sw_font_list.insert("end", f)

    def _sw_select_font_in_list(self, name: str) -> None:
        items = self._sw_font_list.get(0, "end")
        for i, item in enumerate(items):
            if item == name:
                self._sw_font_list.selection_clear(0, "end")
                self._sw_font_list.selection_set(i)
                self._sw_font_list.see(i)
                return

    def _sw_filter_fonts(self) -> None:
        query = self._sw_font_search_var.get().lower()
        if not query:
            filtered = self._sw_all_families
        else:
            filtered = [f for f in self._sw_all_families if query in f.lower()]
        self._sw_populate_font_list(filtered)
        if filtered:
            self._sw_font_list.selection_set(0)

    def _sw_on_font_select(self, _event: tk.Event) -> None:
        sel = self._sw_font_list.curselection()
        if not sel:
            return
        chosen = self._sw_font_list.get(sel[0])
        if chosen and chosen in set(tkfont.families()):
            self.font_family = chosen
            self.apply_text_font()

    def _sw_on_font_wheel(self, event: tk.Event) -> None:
        self._sw_font_list.yview_scroll(-1 * (event.delta // 120), "units")

    def _sw_load_ttf(self) -> None:
        from tkinter import filedialog
        import shutil
        path = filedialog.askopenfilename(
            title="Select a .ttf font file",
            filetypes=[("TrueType Font", "*.ttf"), ("OpenType Font", "*.otf")],
            parent=self._settings_win,
        )
        if not path:
            return
        src = Path(path)
        dest = config_dir() / src.name
        shutil.copy2(src, dest)

        gdi32 = ctypes.windll.gdi32
        added = gdi32.AddFontResourceW(str(dest))
        if added:
            HWND_BROADCAST = 0xFFFF
            WM_FONTCHANGE = 0x001D
            ctypes.windll.user32.SendMessageW(
                HWND_BROADCAST, WM_FONTCHANGE, 0, 0,
            )

        custom = self._load_custom_font_list()
        if str(dest) not in custom:
            custom.append(str(dest))
            self._save_custom_font_list(custom)

        self._sw_all_families = sorted(set(tkfont.families()))
        self._sw_filter_fonts()

    def _custom_fonts_path(self) -> Path:
        return config_dir() / "custom_fonts.json"

    def _load_custom_font_list(self) -> list[str]:
        p = self._custom_fonts_path()
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_custom_font_list(self, fonts: list[str]) -> None:
        try:
            self._custom_fonts_path().write_text(
                json.dumps(fonts, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _register_custom_fonts(self) -> None:
        gdi32 = ctypes.windll.gdi32
        for font_path in self._load_custom_font_list():
            if Path(font_path).exists():
                gdi32.AddFontResourceW(font_path)

    def _sw_apply_font(self) -> None:
        chosen = getattr(self, "_sw_font_var", None)
        if chosen:
            val = chosen.get()
            if val and val in set(tkfont.families()):
                self.font_family = val
                self.apply_text_font()

    def _sw_apply_font_size(self) -> None:
        try:
            val = self._sw_size_var.get()
        except (tk.TclError, ValueError):
            return
        if 8 <= val <= 72:
            self.font_size = val
            self.apply_text_font()

    def _sw_apply_tab_size(self) -> None:
        try:
            val = self._sw_tab_var.get()
        except (tk.TclError, ValueError):
            return
        if 1 <= val <= 16:
            self.tab_size = val
            self._apply_tab_size()
            self.save_config()

    def apply_window_logo(self) -> None:
        if not self.logo_png_path.exists():
            return
        try:
            photo = tk.PhotoImage(file=str(self.logo_png_path))
        except tk.TclError:
            return
        self.root.iconphoto(True, photo)
        # Keep a reference to avoid image garbage collection.
        self._window_logo_photo = photo

    def load_hicon_from_png(self):
        if not self.logo_png_path.exists():
            return None

        gdiplus = ctypes.windll.gdiplus
        token = ctypes.c_size_t(0)
        startup_input = GdiplusStartupInput(1, None, False, False)

        startup_status = gdiplus.GdiplusStartup(
            ctypes.byref(token), ctypes.byref(startup_input), None
        )
        if startup_status != 0:
            return None

        bitmap = ctypes.c_void_p()
        hicon = wintypes.HICON()
        try:
            create_status = gdiplus.GdipCreateBitmapFromFile(
                str(self.logo_png_path), ctypes.byref(bitmap)
            )
            if create_status != 0 or not bitmap.value:
                return None

            icon_status = gdiplus.GdipCreateHICONFromBitmap(
                bitmap, ctypes.byref(hicon)
            )
            if icon_status != 0 or not hicon:
                return None
            return hicon
        finally:
            if bitmap.value:
                gdiplus.GdipDisposeImage(bitmap)
            gdiplus.GdiplusShutdown(token)

    def load_tray_hicon(self):
        user32 = ctypes.windll.user32
        png_hicon = self.load_hicon_from_png()
        if png_hicon:
            self.tray_hicon_shared = False
            return png_hicon

        if self.logo_ico_path.exists():
            hicon = user32.LoadImageW(
                None,
                str(self.logo_ico_path),
                IMAGE_ICON,
                0,
                0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            if hicon:
                self.tray_hicon_shared = False
                return hicon
        self.tray_hicon_shared = True
        return user32.LoadIconW(None, IDI_APPLICATION)

    def build_notify_icon_data(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd()
        nid.uID = TRAY_ICON_ID
        nid.uFlags = NIF_ICON | NIF_TIP | NIF_MESSAGE
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.tray_hicon
        nid.szTip = "Desktop Sticky Note"
        return nid

    def add_tray_icon(self) -> None:
        if self.tray_icon_visible:
            return
        self.tray_hicon = self.load_tray_hicon()
        nid = self.build_notify_icon_data()
        if ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            self.tray_icon_visible = True

    def remove_tray_icon(self) -> None:
        if not self.tray_icon_visible:
            return
        nid = self.build_notify_icon_data()
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self.tray_icon_visible = False
        if self.tray_hicon and not self.tray_hicon_shared:
            ctypes.windll.user32.DestroyIcon(self.tray_hicon)
        self.tray_hicon = None

    def update_tray_icon(self) -> None:
        if self.tray_icon_enabled.get():
            self.add_tray_icon()
        else:
            self.remove_tray_icon()

    def toggle_tray_icon(self) -> None:
        self.update_tray_icon()
        self.save_config()

    def toggle_dragger_pinned(self) -> None:
        if self.dragger_pinned.get():
            self._show_holder()
        else:
            self._schedule_holder_hide()
        self.save_config()

    def _on_hover_distance_changed(self, *_args) -> None:
        self._holder_hover_zone = self.drag_hover_distance.get()
        self.save_config()

    def apply_border_state(self) -> None:
        if self.show_border.get():
            border_color = shade_color(self.background_color, 0.65)
            self.text.configure(
                relief="solid", borderwidth=1,
                highlightthickness=1,
                highlightcolor=border_color,
                highlightbackground=border_color,
            )
        else:
            self.text.configure(
                relief="flat", borderwidth=0,
                highlightthickness=0,
            )

    def toggle_border(self) -> None:
        self.apply_border_state()
        self.save_config()

    def _apply_tab_size(self) -> None:
        space_width = tkfont.Font(
            family=self.font_family, size=self.font_size
        ).measure(" ")
        self.text.configure(tabs=(space_width * self.tab_size,))

    def change_tab_size(self) -> None:
        new_size = simpledialog.askinteger(
            "Tab Size",
            "Enter tab width in spaces (1-16):",
            initialvalue=self.tab_size,
            minvalue=1,
            maxvalue=16,
            parent=self.root,
        )
        if not new_size:
            return
        self.tab_size = new_size
        self._apply_tab_size()
        self.save_config()

    def get_startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            return f'"{Path(sys.executable).resolve()}"'

        script_path = Path(__file__).resolve()
        python_exe = Path(sys.executable).resolve()
        pythonw_exe = python_exe.with_name("pythonw.exe")
        launcher = pythonw_exe if pythonw_exe.exists() else python_exe
        return f'"{launcher}" "{script_path}"'

    def apply_startup_state(self) -> None:
        run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        value_name = "DesktopStickyNote"

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                run_key_path,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            ) as key:
                if self.startup_enabled.get():
                    winreg.SetValueEx(
                        key,
                        value_name,
                        0,
                        winreg.REG_SZ,
                        self.get_startup_command(),
                    )
                else:
                    try:
                        winreg.DeleteValue(key, value_name)
                    except FileNotFoundError:
                        pass
        except OSError:
            # Keep app running even if registry access fails.
            return

    def toggle_startup_launch(self) -> None:
        self.apply_startup_state()
        self.save_config()

    def apply_pin_to_top_state(self) -> None:
        if self.pin_to_top_enabled.get():
            self._keep_on_top_until = 0.0
            ctypes.windll.user32.SetWindowPos(
                self.hwnd(),
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOOWNERZORDER,
            )
            self.root.lift()
        else:
            self._keep_on_top_until = 0.0
            ctypes.windll.user32.SetWindowPos(
                self.hwnd(),
                HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
            )
            self.keep_window_bottom()

    def toggle_pin_to_top(self) -> None:
        self.apply_pin_to_top_state()
        self.save_config()

    def toggle_note_visibility_from_tray(self) -> None:
        if self._force_hidden_by_tray:
            self._force_hidden_by_tray = False
            self._keep_on_top_until = 0.0
            self.root.deiconify()
            self.root.update_idletasks()
            ctypes.windll.user32.SetWindowPos(
                self.hwnd(),
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOOWNERZORDER,
            )
            self.root.lift()
            ctypes.windll.user32.SetForegroundWindow(self.hwnd())
        else:
            self._keep_on_top_until = 0.0
            self._force_hidden_by_tray = True
            self.keep_window_bottom()

    def process_pending_tray_actions(self) -> None:
        if self._pending_tray_left_click:
            self._pending_tray_left_click = False
            self.toggle_note_visibility_from_tray()

        if self._pending_tray_right_click:
            self._pending_tray_right_click = False
            self.show_context_menu_from_tray()

        self.root.after(50, self.process_pending_tray_actions)

    def install_window_proc_hook(self) -> None:
        user32 = ctypes.windll.user32
        hwnd = self.hwnd()

        if self._original_wndproc is not None:
            return

        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]

        def custom_wndproc(hwnd_value, msg, wparam, lparam):
            if msg == WM_TRAYICON and lparam == WM_LBUTTONUP:
                self._pending_tray_left_click = True
                return 0
            if msg == WM_TRAYICON and lparam in {WM_RBUTTONUP, WM_CONTEXTMENU}:
                self._pending_tray_right_click = True
                return 0
            return user32.CallWindowProcW(
                self._original_wndproc, hwnd_value, msg, wparam, lparam
            )

        self._wndproc_ref = WNDPROC(custom_wndproc)
        self._original_wndproc = user32.SetWindowLongPtrW(
            hwnd, GWL_WNDPROC, ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        )

    def uninstall_window_proc_hook(self) -> None:
        if self._original_wndproc is None:
            return
        ctypes.windll.user32.SetWindowLongPtrW(
            self.hwnd(), GWL_WNDPROC, self._original_wndproc
        )
        self._original_wndproc = None
        self._wndproc_ref = None

    def start_drag(self, event: tk.Event) -> None:
        self._drag_start_mouse_x = event.x_root
        self._drag_start_mouse_y = event.y_root
        self._drag_start_window_x = self.root.winfo_x()
        self._drag_start_window_y = self.root.winfo_y()

    def drag_window(self, event: tk.Event) -> None:
        delta_x = event.x_root - self._drag_start_mouse_x
        delta_y = event.y_root - self._drag_start_mouse_y
        new_x = self._drag_start_window_x + delta_x
        new_y = self._drag_start_window_y + delta_y
        self.root.geometry(f"+{new_x}+{new_y}")

    def finish_drag(self, _event: tk.Event) -> None:
        self.save_config()

    def get_resize_direction(self, x_root: int, y_root: int) -> str:
        left = self.root.winfo_x()
        top = self.root.winfo_y()
        right = left + self.root.winfo_width()
        bottom = top + self.root.winfo_height()
        border = self._resize_border

        near_left = x_root <= left + border
        near_right = x_root >= right - border
        near_top = y_root <= top + border
        near_bottom = y_root >= bottom - border

        if near_top and near_left:
            return "nw"
        if near_top and near_right:
            return "ne"
        if near_bottom and near_left:
            return "sw"
        if near_bottom and near_right:
            return "se"
        if near_left:
            return "w"
        if near_right:
            return "e"
        if near_top:
            return "n"
        if near_bottom:
            return "s"
        return ""

    def apply_resize_cursor(self, direction: str) -> None:
        cursor = ""
        if direction in {"nw", "se"}:
            cursor = "size_nw_se"
        elif direction in {"ne", "sw"}:
            cursor = "size_ne_sw"
        elif direction in {"e", "w"}:
            cursor = "size_we"
        elif direction in {"n", "s"}:
            cursor = "size_ns"

        self.root.configure(cursor=cursor)
        self.main_frame.configure(cursor=cursor)
        self.text.configure(cursor=cursor or "xterm")

    def on_resize_motion(self, event: tk.Event) -> None:
        if self._is_resizing:
            return
        direction = self.get_resize_direction(event.x_root, event.y_root)
        self.apply_resize_cursor(direction)

    def on_resize_press(self, event: tk.Event) -> str | None:
        if event.widget == self.holder:
            return None

        direction = self.get_resize_direction(event.x_root, event.y_root)
        if not direction:
            return None

        self._is_resizing = True
        self._resize_direction = direction
        self._resize_start_mouse_x = event.x_root
        self._resize_start_mouse_y = event.y_root
        self._resize_start_x = self.root.winfo_x()
        self._resize_start_y = self.root.winfo_y()
        self._resize_start_width = self.root.winfo_width()
        self._resize_start_height = self.root.winfo_height()
        self.apply_resize_cursor(direction)
        return "break"

    def on_resize_drag(self, event: tk.Event) -> str | None:
        if not self._is_resizing:
            return None

        delta_x = event.x_root - self._resize_start_mouse_x
        delta_y = event.y_root - self._resize_start_mouse_y

        new_x = self._resize_start_x
        new_y = self._resize_start_y
        new_width = self._resize_start_width
        new_height = self._resize_start_height

        if "e" in self._resize_direction:
            new_width = max(self._min_width, self._resize_start_width + delta_x)
        if "s" in self._resize_direction:
            new_height = max(self._min_height, self._resize_start_height + delta_y)
        if "w" in self._resize_direction:
            candidate_width = self._resize_start_width - delta_x
            if candidate_width < self._min_width:
                new_width = self._min_width
                new_x = self._resize_start_x + (self._resize_start_width - self._min_width)
            else:
                new_width = candidate_width
                new_x = self._resize_start_x + delta_x
        if "n" in self._resize_direction:
            candidate_height = self._resize_start_height - delta_y
            if candidate_height < self._min_height:
                new_height = self._min_height
                new_y = self._resize_start_y + (
                    self._resize_start_height - self._min_height
                )
            else:
                new_height = candidate_height
                new_y = self._resize_start_y + delta_y

        self.root.geometry(f"{int(new_width)}x{int(new_height)}+{int(new_x)}+{int(new_y)}")
        return "break"

    def on_resize_release(self, event: tk.Event) -> None:
        if not self._is_resizing:
            return
        self._is_resizing = False
        direction = self.get_resize_direction(event.x_root, event.y_root)
        self.apply_resize_cursor(direction)
        self.save_config()

    def change_background_color(self) -> None:
        _, color_hex = colorchooser.askcolor(color=self.background_color, parent=self.root)
        if not color_hex:
            return
        self.background_color = color_hex
        self.selection_color = blend_colors(self.background_color, "#000000", 0.20)
        self.root.configure(bg=self.background_color)
        self.main_frame.configure(bg=self.background_color)
        self.holder.configure(bg=shade_color(self.background_color, 0.92))
        self._draw_grip_dots()
        self.text.configure(
            bg=self.background_color,
            selectbackground=self.selection_color,
            inactiveselectbackground=self.selection_color,
        )
        self.apply_border_state()
        self.text_changed = True
        self.save_config()

    def apply_text_font(self) -> None:
        self.text.configure(font=(self.font_family, self.font_size))
        self._apply_tab_size()
        self.text_changed = True
        self.save_config()

    def change_font_color(self) -> None:
        _, color_hex = colorchooser.askcolor(color=self.font_color, parent=self.root)
        if not color_hex:
            return
        self.font_color = color_hex
        self.text.configure(fg=self.font_color, insertbackground=self.font_color)
        self.text_changed = True
        self.save_config()

    def change_font_size(self) -> None:
        new_size = simpledialog.askinteger(
            "Font Size",
            "Enter font size (8-72):",
            initialvalue=self.font_size,
            minvalue=8,
            maxvalue=72,
            parent=self.root,
        )
        if not new_size:
            return
        self.font_size = new_size
        self.apply_text_font()

    def change_font(self) -> None:
        families = sorted(set(tkfont.families()))
        preferred = [
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Segoe UI Variable",
            "Segoe UI",
            "Calibri",
            "Arial",
        ]
        suggestions = ", ".join([name for name in preferred if name in families])

        chosen_font = simpledialog.askstring(
            "Font",
            "Enter font family name.\n"
            f"Try one of: {suggestions}",
            initialvalue=self.font_family,
            parent=self.root,
        )
        if not chosen_font:
            return
        if chosen_font not in families:
            return
        self.font_family = chosen_font
        self.apply_text_font()

    def on_text_modified(self, _event=None) -> None:
        if self.text.edit_modified():
            self.text_changed = True
            self.text.edit_modified(False)

    def load_text(self) -> None:
        if not self.file_path.exists():
            return
        try:
            content = self.file_path.read_text(encoding="utf-8")
        except OSError:
            return

        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_modified(False)
        self.text_changed = False

    def save_text(self) -> None:
        try:
            content = self.text.get("1.0", "end-1c")
            self.file_path.write_text(content, encoding="utf-8")
        except OSError:
            return
        self.text_changed = False

    def save_tick(self) -> None:
        if self.text_changed:
            self.save_text()
        self.root.after(600, self.save_tick)

    def on_close(self) -> None:
        if self.text_changed:
            self.save_text()
        self.save_config()
        self.remove_tray_icon()
        self.uninstall_window_proc_hook()
        self._unregister_custom_fonts()
        self.root.destroy()

    def _unregister_custom_fonts(self) -> None:
        gdi32 = ctypes.windll.gdi32
        for font_path in self._load_custom_font_list():
            if Path(font_path).exists():
                gdi32.RemoveFontResourceW(font_path)

    def load_config(self) -> None:
        if not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, dict):
            return

        color = data.get("background_color")
        if isinstance(color, str) and len(color) == 7 and color.startswith("#"):
            self.background_color = color

        size = data.get("font_size")
        if isinstance(size, int) and 8 <= size <= 72:
            self.font_size = size

        family = data.get("font_family")
        if isinstance(family, str) and family in set(tkfont.families()):
            self.font_family = family

        font_color = data.get("font_color")
        if isinstance(font_color, str) and len(font_color) == 7 and font_color.startswith("#"):
            self.font_color = font_color

        show_tray = data.get("show_tray_icon")
        if isinstance(show_tray, bool):
            self.tray_icon_enabled.set(show_tray)

        pin_to_top = data.get("pin_to_top")
        if isinstance(pin_to_top, bool):
            self.pin_to_top_enabled.set(pin_to_top)

        startup = data.get("launch_at_startup")
        if isinstance(startup, bool):
            self.startup_enabled.set(startup)

        geometry = data.get("window_geometry")
        if isinstance(geometry, str) and "x" in geometry and "+" in geometry:
            self.window_geometry = geometry

        dragger_pin = data.get("dragger_pinned")
        if isinstance(dragger_pin, bool):
            self.dragger_pinned.set(dragger_pin)

        border = data.get("show_border")
        if isinstance(border, bool):
            self.show_border.set(border)

        hover_dist = data.get("drag_hover_distance")
        if isinstance(hover_dist, int) and 5 <= hover_dist <= 80:
            self.drag_hover_distance.set(hover_dist)

        tab = data.get("tab_size")
        if isinstance(tab, int) and 1 <= tab <= 16:
            self.tab_size = tab

    def save_config(self) -> None:
        config = {
            "background_color": self.background_color,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_color": self.font_color,
            "launch_at_startup": bool(self.startup_enabled.get()),
            "pin_to_top": bool(self.pin_to_top_enabled.get()),
            "show_tray_icon": bool(self.tray_icon_enabled.get()),
            "window_geometry": self.root.geometry(),
            "dragger_pinned": bool(self.dragger_pinned.get()),
            "show_border": bool(self.show_border.get()),
            "drag_hover_distance": self.drag_hover_distance.get(),
            "tab_size": self.tab_size,
        }
        try:
            self.config_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return


_clean_exit = False


def write_crash_log(exc: BaseException) -> Path:
    log_dir = config_dir() / "log"
    log_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"crash_{stamp}.log"
    lines = [
        f"Crash at: {datetime.datetime.now().isoformat()}",
        f"Python: {sys.version}",
        f"Executable: {sys.executable}",
        f"Frozen: {getattr(sys, 'frozen', False)}",
        "",
        "Traceback:",
        traceback.format_exc(),
    ]
    log_file.write_text("\n".join(lines), encoding="utf-8")
    return log_file


def show_crash_dialog(log_file: Path) -> None:
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _r = _tk.Tk()
        _r.withdraw()
        _mb.showerror(
            "Desktop Sticky Note - Crash",
            f"The application crashed unexpectedly.\n\n"
            f"A crash log has been saved to:\n{log_file}",
        )
        _r.destroy()
    except Exception:
        pass


def main() -> None:
    global _clean_exit
    enable_dpi_awareness()
    root = tk.Tk()
    app = DesktopStickyNoteApp(root)

    _orig_on_close = app.on_close
    def patched_on_close():
        global _clean_exit
        _clean_exit = True
        _orig_on_close()
    app.on_close = patched_on_close
    root.protocol("WM_DELETE_WINDOW", patched_on_close)

    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except BaseException as exc:
        if not _clean_exit:
            log_file = write_crash_log(exc)
            show_crash_dialog(log_file)
        raise
