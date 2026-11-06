"""Ventanas y mouse de Windows. Las coordenadas son píxeles físicos de pantalla."""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

GW_HWNDNEXT = 2
GW_HWNDPREV = 3
GW_OWNER = 4
GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_MINIMIZEBOX = 0x20000
WS_EX_TRANSPARENT = 0x20
WS_EX_TOOLWINDOW = 0x80
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SPI_GETWORKAREA = 0x30
MOUSEEVENTF_WHEEL = 0x800
WHEEL_DELTA = 120
SWP_NOSIZE = 0x1
SWP_NOMOVE = 0x2
SWP_NOZORDER = 0x4
SWP_NOACTIVATE = 0x10
HWND_TOP = 0
DWMWA_CLOAKED = 14
MOUSEEVENTF_LEFTDOWN = 0x2
MOUSEEVENTF_LEFTUP = 0x4
MOUSEEVENTF_RIGHTDOWN = 0x8
MOUSEEVENTF_RIGHTUP = 0x10
DESKTOP_CLASSES = {"Progman", "WorkerW"}
STOP_CLASSES = DESKTOP_CLASSES | {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

HWND = wintypes.HWND
user32.GetTopWindow.argtypes = [HWND]
user32.GetTopWindow.restype = HWND
user32.GetWindow.argtypes = [HWND, wintypes.UINT]
user32.GetWindow.restype = HWND
user32.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [HWND]
user32.IsIconic.argtypes = [HWND]
user32.IsZoomed.argtypes = [HWND]
user32.IsWindow.argtypes = [HWND]
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
dwmapi.DwmGetWindowAttribute.argtypes = [HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def class_name(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def is_cloaked(hwnd) -> bool:
    value = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return value.value != 0


def window_rect(hwnd) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def top_down():
    """Ventanas de nivel superior, de la que está más al frente a la del fondo."""
    hwnd = user32.GetTopWindow(None)
    while hwnd:
        yield hwnd
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)


def place_above_desktop(hwnd) -> None:
    """Deja la ventana justo encima del escritorio y debajo de todas las demás."""
    for candidate in top_down():
        if user32.IsWindowVisible(candidate) and class_name(candidate) in DESKTOP_CLASSES:
            above = user32.GetWindow(candidate, GW_HWNDPREV)
            if above and above != hwnd:
                user32.SetWindowPos(hwnd, above, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            return


class Windows:
    def __init__(self, exclude: set[int]):
        self.exclude = exclude

    def at(self, x: float, y: float):
        for hwnd in top_down():
            if hwnd in self.exclude or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or is_cloaked(hwnd):
                continue
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            if style & (WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW):
                continue
            left, top, width, height = window_rect(hwnd)
            if not (left <= x < left + width and top <= y < top + height):
                continue
            # El escritorio y la barra de tareas no se mueven.
            return None if class_name(hwnd) in STOP_CLASSES else hwnd
        return None

    def rect(self, hwnd):
        return window_rect(hwnd)

    def is_maximized(self, hwnd) -> bool:
        return bool(user32.IsZoomed(hwnd))

    def restore(self, hwnd) -> None:
        user32.ShowWindow(hwnd, SW_RESTORE)

    def bring_to_front(self, hwnd) -> None:
        user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def set_rect(self, hwnd, x, y, width, height) -> None:
        if user32.IsZoomed(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetWindowPos(hwnd, None, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE)

    def minimize(self, hwnd) -> None:
        user32.ShowWindow(hwnd, SW_MINIMIZE)

    def _is_app_window(self, hwnd) -> bool:
        """Una ventana normal de una app, de las que salen en la barra de tareas."""
        if hwnd in self.exclude or not user32.IsWindowVisible(hwnd) or is_cloaked(hwnd):
            return False
        if user32.GetWindow(hwnd, GW_OWNER) or class_name(hwnd) in STOP_CLASSES:
            return False
        if user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & (WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW):
            return False
        return bool(user32.GetWindowLongPtrW(hwnd, GWL_STYLE) & WS_MINIMIZEBOX)

    def minimize_all(self) -> list:
        """Minimiza las ventanas de apps visibles, sin tocar el holograma (Win+D lo escondería)."""
        minimized = []
        for hwnd in list(top_down()):
            if not user32.IsIconic(hwnd) and self._is_app_window(hwnd):
                user32.ShowWindow(hwnd, SW_MINIMIZE)
                minimized.append(hwnd)
        return minimized

    def app_windows(self) -> list[dict]:
        """Las ventanas que salen en la barra de tareas, de la usada más recientemente a la más antigua."""
        found = []
        for hwnd in top_down():
            if self._is_app_window(hwnd):
                title = window_title(hwnd)
                if title:
                    found.append({"hwnd": hwnd, "title": title, "minimized": bool(user32.IsIconic(hwnd)),
                                  "active": hwnd == user32.GetForegroundWindow()})
        return found

    def is_minimized(self, hwnd) -> bool:
        return bool(user32.IsWindow(hwnd) and user32.IsIconic(hwnd))

    def last_minimized(self):
        """Alguna ventana minimizada, para cuando no sabemos cuál se minimizó última."""
        return next((hwnd for hwnd in top_down() if user32.IsIconic(hwnd) and self._is_app_window(hwnd)), None)

    def restore_all(self, hwnds: list) -> None:
        for hwnd in reversed(hwnds):
            if user32.IsWindow(hwnd) and user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)

    def maximize(self, hwnd) -> None:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)


WM_GETICON = 0x7F
SMTO_ABORTIFHUNG = 0x2
GCLP_HICON = -14
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x2
user32.SendMessageTimeoutW.argtypes = [HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT,
                                       wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.GetClassLongPtrW.argtypes = [HWND, ctypes.c_int]
user32.GetClassLongPtrW.restype = ctypes.c_size_t
user32.SetForegroundWindow.argtypes = [HWND]
user32.GetForegroundWindow.restype = HWND


def window_title(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buffer, 256)
    return buffer.value


def window_icon(hwnd) -> int:
    """El ícono de la ventana (HICON), o 0. Con tiempo límite: una app colgada no frena al holograma."""
    for kind in (1, 2, 0):  # grande, pequeño de la app, pequeño
        result = ctypes.c_size_t(0)
        if user32.SendMessageTimeoutW(hwnd, WM_GETICON, kind, 0, SMTO_ABORTIFHUNG, 50, ctypes.byref(result)) and result.value:
            return result.value
    return user32.GetClassLongPtrW(hwnd, GCLP_HICON)


WM_CLOSE = 0x10
user32.PostMessageW.argtypes = [HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def process_name(hwnd) -> str:
    import psutil

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name()
    except psutil.Error:
        return ""


def close_window(hwnd) -> None:
    """Como pulsar la X de la ventana."""
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def activate(hwnd) -> None:
    """Trae la ventana al frente, restaurándola si estaba minimizada."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows solo deja pasar el foco a otra app justo después de usar el teclado: un Alt suelto lo permite.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)


def work_area() -> tuple[int, int, int, int]:
    """Área de la pantalla principal sin la barra de tareas."""
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


class Cursor:
    def move(self, x: float, y: float) -> None:
        user32.SetCursorPos(round(x), round(y))

    def scroll(self, steps: int) -> None:
        """Pasos de la rueda: positivo hacia arriba."""
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, steps * WHEEL_DELTA, 0)

    def click(self, x: float, y: float) -> None:
        user32.SetCursorPos(round(x), round(y))
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def right_click(self, x: float, y: float) -> None:
        user32.SetCursorPos(round(x), round(y))
        user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    """Segundos desde el último uso del teclado o del mouse."""
    info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000
