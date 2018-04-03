#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)

'''
This is a central communication hub between Python codes and web UI
'''

import os, sys, uuid, json
import webbrowser, urlparse
from time import sleep
from multiprocessing import Queue, Manager, cpu_count

from PySide.QtCore import QObject, Slot, Signal
from PySide.QtGui import QMessageBox, QInputDialog, QLineEdit

from classes import Pools
from ui import AddPoolDialog
from miner.miner import MinerWork, MinerRPC
from settings import APP_NAME, DATA_DIR
from ui import LogViewer
from utils.logger import log, LEVEL_ERROR
from utils.common import smart_strip

CPU_COUNT = cpu_count()

def get_num_cpus():
    return CPU_COUNT

import psutil
if sys.platform == 'win32':
    IDLE_CPU_PRIORITY_LEVEL = psutil.IDLE_PRIORITY_CLASS
    LOW_CPU_PRIORITY_LEVEL = psutil.BELOW_NORMAL_PRIORITY_CLASS
    NORMAL_CPU_PRIORITY_LEVEL = psutil.NORMAL_PRIORITY_CLASS
    HIGH_CPU_PRIORITY_LEVEL = psutil.HIGH_PRIORITY_CLASS
    VERY_HIGH_CPU_PRIORITY_LEVEL = psutil.REALTIME_PRIORITY_CLASS
else:
    IDLE_CPU_PRIORITY_LEVEL = 20
    LOW_CPU_PRIORITY_LEVEL = 10
    NORMAL_CPU_PRIORITY_LEVEL = 0
    HIGH_CPU_PRIORITY_LEVEL = -10
    VERY_HIGH_CPU_PRIORITY_LEVEL = -20
    
def get_cpu_priority_level(priority_level):
    cpu_priority_level = NORMAL_CPU_PRIORITY_LEVEL
    if priority_level == "idle":
        cpu_priority_level = IDLE_CPU_PRIORITY_LEVEL
    elif priority_level == "low":
        cpu_priority_level = LOW_CPU_PRIORITY_LEVEL
    elif priority_level == "high":
        cpu_priority_level = HIGH_CPU_PRIORITY_LEVEL
    elif priority_level == "very high":
        cpu_priority_level = VERY_HIGH_CPU_PRIORITY_LEVEL
    return cpu_priority_level

POOL_SIZE_LIMIT = 10 # number of pools can be added to avoid over screen
manager = None

class Hub(QObject):
    def __init__(self, app):
        super(Hub, self).__init__()
        self.app = app
        self.pools = Pools(self.app.property("AppPath"))
        self.pools.load_all()
        
        self.add_pool_dialog = AddPoolDialog(self.app, self, "addpool.html", False)
 
    def setUI(self, ui):
        self.ui = ui
 
    @Slot(str)
    def open_web(self, url):
        #print url
        webbrowser.open(url)
        self.on_web_open_event.emit("web opened")
        
    @Slot(str, int)
    def start_stop_mining(self, pool_id, num_procs=0):
        pool_info = self.pools.find_pool(pool_id)
        if not pool_info:
            self.on_back_end_error_event.emit("Error: pool [%s] not found" % pool_id) 
            return
        
        if pool_info['username'] == "":
            username, result = self._custom_input_dialog(self.ui, \
                        "Enter Wallet Address", "Please enter wallet address to mine:")
            if result:
                ##TODO: address validation
                pool_info['username'] = username
                self.pools.save_all()
            else:
                QMessageBox.warning(self.ui, "Wallet Address Required", \
                    "Wallet address is required to start mining!<br><br>\
                    Hint: You can get a new address from:<br><br><b>https://wallet.sumokoin.com</b>")
                self.on_stop_mining_event.emit(pool_info["id"]) 
                return
        
        """ Stop if mining """
        if self._stop_mining(pool_info):
            self.on_stop_mining_event.emit(pool_info["id"]) 
            return
        
        
        """ Else start mining """
        if num_procs == 0:
            num_procs = get_num_cpus()
        
        global manager
        if not manager: manager = Manager()
        
        if not 'work_submit_queue' in pool_info:
            work_submit_queue = Queue()
            pool_info['work_submit_queue'] = work_submit_queue
        else:
            work_submit_queue = pool_info['work_submit_queue']
        
        if not 'g_work' in pool_info:
            g_work = manager.dict()
            pool_info['g_work'] = g_work
        else:
            g_work = pool_info['g_work']
        
        if not 'hash_report' in pool_info:
            hash_report = manager.dict()
            pool_info['hash_report'] = hash_report
        else:
            hash_report = pool_info['hash_report']
        
        if not 'work_report' in pool_info:
            work_report = manager.dict()
            pool_info['work_report'] = work_report
        else:
            work_report = pool_info['work_report']
            
        cpu_priority_level = get_cpu_priority_level(pool_info['priority_level'])
        
        pool_info['thr_list'] = []
        for thr_id in range(num_procs):
            p = MinerWork(thr_id, work_submit_queue, g_work, hash_report, get_cpu_priority_level('normal'))
            p.start()
            p.set_cpu_priority(cpu_priority_level)
            pool_info['thr_list'].append(p)
        
        # set main UI process priority to normal level to avoid UI frozen
        psutil.Process().nice(NORMAL_CPU_PRIORITY_LEVEL)
                
        pool_info['num_cpus'] = num_procs
        pool_info['is_mining'] = True
        
        rpc = MinerRPC(pool_info, work_submit_queue, g_work, work_report)
        rpc.set_thread_list(pool_info['thr_list'])
        rpc.daemon = True
        rpc.start()
        pool_info['rpc'] = rpc
        
        self.on_start_mining_event.emit(pool_info["id"])
        
    
    def _stop_mining(self, pool_info):
        if 'thr_list' in pool_info and pool_info['thr_list'] is not None:
            # shut down threads
            for thr in pool_info['thr_list']:
                thr.shutdown()
                thr.join()
                self.app_process_events(0.1)
            pool_info['thr_list'] = None
            
            # shut down RPC client
            pool_info['rpc'].shutdown()
            pool_info['rpc'].join()
            work_submit_queue = pool_info['work_submit_queue']
            # clear the submit queue
            while not work_submit_queue.empty():
                _ = work_submit_queue.get()
            
            if 'error' in pool_info: 
                pool_info['error'] = None
            
            pool_info['is_mining'] = False
            return True
        return False
    
    def app_process_events(self, seconds=1):
        for _ in range(int(seconds*10)):
            self.app.processEvents()
            sleep(.1)
    
    @Slot(str, int)
    def change_cpus(self, pool_id, num_cpus):
#         pool_info = get_pool(pool_id)
        pool_info = self.pools.find_pool(pool_id)
        if not pool_info:
            self.on_back_end_error_event.emit("Error: pool [%s] not found" % pool_id) 
            return
        
        pool_info['num_cpus'] = num_cpus
        
        if not 'thr_list' in pool_info or pool_info['thr_list'] is None:
            # it means mining stopped or never started 
            return
        
        thr_list = pool_info['thr_list']
        if num_cpus >  len(thr_list):
            # add more cores
            cpus = num_cpus - len(thr_list)
            work_submit_queue = pool_info['work_submit_queue']
            g_work = pool_info['g_work']
            hash_report = pool_info['hash_report']
            for _ in range(cpus):
                thr_id = len(thr_list)
                p = MinerWork(thr_id, work_submit_queue, g_work, hash_report, 
                              get_cpu_priority_level('normal'))
                thr_list.append(p)
                g_work['num_thrs'] = len(thr_list)
                p.start()
                p.set_cpu_priority(get_cpu_priority_level(pool_info['priority_level']))
        elif num_cpus <  len(thr_list):
            # remove cores
            for _ in range(len(thr_list) - num_cpus):
                thr = thr_list.pop(len(thr_list) - 1)
                thr.shutdown()
                thr.join()
                
    @Slot(str, str)
    def change_priority(self, pool_id, priority_level):
        #print "Change process priority to", priority_level
        cpu_priority_level = get_cpu_priority_level(priority_level)
        
        pool_info = self.pools.find_pool(pool_id)
        if not pool_info:
            self.on_back_end_error_event.emit("Error: pool [%s] not found" % pool_id) 
            return
        
        if 'thr_list' in pool_info and pool_info['thr_list'] is not None:
            for thr in pool_info['thr_list']:
                thr.set_cpu_priority(cpu_priority_level)
            
        pool_info['priority_level'] = priority_level
        sleep(1)
        psutil.Process().nice(NORMAL_CPU_PRIORITY_LEVEL)
        
        #print "Main process priority", psutil.Process().nice()            
        
    @Slot(str)
    def view_log(self, pool_id):
        log_file = os.path.join(DATA_DIR, 'logs', "%s.log" % pool_id)
        log_dialog = LogViewer(parent=self.ui, log_file=log_file)
        log_dialog.load_log()
    
    @Slot(str)
    def hide_pool_row(self, pool_id):
        pool_info = self.pools.find_pool(pool_id)
        if pool_info['is_mining']:
            QMessageBox.warning(self.ui,'Pool Hide Not Allowed', "Pool in mining is not allowed to hide!")
            return
                
        pool_info['is_hidden'] = True
        self.ui.resetWindowSize()
        self.on_hide_pool_success_event.emit(pool_id)
        
    @Slot(str)
    def show_pools(self, pool_ids):
        if not pool_ids: return
        pool_ids = pool_ids.split(',')
        for pool_id in pool_ids:
            pool_info = self.pools.find_pool(pool_id)
            pool_info['is_hidden'] = False
        self.ui.resetWindowSize()
        
    @Slot(str)
    def remove_pool(self, pool_id):
        pool_info = self.pools.find_pool(pool_id)
        # possible to remove user's created pool only
        if not pool_info or pool_info['is_fixed'] == True:
            return
        
        reply = QMessageBox.question(self.ui,'Remove Pool Confirmation',
                "Are you sure to remove this pool?",QMessageBox.Yes,QMessageBox.No)
        
        if reply==QMessageBox.Yes:
            # stop mining
            self._stop_mining( pool_info )
            # remove pool from list
            self.pools.remove_pool(pool_id)
            # tell UI to remove the pool row
            self.on_remove_pool_confirm_event.emit(pool_id)
            # resize window to fit
            self.ui.resetWindowSize()
            # save pool list
            self.pools.save_all()
            
    @Slot()
    def show_addpool_dialog(self):
        if len(self.pools.all_pools) >= POOL_SIZE_LIMIT:
            QMessageBox.warning(self.ui, 'Add/Edit Pool Error', "<b>You have reached number of pools limit!\
            <br> Adding new pool is not allowed.</b><br><br><i>Hint: Remove unused pools to add new ones</i>")
            return
        self.on_reset_addpool_form_event.emit()
#         self.add_pool_dialog.center()
        self.add_pool_dialog.exec_()
#         self.add_pool_dialog.show()

    @Slot()
    def close_addpool_dialog(self):
        self.add_pool_dialog.close()
    
    @Slot(str, str, str, str, str, str, bool)
    def add_edit_pool(self, pool_id, pool_display_name, pool_url, pool_username, pool_password, pool_algo, pool_ssl):
        
        if not pool_display_name.strip():
            QMessageBox.warning(self.add_pool_dialog,'Add/Edit Pool Error', "Pool Name is required.")
            return
        if not pool_url.strip():
            QMessageBox.warning(self.add_pool_dialog,'Add/Edit Pool Error', "Pool URL/Port is required.")
            return
        if not pool_username.strip():
            QMessageBox.warning(self.add_pool_dialog,'Add/Edit Pool Error', "Wallet Address is required.")
            return
        if not pool_algo:
            QMessageBox.warning(self.add_pool_dialog,'Add/Edit Pool Error', "Hash algorithm is required.")
            return
         
        url_host = None
        url_port = None
        try:
            if '://' not in pool_url:
                pool_url = "stratum+tcp://" + pool_url
            url = urlparse.urlparse(pool_url.strip())
            if not url.hostname:
                QMessageBox.warning(self.add_pool_dialog,'Add/Edit Pool Error', "Pool URL (e.g. pool.sumokoin.com) is required.")
                return
                 
            if not url.port:
                reply = QMessageBox.question(self.add_pool_dialog,'Add Pool Confirmation',
                "Pool port is not specified.\nDo you want to use default port [3333] instead?", QMessageBox.Yes, QMessageBox.No)
                if reply == QMessageBox.No:
                    return
                url_port = 3333
            else:
                url_port = int(url.port)
                    
            url_host = url.hostname
        except Exception, e:
            log("Invalid pool URL: " + str(e), LEVEL_ERROR)
            QMessageBox.warning(self.add_pool_dialog, 'Add/Edit Pool Error', "Invalid pool URL!<br><br>Pool URL must be in form of <b>URL:Port</b><br> like <b>pool.sumokoin.com:3333</b>")
            return
        
        if pool_id == "":
            pool_id = str(uuid.uuid4())
            pool_info = {
                'id':  pool_id,
                'name': pool_display_name.strip()[:50],
                'url': "stratum+tcp://%s:%d" % (url_host, url_port),
                'username': pool_username.strip()[:512],
                'password': pool_password.strip()[:512],
                'algo': pool_algo,
                'is_fixed': False,
                'is_mining': False,
                'num_cpus': get_num_cpus(),
                'priority_level': 'normal',
                'is_hidden': False,
                'ssl_enabled': pool_ssl,
            }
             
            self.pools.add_pool(pool_info)
            # resize window to fit
            self.ui.resetWindowSize()
            # set pool info to UI
            _pool_info = {
                'id':  pool_info['id'],
                'name': smart_strip(pool_info['name'], 30),
                'algo': pool_info['algo'],
                'is_fixed': pool_info['is_fixed'],
                'is_hidden': pool_info['is_hidden'],
                'num_cpus': get_num_cpus() if pool_info['num_cpus'] == 0 else pool_info['num_cpus'],
                'priority_level': pool_info['priority_level'],
            }
            self.on_create_sumo_pool_list_event.emit(json.dumps([_pool_info]), CPU_COUNT, sys.platform == "win32")
            self.add_pool_dialog.close()
            QMessageBox.information(self.ui, '%s - Add Pool Success' % APP_NAME, 
                    "New mining pool \"%s\" \nhas been added!" % _pool_info['name'])
        else: # Edit pool
            pool_info = self.pools.find_pool(pool_id)
            need_restart_mining = False
            if pool_info:
                if pool_info['algo'] != pool_algo:
                    pool_info['algo'] = pool_algo
                    need_restart_mining = True
                    
                pool_info['name'] = pool_display_name.strip()[:50]
                
                url = "stratum+tcp://%s:%d" % (url_host, url_port)
                if pool_info['url'] != url:
                    pool_info['url'] =  url
                    need_restart_mining = True
                
                username = pool_username.strip()[:512]
                if pool_info['username'] != username:
                    pool_info['username'] = username
                    need_restart_mining = True
                
                password = pool_password.strip()[:512]
                if pool_info['password'] != password:
                    pool_info['password'] = password
                    need_restart_mining = True
                    
                if  'ssl_enabled' in pool_info and pool_info['ssl_enabled'] != pool_ssl:
                    need_restart_mining = True
                pool_info['ssl_enabled'] = pool_ssl


                pool_info['is_hidden'] = False
                
                _pool_info = {
                    'id':  pool_info['id'],
                    'name': smart_strip(pool_info['name'], 30),
                }
                self.on_edit_pool_success_event.emit(json.dumps(_pool_info))
                self.add_pool_dialog.close()
                
                # restart mining with new settings
                if need_restart_mining and pool_info['is_mining']: 
                    if self._stop_mining(pool_info):
                        self.on_stop_mining_event.emit(pool_info["id"])
                        self.app_process_events(1)
                        self.start_stop_mining(pool_info["id"], pool_info['num_cpus'])
                    
        # save pool list
        self.pools.save_all()
        
    @Slot(str)
    def edit_pool(self, pool_id):
        pool_info = self.pools.find_pool(pool_id)
        if pool_info:
#             if pool_info['is_mining'] and self._stop_mining(pool_info):
#                 self.on_stop_mining_event.emit(pool_info["id"]) 
            
            self.on_reset_addpool_form_event.emit()
            url = pool_info['url']
            if url.find('://') >= 0:
                url = url[url.find('://') + 3:]
            _pool_info = {
                'id':  pool_info['id'],
                'name':pool_info['name'],
                'url': url,
                'algo': pool_info['algo'],
                'username': pool_info['username'],
                'password': pool_info['password'],
                'is_fixed': pool_info['is_fixed'],
            }

            if 'ssl_enabled' in pool_info:
                _pool_info['ssl_enabled'] = pool_info['ssl_enabled']
            else:
                _pool_info['ssl_enabled'] = False
            self.on_edit_pool_event.emit(json.dumps(_pool_info))
            self.add_pool_dialog.exec_()
            
    @Slot()
    def quit_app(self):
        self.ui.handleExitAction(show_confirmation=True)
        
    @Slot(str)
    def open_link(self, link):
        webbrowser.open(link)
        
    @Slot()
    def get_new_address(self):
        result = QMessageBox.question(self.add_pool_dialog, "Get New Wallet Address?", \
             "This will open Sumokoin/Monero/Aeon wallet generator in browser.<br><br>\
             Are you sure to proceed?", \
             QMessageBox.Yes | QMessageBox.No, defaultButton=QMessageBox.Yes)
        
        if result == QMessageBox.No: return
        self.open_link("https://wallet.sumokoin.com")
        
            
    def update_hashrate(self, hash_rate):
        self.on_update_hashrate_event.emit(hash_rate)
    
    def report_error(self, pool_id, error):
        self.on_error_event.emit(pool_id, error)
    
    def create_pool_list(self):
        pool_list = []
        for p in self.pools.all_pools:
            pool_info = {
                'id':  p['id'],
                'name': smart_strip(p['name'], 30),
                'algo': p['algo'],
                'is_fixed': p['is_fixed'],
                'is_hidden': p['is_hidden'],
                'num_cpus': get_num_cpus() if p['num_cpus'] == 0 else p['num_cpus'],
                'priority_level': p['priority_level'] if 'priority_level' in p else 0,
            }
            pool_list.append(pool_info)
            
        self.on_create_sumo_pool_list_event.emit(json.dumps(pool_list), CPU_COUNT, sys.platform == "win32")
        
    
    def _custom_input_dialog(self, ui, title, label, 
                             text_echo_mode=QLineEdit.Normal, 
                             input_mode=QInputDialog.TextInput):
        dlg = QInputDialog(ui)                 
        dlg.setTextEchoMode(text_echo_mode)
        dlg.setInputMode(input_mode)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)                        
        dlg.resize(450, 100)                
        result = dlg.exec_()                             
        text = dlg.textValue()
        return (text, result)
        
    on_web_open_event = Signal(str)
    on_update_hashrate_event = Signal(str)
    on_error_event = Signal(str, str)
    on_back_end_error_event = Signal(str)
    on_create_sumo_pool_list_event = Signal(str, int, bool)
    on_hide_pool_success_event = Signal(str)
    on_remove_pool_confirm_event = Signal(str)
    on_edit_pool_success_event = Signal(str)
    on_start_mining_event = Signal(str)
    on_stop_mining_event = Signal(str)
    on_reset_addpool_form_event = Signal()
    on_edit_pool_event = Signal(str)
