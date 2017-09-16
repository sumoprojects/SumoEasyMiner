#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Sumo miner logger
'''

import sys, logging, os
import logging.handlers
import settings

from common import ensureDir

# Verbosity and log level
QUIET           = False
DEBUG           = False
DEBUG_PROTOCOL  = False
INFO            = True

LEVEL_PROTOCOL  = 'protocol'
LEVEL_INFO      = 'info'
LEVEL_DEBUG     = 'debug'
LEVEL_ERROR     = 'error'

def log(message, level, pool_id=None):
    '''Conditionally write a message to stdout based on command line options and level.'''
    
    global DEBUG
    global DEBUG_PROTOCOL
    global QUIET
    global INFO
    
    if QUIET and level != LEVEL_ERROR: return
    if not DEBUG_PROTOCOL and level == LEVEL_PROTOCOL: return
    if not DEBUG and level == LEVEL_DEBUG: return
    if not INFO and level == LEVEL_INFO: return
    
    if not pool_id:
        log_file = settings.log_file
    else:
        log_file = os.path.join(settings.DATA_DIR, 'logs', "%s.log" % pool_id)
        
    ensureDir(log_file)
    
    logger = get_logger(log_file, maxbytes=2*1024*1024) # maxbytes = 2MB
    
    if level == LEVEL_ERROR:
        logger.error(message)
    elif level == LEVEL_DEBUG or level == LEVEL_PROTOCOL:
        logger.debug(message)
    else:
        logger.info(message)

class ConsoleHandler(logging.StreamHandler):
    """Log to stderr for errors else stdout
    """
    def __init__(self):
        logging.StreamHandler.__init__(self)
        self.stream = None

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.stream = sys.stderr
        else:
            self.stream = sys.stdout
        logging.StreamHandler.emit(self, record)


def get_logger(output_file, log_level=settings.log_level, maxbytes=0):
    """Create a logger instance

    output_file:
        file where to save the log
    level:
        the minimum logging level to save
    maxbytes:
        the maxbytes allowed for the log file size. 0 means no limit.
    """
    logger = logging.getLogger(output_file)
    # avoid duplicate handlers
    if not logger.handlers:
        logger.setLevel(log_level)
        try:
            if not maxbytes:
                file_handler = logging.FileHandler(output_file)
            else:
                file_handler = logging.handlers.RotatingFileHandler(output_file, maxBytes=maxbytes)
        except IOError:
            pass # can not write file
        else:
            file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
            logger.addHandler(file_handler)

        console_handler = ConsoleHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(console_handler)
    return logger

#logger = get_logger(settings.log_file, maxbytes=2*1024*1024*1024)