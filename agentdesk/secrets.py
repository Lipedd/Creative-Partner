"""Persist local-only secrets with Windows' per-user Data Protection API."""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


if os.name == "nt":
    class DataBlob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _input_blob(raw: bytes):
    buffer = ctypes.create_string_buffer(raw)
    blob = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buffer


def protect_secret(value: str) -> str:
    """Encrypt for the current Windows user and return a database-safe value."""
    if os.name != "nt":
        raise RuntimeError("当前系统暂不支持安全保存密钥。")
    source, source_buffer = _input_blob(value.encode("utf-8"))
    output = DataBlob()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(source), "创想伙伴模型密钥", None, None, None, 0x1, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(output.data, output.size)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)
        del source_buffer


def unprotect_secret(value: str) -> str:
    """Decrypt a value for the same Windows user that saved it."""
    if os.name != "nt":
        raise RuntimeError("当前系统暂不支持读取已保存的密钥。")
    source, source_buffer = _input_blob(base64.b64decode(value, validate=True))
    output = DataBlob()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)
        del source_buffer
