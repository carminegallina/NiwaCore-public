@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0niwa-bridge-provision.ps1" %*
