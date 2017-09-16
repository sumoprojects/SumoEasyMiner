#!/usr/bin/python
# -*- coding: utf-8 -*-
## Copyright (c) 2017, The Sumokoin Project (www.sumokoin.org)
'''
Miner client
'''

import sys
import psutil
import binascii, json, socket, struct 
import threading, time, urlparse, random, platform
from multiprocessing import Process, Queue, Manager, cpu_count, Event
#from threading import Timer
try:
    from cryptonite_hash import cpu_has_aes_in_supported, cryptolite_hash, cryptonite_hash
except:
    from libs import cpu_has_aes_in_supported, cryptolite_hash, cryptonite_hash

USER_AGENT = "SumoMiner-CLI"
VERSION = [1, 0]

ALGORITHM_CRYPTONIGHT      = 'cryptonight'
ALGORITHM_CRYPTOLIGHT     = 'cryptonight-light'

ALGORITHMS = [ ALGORITHM_CRYPTONIGHT, ALGORITHM_CRYPTOLIGHT ]

OPT_RANDOMIZE = False  # Randomize scan range start to reduce duplicates
OPT_SCANTIME = 60
OPT_REPLY_WITH_RPC2_EXPLICIT = True # support for explicit RPC 2.0 in reply
OPT_SEND_PING = True
OPT_PING_INTERVAL = 1 # Ping interval in second

# Verbosity and log level
QUIET           = False
DEBUG           = False
DEBUG_PROTOCOL  = False
INFO            = True

LEVEL_PROTOCOL  = 'protocol'
LEVEL_INFO      = 'info'
LEVEL_DEBUG     = 'debug'
LEVEL_ERROR     = 'error'

POOL_ERROR_MSGS = ["Unauthenticated", "Timeout", "Invalid job id"]

HAS_AES_NI = cpu_has_aes_in_supported() # mark if CPU has AES-NI supported

CPU_COUNT = cpu_count()

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

def log(message, level):
    '''Conditionally write a message to stdout based on command line options and level.'''
    
    global DEBUG
    global DEBUG_PROTOCOL
    global QUIET
    global INFO
    
    if QUIET and level != LEVEL_ERROR: return
    if not DEBUG_PROTOCOL and level == LEVEL_PROTOCOL: return
    if not DEBUG and level == LEVEL_DEBUG: return
    if not INFO and level == LEVEL_INFO: return
    
    if level != LEVEL_PROTOCOL: message = '[%s] %s' % (level.upper(), message)
    
    print ("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))


# Convert from/to binary and hexidecimal strings (could be replaced with .encode('hex') and .decode('hex'))
hexlify = binascii.hexlify
unhexlify = binascii.unhexlify


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
    difficulty = float(0xffffffff)/target if target > 0 else 0. # difficulty
    
    return (target, difficulty)

  
class SimpleJsonRpcClient(object):
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
            except Exception, e:
                #print >> sys.stderr, e
                time.sleep(10)
                data = ""
                continue
            
            log('JSON-RPC Server > ' + line, LEVEL_PROTOCOL)
            
            # Parse the JSON
            try:
                reply = json.loads(line)
            except Exception, e:
                log("JSON-RPC Error: Failed to parse JSON %r (skipping)" % line, LEVEL_ERROR)
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
            raise self.ClientException('Not connected')
      
        if method == 'ping':
            with self._lock:
                self._socket.send('\r') # just to keep alive
            log('Ping sent', LEVEL_DEBUG)
            return
    
        request = dict(id = self._message_id, method = method, params = params)
      
        if OPT_REPLY_WITH_RPC2_EXPLICIT:
            request['jsonrpc'] = '2.0'
        
        message = json.dumps(request)
        with self._lock:
            self._requests[self._message_id] = request
            self._message_id += 1
            self._socket.send(message + '\n')
      
        log('JSON-RPC Server < ' + message, LEVEL_PROTOCOL)
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

    def __init__(self, url, username, password, work_submit_queue, g_work, hash_report_queue, is_cryptolite=False):
        SimpleJsonRpcClient.__init__(self)
    
        self._url = url
        self._username = username
        self._password = password
        self._work_submit_queue = work_submit_queue
        self._g_work = g_work
        #self._hash_report_queue = hash_report_queue
        self._is_cryptolite = is_cryptolite
      
        self._login_id = None
        self._thr_list = None
        self._cur_stratum_diff = 0.
      
        self._work_accepted = 0
        self._work_submited = 0
      
        self._my_sock = None
        #self._stopped = False
       
        
        self._hash_report = hash_report_queue
    
#         self._rpc_thread2 = threading.Thread(target = self.serve_forever)
#         self._rpc_thread2.daemon = True
#         self._rpc_thread2.start()
    
    #Timer(30, self.stop, ()).start()
  
    url = property(lambda s: s._url)
    username = property(lambda s: s._username)
    password = property(lambda s: s._password)
    login_id = property(lambda s: s._login_id)
  
    def stop(self):
        self._stopped = True
  
    def set_thread_list(self, thr_list):
        self._thr_list = thr_list
  
    # Overridden from SimpleJsonRpcClient
    def handle_reply(self, request, reply):
        """ Handle login result"""
        if request and request.get("method") == "login":
            error = reply.get("error")
            if not error is None:
                log("Error %d: %s" % (error.get('code'), error.get('message')), LEVEL_ERROR)
                # relogin after 10 seconds
                time.sleep(10)
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
            if reply.get("error") is not None:
                error = reply.get("error")
                log("rejected: %s, %d/%d, NO!!!" % (error.get("message"), 
                                                  self._work_accepted, self._work_submited), LEVEL_ERROR)
                if error.get("message") in POOL_ERROR_MSGS:
                    #self._login()
                    self.try_connect()
                
            elif reply.get("result") is not None:
                res = reply.get("result")
                if res.get("status") == "OK":
                    self._work_accepted += 1
                    _total_hash_rate = 0.
                    if len(self._hash_report) > 0:
                        _total_hash_rate = reduce(lambda x, y: x+y, [self._hash_report[k] for k in dict(self._hash_report)])
                    
                    readable_hashrate = human_readable_hashrate(_total_hash_rate)
                    accepted_percentage = self._work_accepted*100./self._work_submited
                    log("accepted %d/%d (%.2f%%), %s YES!" % (self._work_accepted, self._work_submited, 
                                                        accepted_percentage, readable_hashrate), LEVEL_INFO)
        
        elif reply.get("error") is not None:
            error = reply.get("error")
            if error.get("message") in POOL_ERROR_MSGS:
                #self._login()
                self.try_connect()
            log("Error %d: %s" % (error.get('code'), error.get('message')), LEVEL_ERROR)
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
            log("Invalid stratum target: %s" % target_hex, LEVEL_ERROR)
            return
              
        blob_hex = job_params.get("blob")
        try:
            blob_bin = unhexlify(blob_hex)
            nonce = long( hexlify(blob_bin[39:43]), 16)
            assert(len(blob_bin) == 76)
            assert(nonce >= 0)
        except:
            log("Invalid stratum blob: %s" % blob_hex, LEVEL_ERROR)
            return
          
        self._g_work['login_id'] = self._login_id
        self._g_work['target'] = target
        self._g_work['blob_bin'] = blob_bin
        self._g_work['nonce'] = nonce
        self._g_work['num_thrs'] = len(self._thr_list)
        self._g_work['job_id'] = job_id
        self._g_work['is_cryptolite'] = self._is_cryptolite
        
        log('New job recv: target="%s" blob="%s"' % (target_hex, blob_hex), LEVEL_DEBUG)
        if difficulty != self._cur_stratum_diff:
            log("Stratum difficulty set to %.f" % difficulty, LEVEL_INFO)
            self._cur_stratum_diff = difficulty
        
  
    def serve_forever(self):
        self.try_connect()
        start = time.time()
        while not self.exit.is_set():
            if not self._work_submit_queue.empty():
                work_submit = self._work_submit_queue.get()
                try:
                    self.send(method=work_submit['method'], params=work_submit['params'])
                    start = time.time() + OPT_PING_INTERVAL # delay sending 'ping'
                except socket.error, e:
                    #print >> sys.stderr, e
                    self.try_connect()
                    continue
            elif OPT_SEND_PING:
                """ 'ping' stratum server periodically to detect disconnection """
                elapsed = time.time() - start
                if elapsed >= OPT_PING_INTERVAL:
                    try:
                        self.send(method='ping', params=None)
                    except socket.error:
                        self.try_connect()
                        continue
                    finally:
                        start = time.time()            
            time.sleep(.1)
    
    def try_connect(self):
        url = urlparse.urlparse(self.url)
        hostname = url.hostname or ''
        port = url.port or 3333
          
        while not self.exit.is_set():
            if not self._my_sock:
                log('Connecting to RPC server [%s:%d]...' % (hostname, port), LEVEL_INFO)
                self._my_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock_keep_alive()
            else:
                log("Network error! Reconnecting...", LEVEL_ERROR)
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
              
            try:
                self._my_sock.connect((hostname, port))
                self.connect(self._my_sock)
            except socket.error:
                time.sleep(10)
            else:
                self._login()
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
        log('Logging in ...', LEVEL_INFO)
        params = dict(login=self._username, agent="%s/%d.%s" 
                                        %(USER_AGENT, VERSION[0], VERSION[1]))
        params['pass'] = self._password
        try:
            self.send(method='login', params = params)
        except socket.error:
            self.try_connect()
        else:
            # mark 'check idle time' to avoid multiple logins
            self._last_check_idle_time = time.time()

      
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
        _p.nice(cpu_priority_level)
  
    def run(self):
        _total_hashes = 0
          
        blob_bin = None
        nonce = 1
        max_nonce = target = login_id = 0
        #end_nonce = 0xffffffff - 0x20
        end_nonce = 0
        is_cryptolite = 0        # (if) is cryptonight-lite algo
          
        while not self.exit.is_set():
            try:
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
                    end_nonce = 0xffffffff /self._g_work['num_thrs']*(self._thr_id + 1) - 0x20
                    nonce += 0xffffffff/self._g_work['num_thrs']*self._thr_id
                    """ randomize nonce start"""
                    if OPT_RANDOMIZE:
                        offset = int(OPT_SCANTIME*self._hash_rate) if self._hash_rate > 0 else OPT_SCANTIME*64
                        nonce += random.randint(0, 0xffffffff/self._g_work['num_thrs'] - offset)
                    if nonce > 0xffffffff:
                        nonce = end_nonce
                
                max64 = int(OPT_SCANTIME*self._hash_rate) if self._hash_rate > 0 else 64                     
                if nonce + max64 > end_nonce:
                    #nonce = end_nonce - max64*2
                    max_nonce = end_nonce
                else:
                    max_nonce = nonce + max64                
                
                """ start hash scan """
                start = _start = time.time()
                hashes_done = total_hashes_done = 0
                while nonce <= max_nonce and not self.exit.is_set():
                    nonce_bin = struct.pack("<I", nonce)
                    blob_bin = blob_bin[:39] + nonce_bin + blob_bin[43:]
                    
                    if is_cryptolite:
                        _hash = cryptolite_hash(blob_bin, HAS_AES_NI)
                    else:
                        _hash = cryptonite_hash(blob_bin, HAS_AES_NI)
                  
                    nonce += 1
                    hashes_done += 1
                    total_hashes_done += 1
                    
                    """ calculate hashrate regularly """
                    if hashes_done > self._hash_rate*2:
                        elapsed = time.time() - _start
                        if elapsed > 0.1:
                            self._hash_rate = hashes_done/elapsed
                            """ share _hash rate """
                            self._shareHashRate()
                            log('CPU #%d: %.2f H/s' % (self._thr_id, self._hash_rate), LEVEL_DEBUG)
                            _start = time.time()
                            hashes_done = 0
                      
                    if struct.unpack("<I", _hash[28:])[0] < target:
                        """ Yes, hash found! """
                        params = dict(id=login_id, job_id = self._cur_job_id, 
                                      nonce=hexlify(nonce_bin), result=hexlify(_hash))
                        self._work_submit_queue.put({'method': 'submit', 'params': params})
                        break
                      
                    """ if there is a new work, break scan """
                    if self._g_work['job_id'] != self._cur_job_id:
                        break
                
                """ calculate hashrate """
                elapsed = time.time() - start
                self._hash_rate = total_hashes_done/elapsed if elapsed > 0 else 0.
                log('CPU #%d: %.2f H/s' % (self._thr_id, self._hash_rate), LEVEL_DEBUG)
                self._shareHashRate()
                
                """ if idle: """
                if total_hashes_done == 0:
                    time.sleep(.1)
            
            except KeyboardInterrupt:
                return
        
        ## Set hash_rate to 0.0 before exit
        self._hash_rate = 0.        
        self._shareHashRate()
    
    def _shareHashRate(self):
        self._hash_report_queue.update({'%d' % self._thr_id: self._hash_rate})
        
    def shutdown(self):
        log("Miner thread# %d shutdown initiated" % self._thr_id, LEVEL_DEBUG)
        self.exit.set()

def get_cpu_priority_level(priority_level):
    cpu_priority_level = NORMAL_CPU_PRIORITY_LEVEL
    if priority_level == "idle":
        cpu_priority_level = IDLE_CPU_PRIORITY_LEVEL
    elif priority_level == "low":
        cpu_priority_level = LOW_CPU_PRIORITY_LEVEL
    elif priority_level == "high":
        cpu_priority_level = HIGH_CPU_PRIORITY_LEVEL
    elif priority_level == "very_high":
        cpu_priority_level = VERY_HIGH_CPU_PRIORITY_LEVEL
    return cpu_priority_level

if __name__ == '__main__':
    import argparse
    
    # Cmd Example: 
    # python miner_cli.py -a cryptonight-light -o stratum+tcp://aeon.sumominer.com:3334 -u WmtuFrqE4gnFt1to3qUk3qDsC1LEuK6bqHY5L7HjMTjn8WMSaAGTvpLCbvj6W2phLuamkTGFAAMDmivhpQDH8Ker39DHJJhbd -p x -t 8 -P -d
    
    # Parse the command line
    parser = argparse.ArgumentParser(description = "SumoMiner for CryptoNode currency using the stratum protocol")
    
    parser.add_argument('-a', '--algo', default = ALGORITHM_CRYPTONIGHT, choices = ALGORITHMS, help = 'hashing algorithm to use for proof of work')
    parser.add_argument('-o', '--url', help = 'stratum mining server url (eg: stratum+tcp://foobar.com:3333)')
    parser.add_argument('-u', '--user', dest = 'username', help = 'username for mining server')
    parser.add_argument('-p', '--pass', dest = 'password', default = 'x', help = 'password for mining server')
    parser.add_argument('-t', '--threads', dest = 'threads', default = '0', help = 'number of mining threads')
    parser.add_argument('-prio', '--priority', dest = 'priority', default = 'normal', help = 'thread priority levels: idle, low, normal (default), high, very_high')
    
    parser.add_argument('-q', '--quiet', action ='store_true', help = 'suppress non-errors')
    parser.add_argument('-P', '--dump-protocol', dest = 'protocol', action ='store_true', help = 'show all JSON-RPC chatter')
    parser.add_argument('-d', '--debug', action ='store_true', help = 'show extra debug information')
    parser.add_argument('-r', '--randomize', action ='store_true', help = 'randomize scan range start to reduce duplicates')
    
    version = '%s v.%s' % (USER_AGENT, '.'.join(str(v) for v in VERSION))
    parser.add_argument('-v', '--version', action = 'version', version = version)
    
    options = parser.parse_args(sys.argv[1:])
        
    message = None
    if not options.url:
        message = "Pool URL must be supplied to start mining!"
    elif not options.username:
        message = "Username must be supplied to start mining!"
    
    if message:
        parser.print_help()
        print
        print >> sys.stderr, message
        sys.exit(1)
    
    # Set the logging level
    if options.debug: DEBUG = True
    if options.protocol: DEBUG_PROTOCOL = True
    if options.quiet: QUIET = True
    if options.randomize: OPT_RANDOMIZE = True
    
    manager = Manager()
    g_work = manager.dict()
    work_submit_queue = Queue()
    hash_report_queue = manager.dict()
           
    threads = int(options.threads) if int(options.threads) > 0 else CPU_COUNT
    is_cryptolite = options.algo == ALGORITHM_CRYPTOLIGHT
    
    thr_list = []
    rpc = None
    
    log('Starting [%s] in %d threads...' % (version, threads), LEVEL_INFO)
    log('CPU Supports AES-NI: %s' % ('YES' if HAS_AES_NI else 'NO'), LEVEL_INFO)
    
    cpu_priority_level = get_cpu_priority_level(options.priority)
    psutil.Process().nice(cpu_priority_level)
    
    try:
        for thr_id in range(threads):
            p = MinerWork(thr_id, work_submit_queue, g_work, hash_report_queue, cpu_priority_level)
            p.start()
            thr_list.append(p)
            log("Thread# %d started" % thr_id, LEVEL_DEBUG)
            time.sleep(0.2)      # stagger threads
      
        rpc = MinerRPC(options.url, options.username, options.password, 
                       work_submit_queue, g_work, hash_report_queue, is_cryptolite)
        rpc.set_thread_list(thr_list)
        rpc.serve_forever()
    
    except KeyboardInterrupt:
        log("(Ctrl+C) Stop mining...", LEVEL_INFO)
        for thr_proc in thr_list:
            thr_proc.shutdown()
            thr_proc.join()
        
        if rpc:
            rpc.shutdown()

        if manager: 
            manager.shutdown()
        
    sys.exit()