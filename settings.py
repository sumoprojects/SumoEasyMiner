#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
App settings
'''

__doc__ = 'default application wide settings'

import sys
import os
import logging

from utils.common import getHomeDir, makeDir

USER_AGENT = APP_NAME = "Sumo Easy Miner"
VERSION = [0, 1, 'b1.3']

OPT_RANDOMIZE = False  # Randomize scan range start to reduce duplicates
OPT_SCANTIME = 60
OPT_REPLY_WITH_RPC2_EXPLICIT = True # support for explicit RPC 2.0 in reply
OPT_SEND_PING = True
OPT_PING_INTERVAL = 1 # Ping interval in second

HASHING_ALGO = ["Cryptonight", "Cryptonight-Light"]

_data_dir = str(makeDir(os.path.join(getHomeDir(), 'SumoMiner')))
DATA_DIR = _data_dir

log_file  = os.path.join(DATA_DIR, 'logs', 'sumominer.log') # default logging file
log_level = logging.DEBUG # logging level