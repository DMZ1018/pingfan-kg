"""在 DSH Windows 沙箱下运行 pip。

沙箱把 mode=0o700 的目录 ACL 收紧到当前受限令牌之外，
而 tempfile.mkdtemp() 固定用 0o700，导致 pip 下载/解包临时目录不可写。
这里把 os.mkdir 的 mode 统一抬到 0o777 再调用 pip。
"""
import os
import runpy
import sys

_orig_mkdir = os.mkdir


def _mkdir(path, mode=0o777, *args, **kwargs):
    return _orig_mkdir(path, 0o777, *args, **kwargs)


os.mkdir = _mkdir
sys.argv = ["pip"] + sys.argv[1:]
runpy.run_module("pip", run_name="__main__")
