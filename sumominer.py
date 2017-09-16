#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
App entry point
'''

import multiprocessing

from main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()