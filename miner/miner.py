#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Main miner worker, RPC client
'''


import sys, psutil

import json, socket, struct
import errno 
import ssl
import threading, time, urlparse, random, platform
from multiprocessing import Process, Event, cpu_count
#from threading import Timer
from libs import cpu_has_aes_in_supported, cryptolite_hash, cryptonite_hash
import settings

from utils.logger import log, LEVEL_DEBUG, LEVEL_ERROR, LEVEL_INFO, LEVEL_PROTOCOL

POOL_ERROR_MSGS = ["Unauthenticated", "Timeout", "Invalid job id"]

HAS_AES_NI = cpu_has_aes_in_supported() # mark if CPU has AES-NI supported
CPU_COUNT = cpu_count()
MAX_INT = 0xffffffff
    
# Convert from/to binary and hexidecimal strings 
# (could be replaced with .encode('hex') and .decode('hex'))
from binascii import hexlify, unhexlify

NETWORK_ERROR_MSG = "Network error! Reconnecting..."

def human_readable_hashrate(hashrate):
    '''Returns a human readable representation of hashrate.'''
    if hashrate < 1000:
        return '%.2f H/s' % hashrate
    if hashrate < 10000000:
        return '%.2f kH/s' % (hashrate / 1000)
    if hashrate < 10000000000:
        return '%.2f mH/s' % (hashrate / 1000000)
    return '%.2f gH/s' % (hashrate / 1000000000)

""" decode 256-bit target value """
def decode_target_value(target_hex):
    target_bin = unhexlify(target_hex)
    target_bin = target_bin[::-1]   # byte-swap and dword-swap
    target_bin_str = hexlify(target_bin)
    
    target = long(target_bin_str, 16)
    difficulty = float(MAX_INT)/target if target > 0 else 0. # difficulty
    
    return (target, difficulty)

  
class SimpleJsonRpcClient(threading.Thread):
    '''Simple JSON-RPC client.
    
      To use this class:
        1) Create a sub-class
        2) Override handle_reply(self, request, reply)
        3) Call connect(socket)
    
      Use self.send(method, params) to send JSON-RPC commands to the server.
    
      A new thread is created for listening to the connection; so calls to handle_reply
      are synchronized. It is safe to call send from withing handle_reply.
    '''

    class ClientException(Exception): pass
    
    class RequestReplyException(Exception):
        def __init__(self, message, reply, request = None):
            Exception.__init__(self, message)
            self._reply = reply
            self._request = request
    
        request = property(lambda s: s._request)
        reply = property(lambda s: s._reply)

    class RequestReplyWarning(RequestReplyException):
        '''Sub-classes can raise this to inform the user of JSON-RPC server issues.'''
        pass

    def __init__(self):
        threading.Thread.__init__(self)
        self._socket = None
        self._lock = threading.RLock()
        self._rpc_thread = None
        self._message_id = 1
        self._requests = dict()
        
        self.exit = Event()
        
    def _handle_incoming_rpc(self):
        data = ""
        while not self.exit.is_set():
            try:
                # Get the next line if we have one, otherwise, read and block
                if '\n' in data:
                    (line, data) = data.split('\n', 1)
                
                else:
                    chunk = self._socket.recv(1024)
                    if chunk: data += chunk
                    continue
#             except IOError as e:
#                 if e.errno == 10053: # Error: An established connection was aborted by the software in your host machine
#                     pass
#                 time.sleep(1)
#                 data = ""
#                 continue
            except Exception, e:
                #print >> sys.stderr, e
                time.sleep(1)
                data = ""
                continue
            
            log('JSON-RPC Server > ' + line, LEVEL_PROTOCOL, self._pool_id)
            
            # Parse the JSON
            try:
                reply = json.loads(line)
            except Exception, e:
                log("JSON-RPC Error: Failed to parse JSON %r (skipping)" % line, LEVEL_ERROR, self._pool_id)
                continue
            
            try:
                request = None
                with self._lock:
                    if 'id' in reply and reply['id'] in self._requests:
                        request = self._requests[reply['id']]
                    self.handle_reply(request = request, reply = reply)
            except self.RequestReplyWarning, e:
                output = e.message
                if e.request:
                    output += '\n  ' + e.request
                output += '\n  ' + e.reply
                log(output, LEVEL_ERROR)


    def handle_reply(self, request, reply):
        # Override this method in sub-classes to handle a message from the server
        raise self.RequestReplyWarning('Override this method')


    def send(self, method, params):
        '''Sends a message to the JSON-RPC server'''
        if not self._socket:
            #raise self.ClientException('Not connected')
            return
      
        if method == 'ping':
            with self._lock:
                self._socket.send('\r') # just to keep alive
            log('Ping sent', LEVEL_DEBUG, self._pool_id)
            return
    
        request = dict(id = self._message_id, method = method, params = params)
      
        if settings.OPT_REPLY_WITH_RPC2_EXPLICIT:
            request['jsonrpc'] = '2.0'
        
        message = json.dumps(request)
        with self._lock:
            self._requests[self._message_id] = request
            self._message_id += 1
            self._socket.send(message + '\n')
      
        log('JSON-RPC Server < ' + message, LEVEL_PROTOCOL, self._pool_id)
        return request


    def connect(self, socket):
        '''Connects to a remove JSON-RPC server'''
        self._socket = socket

        if not self._rpc_thread:
            self._rpc_thread = threading.Thread(target = self._handle_incoming_rpc)
            self._rpc_thread.daemon = True
            self._rpc_thread.start()
    
    def shutdown(self):
        log("RPC shutdown initiated", LEVEL_DEBUG)
        self.exit.set()
    

class MinerRPC(SimpleJsonRpcClient):
  
    class MinerRPCWarning(SimpleJsonRpcClient.RequestReplyWarning):
        def __init__(self, message, reply, request = None):
            SimpleJsonRpcClient.RequestReplyWarning.__init__(self, 'Mining Sate Error: ' + message, reply, request)

    class MinerRPCAuthenticationException(SimpleJsonRpcClient.RequestReplyException): pass

    def __init__(self, pool_info, work_submit_queue, g_work, work_report):
        SimpleJsonRpcClient.__init__(self)
    
        self._pool_info = pool_info
        self._pool_id = pool_info['id']
        self._url = pool_info['url']
        self._username = pool_info['username']
        self._password = pool_info['password']
        self._work_submit_queue = work_submit_queue
        self._g_work = g_work
        self._work_report = work_report
        
        self._login_id = None
        self._thr_list = None
        self._cur_stratum_diff = 0.
      
        if 'work_accepted' in work_report:
            self._work_accepted = work_report['work_accepted']
        else:
            self._work_accepted = 0
        
        if 'work_submited' in work_report:
            self._work_submited = work_report['work_submited']
        else:
            self._work_submited = 0

        self._my_sock = None
        self._last_check_idle_time = time.time()
        
        
    url = property(lambda s: s._url)
    username = property(lambda s: s._username)
    password = property(lambda s: s._password)
    login_id = property(lambda s: s._login_id)
  
    def set_thread_list(self, thr_list):
        self._thr_list = thr_list
  
    # Overridden from SimpleJsonRpcClient
    def handle_reply(self, request, reply):
        """ Handle login result"""
        if request and request.get("method") == "login":
            error = reply.get("error")
            if error is not None:
                self._pool_info['error'] = error.get('message')
                log("Error %d: %s" % (error.get('code'), error.get('message')), LEVEL_ERROR, self._pool_id)
                # relogin after 10 seconds
                if self._wait(10):
                    self._login()
                return
        
            result = reply.get("result")
            if result and result.get("status") == "OK":
                job_params = result.get("job")
                if job_params:
                    self._login_id = result.get("id")
                    """ handle job here """
                    self._set_new_job(job_params)
      
        elif request and request.get("method") == "submit":
            self._work_submited += 1
            self._work_report['work_submited'] = self._work_submited
            if reply.get("error") is not None:
                error = reply.get("error")
                log("rejected: %s, %d/%d, NO!!!" % (error.get("message"), 
                                                  self._work_accepted, self._work_submited), LEVEL_ERROR, self._pool_id)
                if error.get("message") in POOL_ERROR_MSGS:
                    #self._login()
                    self.try_connect()
                
            elif reply.get("result") is not None:
                res = reply.get("result")
                if res.get("status") == "OK":
                    self._work_accepted += 1
                    accepted_percentage = self._work_accepted*100./self._work_submited
#                     hash_rates = self._pool_info['hash_report'] if 'hash_report' in self._pool_info else {}
#                     if len(hash_rates) > 0:
#                         hash_rates = dict(hash_rates)
#                         _total_hash_rate = reduce(lambda x, y: x+y, [hash_rates[k] for k in hash_rates])
#                     else:
#                         _total_hash_rate = 0.0
                    _total_hash_rate = 0.0
                    if 'total_hashrate' in self._pool_info:
                        _total_hash_rate = self._pool_info['total_hashrate']
                    log("accepted %d/%d (%.2f%%), %s, YES!" % (self._work_accepted, self._work_submited, 
                        accepted_percentage, human_readable_hashrate(_total_hash_rate)), LEVEL_INFO, self._pool_id)
                    self._work_report['work_accepted'] = self._work_accepted
        
        elif reply.get("error") is not None:
            error = reply.get("error")
            if error.get("message") in POOL_ERROR_MSGS:
                #self._login()
                self.try_connect()
            log("Error %d: %s" % (error.get('code'), error.get('message')), LEVEL_ERROR, self._pool_id)
            #self.MinerRPCWarning(error.get("message"), reply)
      
        elif reply.get("method") == "job":
            job_params = reply.get("params")
            """ handle job here """
            if job_params:
                self._set_new_job(job_params)
      
     
    def _set_new_job(self, job_params):
        job_id = job_params.get("job_id")
        try:
            target_hex = job_params.get("target")
            target, difficulty = decode_target_value(target_hex)
            assert(target > 0 and difficulty > 0)
        except:
            log("Invalid stratum target: %s" % target_hex, LEVEL_ERROR, self._pool_id)
            return
              
        blob_hex = job_params.get("blob")
        try:
            blob_bin = unhexlify(blob_hex)
            nonce = long( hexlify(blob_bin[39:43]), 16)
            assert(len(blob_bin) == 76)
            assert(nonce >= 0)
        except:
            log("Invalid stratum blob: %s" % blob_hex, LEVEL_ERROR, self._pool_id)
            return
          
        self._g_work['login_id'] = self._login_id
        self._g_work['target'] = target
        self._g_work['blob_bin'] = blob_bin
        self._g_work['nonce'] = nonce
        self._g_work['num_thrs'] = len(self._thr_list)
        self._g_work['job_id'] = job_id
        self._g_work['is_cryptolite'] = self._pool_info['algo'] == "Cryptonight-Light"
        
        log('New job recv: target="%s" blob="%s"' % (target_hex, blob_hex), LEVEL_INFO, self._pool_id)
        if difficulty != self._cur_stratum_diff:
            self._cur_stratum_diff = difficulty
            self._work_report['difficulty'] = difficulty
            log("Stratum difficulty set to %.f" % difficulty, LEVEL_INFO, self._pool_id)
  
    def run(self):
        self.try_connect()
        start = time.time()
        while not self.exit.is_set():
            if not self._work_submit_queue.empty():
                work_submit = self._work_submit_queue.get()
                try:
                    self.send(method=work_submit['method'], params=work_submit['params'])
                    start = time.time() + settings.OPT_PING_INTERVAL # to delay sending 'ping' by interval setting
                except socket.error:
                    self.try_connect()
                    continue
            elif settings.OPT_SEND_PING:
                """ 'ping' stratum server periodically to detect disconnection """
                elapsed = time.time() - start
                if elapsed >= settings.OPT_PING_INTERVAL:
                    try:
                        self.send(method='ping', params=None)
                    except socket.error:
                        self.try_connect()
                        continue
                    finally:
                        start = time.time()
            
            """ relogin after 1 minute idle, i.e. receiving no new jobs for a long time, 
                may be due to some pool's error other than network error """
            if time.time() - self._last_check_idle_time >= 60:
                if 'error' in self._pool_info and self._pool_info['error'] == NETWORK_ERROR_MSG:
                    self._last_check_idle_time = time.time()
                    continue
                
                hash_rates = self._pool_info['hash_report'] if 'hash_report' in self._pool_info else None
                if hash_rates is not None and len(hash_rates) > 0: # it means mining is already on 
                    total_hash_rate = reduce(lambda x, y: x+y, [hash_rates[k] for k in dict(hash_rates)])
                    # but mining is now idle
                    if total_hash_rate == 0.:
                        self._login()
                self._last_check_idle_time = time.time()
                             
            time.sleep(.1)
        """ try to close socket before exit """
        try:
            self._my_sock.close()
        except:
            pass
    
    def try_connect(self):
        url = urlparse.urlparse(self.url)
        hostname = url.hostname
        try:
            port = int(url.port)
        except:
            self._pool_info['error'] = "Invalid pool port"
            log("Invalid pool port!", LEVEL_ERROR)
            return
        
        if not hostname:
            self._pool_info['error'] = "Invalid pool URL"
            log("Invalid pool URL", LEVEL_ERROR)
            return
          
        while not self.exit.is_set():
            if not self._my_sock:
                log('Connecting to RPC server [%s:%d]...' % (hostname, port), LEVEL_INFO, self._pool_id)
                self._my_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock_keep_alive()
            else:
                log(NETWORK_ERROR_MSG, LEVEL_ERROR, self._pool_id)
                self._pool_info['error'] = NETWORK_ERROR_MSG
                # (try to) stop all mining jobs by setting global job_id as None
                self._g_work['job_id'] = None
                # and clear submit works remain in queue if any
                while not self._work_submit_queue.empty():
                    _ = self._work_submit_queue.get()
                
                try:
                    self._my_sock.close()
                except:
                    pass
                else:
                    self._my_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._sock_keep_alive()
              
            if 'ssl_enabled' in self._pool_info and self._pool_info['ssl_enabled']:
                self._my_sock = ssl.wrap_socket(self._my_sock)

            try:
                self._my_sock.connect((hostname, port))
                self.connect(self._my_sock)
            except socket.error:
                # wait 10 seconds
                self._wait(10)
            else:
                self._login()
                if 'error' in self._pool_info: 
                    self._pool_info['error'] = None
                break
                
    
    def _sock_keep_alive(self):
        after_idle_sec = 1
        interval_sec= 3
        my_os = platform.system()
        try:
            if my_os == "Windows":
                self._my_sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, after_idle_sec*1000, interval_sec*1000))
            elif my_os == "Linux":
                self._my_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self._my_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
                self._my_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
            elif my_os == "Darwin":
                TCP_KEEPALIVE = 0x10
                self._my_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                self._my_sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, interval_sec)
        except:
            pass
        
    def _login(self):
        # (re)login
        log('Logging in ...', LEVEL_INFO, self._pool_id)
        params = dict(login=self._username, agent="%s/%d.%s" 
                      %(settings.USER_AGENT, settings.VERSION[0], settings.VERSION[1]))
        params['pass'] = self._password
        try:
            self.send(method='login', params = params)
        except socket.error:
            self.try_connect()
        else:
            # mark 'check idle time' to avoid multiple logins
            self._last_check_idle_time = time.time()
    
    def _wait(self, seconds=1):
        """ wait without blocking UI
        """
        for _ in range(seconds*10):
            if self.exit.is_set(): return False
            time.sleep(.1)
        return True
      
      
class MinerWork(Process):
    def __init__(self, thr_id, work_submit_queue, g_work, hash_report, cpu_priority_level):
        Process.__init__(self)
        self._cur_job_id = None
        self._hash_rate = 0.0
        self._thr_id = thr_id
        self._work_submit_queue = work_submit_queue
        self._g_work = g_work
        self._hash_report_queue = hash_report
        self.exit = Event()
                
        _p = psutil.Process(self.pid)
        _cpu_affinity = [CPU_COUNT - (thr_id % CPU_COUNT) - 1]
        if sys.platform == "win32":
            _p.cpu_affinity(_cpu_affinity)
        #_p.nice(cpu_priority_level)
  
    def run(self):
        _total_hashes = 0
          
        blob_bin = None
        nonce = 1
        max_nonce = target = login_id = 0
        #end_nonce = MAX_INT - 0x20
        end_nonce = 0
        is_cryptolite = 0        # (if) is cryptonight-lite algo
#         max_int32 = 2**32        # =4294967296
          
        while not self.exit.is_set():
            if not 'job_id' in self._g_work or self._g_work['job_id'] is None:
                self._hash_rate = 0.
                self._shareHashRate()
                time.sleep(.1)
                continue
            
                                 
            if self._g_work['job_id'] != self._cur_job_id:
                self._cur_job_id = self._g_work['job_id']
                nonce = self._g_work['nonce']
                blob_bin = self._g_work['blob_bin']
                target = self._g_work['target']
                login_id = self._g_work['login_id']
                is_cryptolite = self._g_work['is_cryptolite']
                end_nonce = MAX_INT /self._g_work['num_thrs']*(self._thr_id + 1) - 0x20
                nonce += MAX_INT/self._g_work['num_thrs']*self._thr_id
                """ randomize nonce start"""
                if settings.OPT_RANDOMIZE:
                    offset = int(settings.OPT_SCANTIME*self._hash_rate) if self._hash_rate > 0 else 64*settings.OPT_SCANTIME
                    nonce += random.randint(0, MAX_INT/self._g_work['num_thrs'] - offset)
                if nonce > MAX_INT - 0x20:
                    nonce = end_nonce
                
            max64 = int(settings.OPT_SCANTIME*self._hash_rate) if self._hash_rate > 0 else 64    
            if nonce + max64 > end_nonce:
                max_nonce = end_nonce
            else:
                max_nonce = nonce + max64
                
            if max_nonce > MAX_INT: 
                max_nonce = MAX_INT
            
            """ start _hash scan """
            total_hashes_done = 0
            _hashes_done = 0
            start = _start = time.time()
            while nonce <= max_nonce and not self.exit.is_set():
                nonce_bin = struct.pack("<I", nonce)
                blob_bin = blob_bin[:39] + nonce_bin + blob_bin[43:]
                
                if is_cryptolite:
                    _hash = cryptolite_hash(blob_bin, HAS_AES_NI)
                else:
                    _hash = cryptonite_hash(blob_bin, HAS_AES_NI)
              
                nonce += 1
                _hashes_done += 1
                total_hashes_done += 1
                
                """ calculate _hash rate"""
                if _hashes_done >= self._hash_rate/2:
#                 if _hashes_done >= 10:
                    elapsed = time.time() - _start
                    if elapsed > 0:
                        self._hash_rate = _hashes_done/elapsed
                        """ share _hash rate """
                        self._shareHashRate()
                        log('CPU #%d: %.2f H/s' % (self._thr_id, self._hash_rate), LEVEL_DEBUG)
                        _start = time.time()
                        _hashes_done = 0
                  
                if struct.unpack("<I", _hash[28:])[0] < target:
                    """ Yes, hash found! """
                    params = dict(id=login_id, job_id = self._cur_job_id, 
                                  nonce=hexlify(nonce_bin), result=hexlify(_hash))
                    self._work_submit_queue.put({'method': 'submit', 'params': params})
                    break
                  
                """ if there is a new work, break scan """
                if self._g_work['job_id'] != self._cur_job_id:
                    break
            
            
            elapsed = time.time() - start
            self._hash_rate = total_hashes_done/elapsed if elapsed > 0 else 0.
            """ share _hash rate """
            self._shareHashRate()
            log('CPU #%d: %.2f H/s' % (self._thr_id, self._hash_rate), LEVEL_DEBUG)
            
            """ if idle: """
            if total_hashes_done == 0:
                time.sleep(.1)
        
        ## Set hash_rate to 0.0 before exit
        self._hash_rate = 0.        
        self._shareHashRate()
    
    def _shareHashRate(self):
        self._hash_report_queue.update({'%d' % self._thr_id: self._hash_rate})
                
    def shutdown(self):
        log("Miner thread# %d shutdown initiated" % self._thr_id, LEVEL_DEBUG)
        self.exit.set()
        
    def set_cpu_priority(self, cpu_priority_level):
        _p = psutil.Process(self.pid)
        _p.nice(cpu_priority_level)
    
    def show_priority(self):
        _p = psutil.Process(self.pid)
        print "PID", _p.pid, "Priority", _p.nice()