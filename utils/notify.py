#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Notification helper classes
'''

import sys
from logger import log, LEVEL_DEBUG, LEVEL_INFO

has_libnotify = True
has_growl = True

try:
    import pynotify
except:
    has_libnotify = False

if not has_libnotify:
    try:
        import Growl
        from Growl import GROWL_NOTIFICATION_ICON
    except:
        has_growl = False

class Notify(object):
    notifier = None
    appname = ""

    def __init__(self, appname):
        self.appname = appname
        # Our preferences, in order:
        # libnotify
        # growl
        # systemtray bubble
        try:
            if has_libnotify:
                self.notifier = LibNotify(self.appname)
            elif has_growl:
                self.notifier = GrowlNotify(self.appname)
            else:
                log("No notifier found, system tray bubble will be used.", LEVEL_DEBUG)
        except:
            self.notifier = None
            log("Failed to initialize notifier, system tray bubble will be used.", LEVEL_DEBUG)

    def notify(self, title, message, icon=None):
        if not self.notifier is None:
            self.notifier.notify(title, message, icon)

class LibNotify(object):
    def __init__(self, appname):
        self.appname = appname
        if not pynotify.init(appname):
            log("PyNotify failed to initialize with appname: %s" % appname, LEVEL_DEBUG)

    def notify(self, title, message, icon):
        title = "%s - %s" % (self.appname, title)
        try:
            notification = pynotify.Notification(title, message, icon)
        except TypeError:
            notification = pynotify.Notification(title, message)
        
        notification.show()

class GrowlNotify(object):
    def __init__(self, appname):
        notification_names = ["New Messages"]
        defaultNotifications = ["New Messages"]
        self.notification = Growl.GrowlNotifier(appname, notification_names, defaultNotifications)
        self.notification.register()
        self.appname = appname
        
    def notify(self, title, message, icon):
        title = "%s - %s" % ( self.appname, title)
        try:
            self.notification.notify("New Messages", title, message, icon)
        except TypeError:
            self.notification.notify("New Messages", title, message, GROWL_NOTIFICATION_ICON)

