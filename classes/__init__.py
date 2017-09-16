#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Misc classes for app and settings
'''

import os, uuid
import json

from settings import DATA_DIR, HASHING_ALGO
from utils.common import ensureDir, readFile, writeFile
from multiprocessing import cpu_count

CPU_COUNT = cpu_count()

class Pools():
    all_pools_file_path = os.path.join(DATA_DIR, 'conf', 'all_pools.json')
    def __init__(self, app_path):
        self.app_path = app_path
        ensureDir(self.all_pools_file_path)
        self.all_pools = []
    
    def _load_fixed_pools(self):
#         fixed_pools = []
#         file_path = os.path.join(self.app_path, 'fixed_pools.json')
#         if os.path.exists(file_path):
#             _pools = json.loads(readFile(file_path))
#             for p in _pools:
#                 fixed_pools.append(p)
        fixed_pools = [
            {
             "username": "", 
             "is_mining": False, 
             "is_hidden": False, 
             "password": "x", 
             "id": "86782736-2906-43ad-8f87-3c3f0e8a264b", 
             "priority_level": "normal", 
             "name": "[SUMO] Sumokoin Official Pool", 
             "url": "stratum+tcp://pool.sumokoin.com:3333", 
             "num_cpus": 0, 
             "algo": "Cryptonight", 
             "is_fixed": True
          }
        ]
        return fixed_pools
    
    def _set_default_values(self, p):
        p['id'] = p['id'] if 'id' in p else str(uuid.uuid4())
        p['algo'] = p['algo'] if 'algo' in p and p['algo'] in HASHING_ALGO else 'Cryptonight'
        p['name'] = p['name'] if 'name' in p and p['name'] else 'Unknown'
        p['url'] = p['url'] if 'url' in p else ''
        p['username'] = p['username'] if 'username' in p else ''
        p['password'] = p['password'] if 'password' in p else 'x'
        p['is_mining'] = p['is_mining'] if 'is_mining' in p else False
        p['is_hidden'] = p['is_hidden'] if 'is_hidden' in p else False
        p['is_fixed'] = p['is_fixed'] if 'is_fixed' in p else False
        p['num_cpus'] = p['num_cpus'] if 'num_cpus' in p else \
                                (CPU_COUNT - 1 if CPU_COUNT > 1 else CPU_COUNT)
        p['priority_level'] = p['priority_level'] if 'priority_level' in p else 'normal'    
    
    def find_pool(self, pool_id):
        for p in self.all_pools:
            if p['id'] == pool_id:
                return p
        return None
        
    def load_all(self):
        if os.path.exists(self.all_pools_file_path):
            _pools = []
            try:
                _pools = json.loads(readFile(self.all_pools_file_path))
            except:
                pass
            for p in _pools:
                self._set_default_values(p)
                self.all_pools.append(p)
        
        fixed_pools = self._load_fixed_pools()
        for p1 in fixed_pools:
            pool_found = False
            for p2 in self.all_pools:
                if p1['id'] == p2['id']:
                    # copy default/fixed mining properties
                    p2['algo'] = p1['algo']
                    p2['name'] = p1['name']
                    p2['url'] = p1['url']
                    p2['is_fixed'] = True
                    p2['is_mining'] = False if not p2['username'] else p2['is_mining']
                    pool_found = True
                    break
            if not pool_found:
                self._set_default_values(p1)
                p1['is_fixed'] = True
                self.all_pools.insert(0, p1)
        
    def save_all(self):
        _pools = []
        for p in self.all_pools:
            _p = {
                'id': p['id'],
                'algo': p['algo'],
                'name': p['name'],
                'url': p['url'],
                'username': p['username'],
                'password': p['password'],
                'is_mining': False if not p['username'] else p['is_mining'],
                'is_hidden': p['is_hidden'],
                'is_fixed': p['is_fixed'],
                'num_cpus': p['num_cpus'],
                'priority_level': p['priority_level'],
            }
            _pools.append(_p)
            
        writeFile(self.all_pools_file_path, 
                  json.dumps(_pools, indent=2))
    
    def add_pool(self, p):
        if 'id' not in p:
            p['id'] = str(uuid.uuid4())
        self.all_pools.append(p)
        self.save_all()
        
    def remove_pool(self, pool_id):
        p = self.find_pool(pool_id)
        if p is not None: 
            self.all_pools.remove(p)
            self.save_all()