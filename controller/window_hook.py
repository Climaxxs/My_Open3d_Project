"""
Windows窗口钩子 - 用于捕获嵌入的Open3D窗口的鼠标事件
"""

import ctypes
import ctypes.wintypes as wintypes
from ctypes import WINFUNCTYPE, windll
import win32gui
import win32con


# 定义Windows API类型
LRESULT = ctypes.c_long
HWND = wintypes.HWND
UINT = wintypes.UINT
WPARAM = wintypes.WPARAM
LPARAM = wintypes.LPARAM

# 定义窗口过程回调类型
WNDPROC = WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class WindowHook:
    """Windows窗口钩子，用于拦截Open3D窗口的鼠标事件"""

    def __init__(self, open3d_hwnd, callback):
        """
        初始化窗口钩子

        Args:
            open3d_hwnd: Open3D窗口的句柄
            callback: 鼠标点击回调函数，接收(x, y)参数
        """
        self.open3d_hwnd = open3d_hwnd
        self.callback = callback
        self.original_wndproc = None
        self.hooked = False

    def install_hook(self):
        """安装窗口钩子"""
        try:
            # 保存原始的窗口过程
            self.original_wndproc = win32gui.GetWindowLong(
                self.open3d_hwnd, win32con.GWL_WNDPROC
            )

            # 创建新的窗口过程
            new_wndproc = WNDPROC(self._window_procedure)

            # 设置新的窗口过程
            win32gui.SetWindowLong(
                self.open3d_hwnd,
                win32con.GWL_WNDPROC,
                new_wndproc
            )

            # 保存引用，防止垃圾回收
            self._new_wndproc = new_wndproc
            self.hooked = True

            print(f"窗口钩子安装成功，Open3D窗口句柄: {self.open3d_hwnd}")
            return True

        except Exception as e:
            print(f"安装窗口钩子失败: {e}")
            return False

    def uninstall_hook(self):
        """卸载窗口钩子"""
        if self.hooked and self.original_wndproc:
            try:
                win32gui.SetWindowLong(
                    self.open3d_hwnd,
                    win32con.GWL_WNDPROC,
                    self.original_wndproc
                )
                self.hooked = False
                print("窗口钩子已卸载")
            except Exception as e:
                print(f"卸载窗口钩子失败: {e}")

    def _window_procedure(self, hwnd, msg, wparam, lparam):
        """
        自定义窗口过程，拦截鼠标消息
        """
        try:
            # 处理鼠标左键按下消息
            if msg == win32con.WM_LBUTTONDOWN:
                # 提取鼠标坐标
                x = lparam & 0xFFFF  # 低16位是x坐标
                y = (lparam >> 16) & 0xFFFF  # 高16位是y坐标

                # 调用回调函数
                if self.callback:
                    self.callback(x, y)

                # 返回0表示消息已处理
                return 0

            # 其他鼠标消息也可以处理
            elif msg == win32con.WM_LBUTTONUP:
                # 可以处理鼠标释放消息
                pass
            elif msg == win32con.WM_MOUSEMOVE:
                # 可以处理鼠标移动消息
                pass

        except Exception as e:
            print(f"窗口过程处理错误: {e}")

        # 调用原始窗口过程处理其他消息
        if self.original_wndproc:
            return win32gui.CallWindowProc(self.original_wndproc, hwnd, msg, wparam, lparam)
        else:
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


def get_open3d_window_handle():
    """查找Open3D窗口句柄"""
    try:
        hwnd = win32gui.FindWindow(None, "Open3D")
        if hwnd:
            print(f"找到Open3D窗口句柄: {hwnd}")
            return hwnd
        else:
            print("未找到Open3D窗口")
            return None
    except Exception as e:
        print(f"查找Open3D窗口失败: {e}")
        return None


def test_mouse_hook():
    """测试鼠标钩子"""
    print("测试鼠标钩子...")

    def mouse_callback(x, y):
        print(f"鼠标点击捕获: ({x}, {y})")

    # 查找Open3D窗口
    hwnd = get_open3d_window_handle()
    if hwnd:
        hook = WindowHook(hwnd, mouse_callback)
        if hook.install_hook():
            print("钩子安装成功，请在Open3D窗口中点击测试")
            # 在实际应用中，需要保持钩子活跃
            # 这里只是测试，不保持运行
            return hook
    return None


if __name__ == "__main__":
    print("窗口钩子模块测试")
    test_mouse_hook()