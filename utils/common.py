#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
helper classes and functions
'''

import os, sys, string, hashlib
import re, textwrap
from unicodedata import normalize

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
    

class DummyStream:
    ''' dummyStream behaves like a stream but does nothing. '''
    def __init__(self): pass
    def write(self,data): pass
    def read(self,data): pass
    def flush(self): pass
    def close(self): pass
    
def getAppPath():
    '''Get the path to this script no matter how it's run.'''
    #Determine if the application is a py/pyw or a frozen exe.
    if hasattr(sys, 'frozen'):
        # If run from exe
        #dir_path = os.path.dirname(unicode(sys.executable, sys.getfilesystemencoding()))
        dir_path = os.path.dirname(sys.executable)
    elif '__file__' in locals():
        # If run from py
        dir_path = os.path.dirname(unicode(__file__, sys.getfilesystemencoding()))
    else:
        # If run from command line
        #dir_path = sys.path[0]
        dir_path = os.getcwdu()
    return dir_path

    
def getHomeDir():
    if sys.platform == 'win32':
        import winpaths
        homedir = winpaths.get_common_appdata() # = e.g # = e.g 'C:\ProgramData'
    else:
        homedir = os.path.expanduser("~")
    return homedir
    
def makeDir(d):
    if not os.path.exists(d):
        os.makedirs(d)
    return d

def ensureDir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)
    return f

def _xorData(data):
    """Xor Method, Take a data Xor all bytes and return"""
    data = [chr(ord(c) ^ 10) for c in data]
    return string.join(data, '')

def readFile(path, offset=0, size=-1, xor_data=False):
    """Read specified block from file, using the given size and offset"""
    fd = open(path, 'rb')
    fd.seek(offset)
    data = fd.read(size)
    fd.close()
    return _xorData(data) if xor_data else data
    
def writeFile(path, buf, offset=0, xor_data=False):
    """Write specified block on file at the given offset"""
    if xor_data:
        buf = _xorData(buf)
    fd = open(path, 'wb')
    fd.seek(offset)
    fd.write(buf)
    fd.close()
    return len(buf)


def md5_for_file(f, block_size=2**20):
    md5 = hashlib.md5()
    while True:
        data = f.read(block_size)
        if not data:
            break
        md5.update(data)
    return md5.hexdigest()


def smart_strip(s, max_length=0):
    s = s.strip()
    if max_length == 0 or len(s) <= max_length:
        return s
    
    if max_length > 3:
        return s[:-(len(s) - max_length + 3)].strip() + '...'
    else:
        return s[:-(len(s) - max_length)].strip()


def strip_by_word(the_string, width):
    if width <= 0:
        return the_string.strip()
    
    s = the_string
    if len(the_string) > width:
        s = textwrap.wrap(s, width)[0]
        if s[-1:] in [u'.', u',', u'?', u'!', u';', u'-', u':']:
            s = s[:-1].strip()
    
    if len(s) < len(the_string):
        s += '...'
    
    return s