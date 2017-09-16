#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Main app def
'''

import sys, os, hashlib

from app.QSingleApplication import QSingleApplication
import PySide.QtCore as qt_core
from PySide.QtGui import QMessageBox
from utils.common import DummyStream, getAppPath, readFile
from settings import APP_NAME

from app.hub import Hub
from ui import WebUI

file_hashes = [
        ('www/scripts/jquery-1.9.1.min.js', 'c12f6098e641aaca96c60215800f18f5671039aecf812217fab3c0d152f6adb4'),
        ('www/scripts/bootstrap.min.js', '2979f9a6e32fc42c3e7406339ee9fe76b31d1b52059776a02b4a7fa6a4fd280a'),
        ('www/scripts/mustache.min.js', '3258bb61f5b69f33076dd0c91e13ddd2c7fe771882adff9345e90d4ab7c32426'),
        ('www/scripts/jquery.sparkline.js', '6bb90109f3b9a5936a3e3984ef424391dfee5c70a715d2c5f27934d43a7c81b7'),
        ('www/scripts/utils.js', 'e4362beaee047dcf9eb94129413509243f42dda5fcd3242be7d66b70308f932a'),
        
        ('www/css/bootstrap.min.css', '2e4ceda16bdb9f59b01ee01552e8a353ee7cc4e4ebac7d51413106094384ef37'),
        ('www/css/font-awesome.min.css', 'b8b02026a298258ce5069d7b6723c2034058d99220b6612b54bc0c5bf774dcfb'),
        
        ('www/css/fonts/fontawesome-webfont.ttf', '7b5a4320fba0d4c8f79327645b4b9cc875a2ec617a557e849b813918eb733499'),
        ('www/css/fonts/glyphicons-halflings-regular.ttf', 'e395044093757d82afcb138957d06a1ea9361bdcf0b442d06a18a8051af57456'),
        ('www/css/fonts/RoboReg.ttf', 'dc66a0e6527b9e41f390f157a30f96caed33c68d5db0efc6864b4f06d3a41a50'),
    ]

def _check_file_integrity(app):
    ''' Check file integrity to make sure all resources loaded
        to webview won't be modified by an unknown party '''
    for file_name, file_hash in file_hashes:
        file_path = os.path.normpath(os.path.join(app.property("ResPath"), file_name))
        if not os.path.exists(file_path):
            return False
        data = readFile(file_path)
#         print( file_path, hashlib.sha256(data).hexdigest() )
        if hashlib.sha256(data).hexdigest() != file_hash:
            return False
        
    return True


def main():
    if getattr(sys, "frozen", False) and sys.platform in ['win32','cygwin','win64']:
        # and now redirect all default streams to DummyStream:
        sys.stdout = DummyStream()
        sys.stderr = DummyStream()
        sys.stdin = DummyStream()
        sys.__stdout__ = DummyStream()
        sys.__stderr__ = DummyStream()
        sys.__stdin__ = DummyStream()
              
    # Get application path
    app_path = getAppPath()
    if sys.platform == 'darwin' and hasattr(sys, 'frozen'):
        resources_path = os.path.normpath(os.path.abspath(os.path.join(app_path, "..", "Resources")))
    else:
        resources_path = os.path.normpath(os.path.abspath(os.path.join(app_path, "Resources")))
        
    # Application setup
    app = QSingleApplication(sys.argv)
    app.setOrganizationName('Sumokoin')
    app.setOrganizationDomain('www.sumokoin.org')
    app.setApplicationName(APP_NAME)
    app.setProperty("AppPath", app_path)
    app.setProperty("ResPath", resources_path)
    if sys.platform != 'win32':
        app.setAttribute(qt_core.Qt.AA_DontShowIconsInMenus)
    
    app.setStyleSheet('QMainWindow{background-color: white;}')
    app.setStyleSheet('QDialog{background-color: white;}')
    
    if not _check_file_integrity(app):
        QMessageBox.critical(None, "Application Fatal Error", """<b>File integrity check failed!</b>
                <br><br>This could be a result of unknown (maybe, malicious) action<br> to code files.""")
        app.quit()
        return
    
    hub = Hub(app=app)
    ui = WebUI(app=app, hub=hub, debug=False)
    hub.setUI(ui)
    app.singleStart(ui)
        
    sys.exit(app.exec_())
