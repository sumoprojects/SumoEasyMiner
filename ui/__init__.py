#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Main Window UI definations and methods
'''



import os, sys, json
from time import time, sleep

from PySide.QtGui import QApplication, QMainWindow, QIcon, QSystemTrayIcon, \
    QMenu, QAction, QMessageBox, QDialog, QGridLayout, QInputDialog, QLineEdit, QImageReader
    
import PySide.QtCore as qt_core
import PySide.QtWebKit as web_core
from PySide.QtCore import QTimer

# qt_core.QCoreApplication.addLibraryPath(os.path.join(os.path.dirname(qt_core.__file__), "plugins"))
# QImageReader.supportedImageFormats()

from settings import APP_NAME, USER_AGENT, VERSION
from utils.logger import log, LEVEL_DEBUG, LEVEL_ERROR, LEVEL_INFO
from miner.miner import MinerWork, MinerRPC, human_readable_hashrate

from utils.notify import Notify
MSG_TYPE_INFO = 1
MSG_TYPE_WARNING = 2
MSG_TYPE_CRITICAL = 3

thr_list = []
manager = None
tray_icon_tooltip = "%s v%d.%d-%s" % (APP_NAME, VERSION[0], VERSION[1], VERSION[2])

WINDOW_WIDTH = 980
HEAD_ROW_HEIGHT = 51 + 56
POOL_ROW_HEIGHT = 77
BOTTOM_MARGIN = 5

log_text_tmpl = """
<index>
    <head>
        <style type="text/css">
            body{
                font-family: "Lucida Console", "Courier New", Monaco, Courier, monospace;
            }
        </style>
    </head>
    <body>
        <div style="width=100%%;height:100%%">
            <code><pre>
%s
            </pre></code>
        </div>
    <body>
</index>
"""

from html import index, addpool

class LogViewer(QMainWindow):
    def __init__(self, parent, log_file):
        QMainWindow.__init__(self, parent)
        self.view = web_core.QWebView(self)
        self.view.setContextMenuPolicy(qt_core.Qt.NoContextMenu)
        self.view.setCursor(qt_core.Qt.ArrowCursor)
        self.view.setZoomFactor(1)
        self.setCentralWidget(self.view)
        
        self.log_file = log_file
        self.setWindowTitle("%s - Log view [%s]" % (APP_NAME, os.path.basename(log_file)))
    
    def load_log(self):
        if not os.path.exists(self.log_file):
            _text = "[No logs]"
        else:
            with open(self.log_file) as f:
                f.seek (0, 2)           # Seek @ EOF
                fsize = f.tell()        # Get Size
                f.seek (max (fsize-4*1024*1024, 0), 0) # read last 4MB
                _text = f.read()
        self.view.setHtml(log_text_tmpl % (_text, ))
        self.resize(800, 600)
        self.show()
        
        

class BaseWebUI(QMainWindow):
    def __init__(self, html, app, hub, debug=False):
        QMainWindow.__init__(self)
        self.app = app
        self.hub = hub
        self.debug = debug
        self.html = html
        self.url = "file:///" \
            + os.path.join(self.app.property("ResPath"), "www/", html ).replace('\\', '/')
        
        
        self.is_first_load = True
        self.view = web_core.QWebView(self)
        
        if not self.debug:
            self.view.setContextMenuPolicy(qt_core.Qt.NoContextMenu)
        
        self.view.setCursor(qt_core.Qt.ArrowCursor)
        self.view.setZoomFactor(1)
        
        self.setWindowTitle(APP_NAME)
        self.icon = self._getQIcon('sumominer_64x64.png')
        self.setWindowIcon(self.icon)
        
        self.setCentralWidget(self.view)
        self.center()
        
        
    def run(self):
        self.view.loadFinished.connect(self._load_finished)
        self.view.load(qt_core.QUrl(self.url))
#         self.view.setHtml(self.html, qt_core.QUrl(self.url))
        
        
    def center(self):
        frameGm = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        centerPoint = QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())
        
    def _load_finished(self):
        #This is the actual context/frame a webpage is running in.  
        # Other frames could include iframes or such.
        main_page = self.view.page()
        main_frame = main_page.mainFrame()
        # ATTENTION here's the magic that sets a bridge between Python to HTML
        main_frame.addToJavaScriptWindowObject("app_hub", self.hub)
        
        if self.is_first_load: ## Avoid re-settings on page reload (if happened)
            change_setting = main_page.settings().setAttribute
            settings = web_core.QWebSettings
            change_setting(settings.DeveloperExtrasEnabled, self.debug)
            change_setting(settings.LocalStorageEnabled, True)
            change_setting(settings.OfflineStorageDatabaseEnabled, True)
            change_setting(settings.OfflineWebApplicationCacheEnabled, True)
            change_setting(settings.JavascriptCanOpenWindows, True)
            change_setting(settings.PluginsEnabled, False)
            
            # Show web inspector if debug on
            if self.debug:
                self.inspector = web_core.QWebInspector()
                self.inspector.setPage(self.view.page())
                self.inspector.show()
            
            self.is_first_load = False
                    
        #Tell the HTML side, we are open for business
        main_frame.evaluateJavaScript("app_ready()")
        
    def _getQIcon(self, icon_file):
        return QIcon(os.path.join(self.app.property("ResPath"), 'icons', icon_file))

        
class AddPoolDialog(QDialog):
    def __init__(self, app, hub, html, debug=False):
        QDialog.__init__(self)
        self.app = app
        self.hub = hub
        self.html = addpool.html
        self.debug = debug
        self.url = "file:///" \
            + os.path.join(self.app.property("ResPath"), "www/", html).replace('\\', '/')
        
        self.is_first_load = True
        self.view = web_core.QWebView(self)
        
        if not self.debug:
            self.view.setContextMenuPolicy(qt_core.Qt.NoContextMenu)
        
        self.view.setCursor(qt_core.Qt.ArrowCursor)
        self.view.setZoomFactor(1)
        
        self.setWindowTitle("Add/Edit Pool :: %s" % APP_NAME)
        self.icon = self._getQIcon('sumominer_64x64.png')
        self.setWindowIcon(self.icon)
        
        layout = QGridLayout()
        layout.addWidget(self.view)
        self.setLayout(layout)
        
        self.setFixedSize(qt_core.QSize(660,480))
        self.center()
        
        self.view.loadFinished.connect(self._load_finished)
#         self.view.load(qt_core.QUrl(self.url))
        self.view.setHtml(self.html, qt_core.QUrl(self.url))
    
        
    def _load_finished(self):
        #This is the actual context/frame a webpage is running in.  
        # Other frames could include iframes or such.
        main_page = self.view.page()
        main_frame = main_page.mainFrame()
        # ATTENTION here's the magic that sets a bridge between Python to HTML
        main_frame.addToJavaScriptWindowObject("app_hub", self.hub)
        
        if self.is_first_load: ## Avoid re-settings on page reload (if happened)
            change_setting = main_page.settings().setAttribute
            settings = web_core.QWebSettings
            change_setting(settings.DeveloperExtrasEnabled, self.debug)
            change_setting(settings.LocalStorageEnabled, True)
            change_setting(settings.OfflineStorageDatabaseEnabled, True)
            change_setting(settings.OfflineWebApplicationCacheEnabled, True)
            change_setting(settings.JavascriptCanOpenWindows, True)
            change_setting(settings.PluginsEnabled, False)
            
            # Show web inspector if debug on
            if self.debug:
                self.inspector = web_core.QWebInspector()
                self.inspector.setPage(self.view.page())
                self.inspector.show()
            
            self.is_first_load = False
                    
        #Tell the HTML side, we are open for business
        main_frame.evaluateJavaScript("app_ready()")
        
    
    def _getQIcon(self, icon_file):
        return QIcon(os.path.join(self.app.property("ResPath"), 'icons', icon_file))
    
    def center(self):
        frameGm = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        centerPoint = QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())
        
             
class WebUI(BaseWebUI):
    def __init__(self, app, hub, debug=False):
        BaseWebUI.__init__(self, "index.html", app, hub, debug)
        self.html = index.html
        
        self.agent = '%s v%s' % (USER_AGENT, '.'.join(str(v) for v in VERSION))
        log("Starting [%s]..." % self.agent, LEVEL_INFO)
        
        # Setup the system tray icon
        if sys.platform == 'darwin':
            tray_icon = 'sumominer_16x16_mac.png'
        elif sys.platform == "win32":
            tray_icon = 'sumominer_16x16.png'
        else:
            tray_icon = 'sumominer_32x32_ubuntu.png'
        
        self.trayIcon = QSystemTrayIcon(self._getQIcon(tray_icon))
        self.trayIcon.setToolTip(tray_icon_tooltip)
        
        # Setup the tray icon context menu
        self.trayMenu = QMenu()
        
        self.showAppAction = QAction('&Show %s' % APP_NAME, self)
        f = self.showAppAction.font()
        f.setBold(True)
        self.showAppAction.setFont(f)
        self.trayMenu.addAction(self.showAppAction)
        
        
        self.aboutAction = QAction('&About...', self)
        self.trayMenu.addAction(self.aboutAction)
        
        self.trayMenu.addSeparator()
        self.exitAction = QAction('&Exit', self)
        self.trayMenu.addAction(self.exitAction)
        # Add menu to tray icon
        self.trayIcon.setContextMenu(self.trayMenu)
              
        # connect signals
        self.trayIcon.activated.connect(self._handleTrayIconActivate)
        self.exitAction.triggered.connect(self.handleExitAction)
        self.aboutAction.triggered.connect(self.handleAboutAction)
        self.showAppAction.triggered.connect(self._handleShowAppAction)
        self.app.aboutToQuit.connect(self._handleAboutToQuit)
        
        # Setup notification support
        self.system_tray_running_notified = False
        self.notifier = Notify(APP_NAME)
        self.trayIcon.show()

    def run(self):
        # load user's pool list
        # load_pools(self.app.property("AppPath"))
        
        self.view.loadFinished.connect(self._load_finished)
#         self.view.load(qt_core.QUrl(self.url))
        self.view.setHtml(index.html, qt_core.QUrl(self.url))
        
        self.resetWindowSize()
        self.center()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._updateHashRate)
        self.timer.start(2000)
        
        self.wait(1)
        
        self.timer2 = QTimer(self)
        self.timer2.timeout.connect(self._reportError)
        self.timer2.start(2000)
        
        self.trayIcon.show()
        self.show()        
        
    
    def closeEvent(self, event):
        """ Override QT close event
        """
        event.ignore()
        self.hide()
        if not self.system_tray_running_notified:
            self.notify("%s is still running at system tray." % APP_NAME, 
                                                                        "Running Status")
            self.system_tray_running_notified = True
            
    
    def resetWindowSize(self):
        ws = qt_core.QSize( WINDOW_WIDTH, 
                HEAD_ROW_HEIGHT + POOL_ROW_HEIGHT*(len([p for p in self.hub.pools.all_pools if not p['is_hidden']])) 
                + BOTTOM_MARGIN)
        self.setFixedSize(ws)
    
        
    def _getQIcon(self, icon_file):
        _icon_path = os.path.join(self.app.property("ResPath"), 'icons', icon_file)
        return QIcon(_icon_path)
        
    def _handleTrayIconActivate(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()
        
    def handleExitAction(self, show_confirmation=False):
        reply = QMessageBox.No
        if show_confirmation:
            reply=QMessageBox.question(self,'Exit %s?' % APP_NAME,
                    "Are you sure to exit %s?" % APP_NAME, QMessageBox.Yes,QMessageBox.No)
        if not show_confirmation or reply==QMessageBox.Yes:
            self.trayIcon.hide()
            QTimer.singleShot(250, self.app.quit)
    
    def _handleShowAppAction(self):
        self.showNormal()
        self.activateWindow()
        
    def handleAboutAction(self):
        self.showNormal()
        self.about()
    
    def _reportError(self):
        for pool_info in self.hub.pools.all_pools:
            if 'error' in pool_info:
                if pool_info['error'] is not None:
                    self.hub.report_error(pool_info['id'], pool_info['error'])
                else:
                    self.hub.report_error(pool_info['id'], 'ERROR_END')
                    pool_info.pop("error", None)
    
    def _updateHashRate(self):
        _sum_hashrates = 0.
        for pool_info in self.hub.pools.all_pools:
            _json = {'pool_id': pool_info['id']}
            hash_rates = pool_info['hash_report'] if 'hash_report' in pool_info else {}
            if len(hash_rates) > 0:
                _hash_rates = dict(hash_rates)
                _total_hash_rate = reduce(lambda x, y: x+y, [_hash_rates[k] for k in _hash_rates])
                _json['hash_rate'] = _total_hash_rate
                _sum_hashrates += _total_hash_rate
                pool_info['total_hashrate'] =  _total_hash_rate
            else:
                _json['hash_rate'] = 0.0
            # reset hashrate
            if 'hash_report' in pool_info and 'thr_list' in pool_info:
                if pool_info['thr_list'] is not None:
                    for thr in pool_info['thr_list']:
                        pool_info['hash_report'].update({'%d' % thr._thr_id: 0.0})
             
            
            work_report = pool_info['work_report'] if 'work_report' in pool_info else {}
            if 'work_submited' in work_report and work_report['work_submited'] > 0:
                _json['shares_good'] = work_report['work_accepted'] if 'work_accepted' in work_report else 0
                _json['shares_total'] = work_report['work_submited']
                _json['shares_pct'] = "%.2f%%" % (_json['shares_good']*100.0/_json['shares_total'], )
            else:
                _json['shares_good'] = 0
                _json['shares_total'] = 0
                _json['shares_pct'] = "0.00%"
            
            if 'difficulty' in work_report:
                _json['difficulty'] = "%.f" % work_report['difficulty']
            else:
                _json['difficulty'] = "0"
            
            self.hub.update_hashrate(json.dumps(_json))
            
        self.trayIcon.setToolTip("%s\nHashrate: %s" % (tray_icon_tooltip, 
                                               human_readable_hashrate(_sum_hashrates)))

    def _load_finished(self):
        #This is the actual context/frame a webpage is running in.  
        # Other frames could include iframes or such.
        main_page = self.view.page()
        main_frame = main_page.mainFrame()
        # ATTENTION here's the magic that sets a bridge between Python to HTML
        main_frame.addToJavaScriptWindowObject("app_hub", self.hub)
        
        if self.is_first_load: ## Avoid re-settings on page reload (if happened)
            change_setting = main_page.settings().setAttribute
            settings = web_core.QWebSettings
            change_setting(settings.DeveloperExtrasEnabled, self.debug)
            change_setting(settings.LocalStorageEnabled, True)
            change_setting(settings.OfflineStorageDatabaseEnabled, True)
            change_setting(settings.OfflineWebApplicationCacheEnabled, True)
            change_setting(settings.JavascriptCanOpenWindows, True)
            change_setting(settings.PluginsEnabled, False)
            
            # Show web inspector if debug on
            if self.debug:
                self.inspector = web_core.QWebInspector()
                self.inspector.setPage(self.view.page())
                self.inspector.show()
        #Tell the HTML side, we are open for business
        main_frame.evaluateJavaScript("app_ready()")
        # send pool list to HTML for rendering
        self.hub.create_pool_list()
        # Resize main window to fit web content (avoid scroll bars showed)
        main_page.setViewportSize(main_frame.contentsSize())
        #self.setFixedSize(860, 360)
        
        # resume mining jobs
        for p in self.hub.pools.all_pools:
            if 'is_mining' in p and p['is_mining']:
                self.hub.start_stop_mining(p['id'])
        
        self.is_first_load = False

    
    def _handleAboutToQuit(self):
        log("%s is about to quit..." % APP_NAME, LEVEL_INFO)
        for pool_info in self.hub.pools.all_pools:
            if not 'thr_list' in pool_info or pool_info['thr_list'] is None:
                pool_info['is_mining'] = False
            else:
                # shut down threads
                for thr in pool_info['thr_list']:
                    thr.shutdown()
                    thr.join()
                # shut down RPC client
                pool_info['rpc'].shutdown()
                pool_info['rpc'].join()
                pool_info['is_mining'] = True # save mining status to resume on next start
        
        if manager: manager.shutdown()
        # save pool list
        self.hub.pools.save_all()
        
        
    def notify(self, message, title="", icon=None, msg_type=None):
        if self.notifier.notifier is not None:
            self.notifier.notify(title, message, icon)
        else:
            self.showMessage(message, title, msg_type)

    def showMessage(self, message, title="", msg_type=None, timeout=2000):
        """Displays 'message' through the tray icon's showMessage function,
        with title 'title'. 'type' is one of the enumerations of
        'common.MessageTypes'.
        """
        if msg_type is None or msg_type == MSG_TYPE_INFO:
            icon = QSystemTrayIcon.Information

        elif msg_type == MSG_TYPE_WARNING:
            icon = QSystemTrayIcon.Warning

        elif msg_type == MSG_TYPE_CRITICAL:
            icon = QSystemTrayIcon.Critical
        
        title = "%s - %s" % (APP_NAME, title) if title else APP_NAME
        self.trayIcon.showMessage(title, message, icon, timeout)
        
    
    def about(self):
        QMessageBox.about(self, "About", \
            u"%s <br><br>Copyright© 2017 - Sumokoin Projects<br><br>\
            <b>www.sumokoin.org</b>" % self.agent)    
    
    
    def wait(self, timeout=1):
        for _ in range(timeout*10):
            sleep(0.1)
            self.app.processEvents()
