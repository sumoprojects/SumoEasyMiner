# Sumo Easy Miner

Copyright (c) 2017, Sumokoin.org

The most easy, intuitive CPU miner for cryptonote-based cryptocurrencies like SUMOKOIN (SUMO), Monero (XMR), Aeon (AEON) etc.

![](http://www.sumokoin.org/images/easy-miner-features_1080x1100.png)

## USAGE

### Download

**Windows and Mac OS X**

Visit https://github.com/sumoprojects/SumoEasyMiner/releases.

**Linux**
- Clone `git clone https://github.com/sumoprojects/SumoEasyMiner SumoEasyMiner` or [download SumoEasyMiner repo](https://github.com/sumoprojects/SumoEasyMiner/archive/master.zip).
- Clone `git clone https://github.com/sumoprojects/cryptonight-hash-lib cryptonight-hash-lib` or [download cryptonight-hash-lib repo](https://github.com/sumoprojects/cryptonight-hash-lib/archive/master.zip).

### Install Dependencies
- `sudo apt-get install cmake gcc python-dev python-pip python-pyside`
-  `pip install psutil`

### Compile library and run
- `cd /path/to/cryptonight-hash-lib`
- `cmake .`

The last lines of the output should look something like this:
```
-- Configuring done
-- Generating done
-- Build files have been written to: /path/to/cryptonight-hash-lib
```
- `make`

The last lines of the output should look something like this:
```
[100%] Linking C shared library cryptonite_hash.so
[100%] Built target cryptonite_hash
```
- Copy just created `cryptonite_hash.so` from `cryptonight-hash-lib` folder to `/path/to/SumoEasyMiner/libs` folder.
```
- Run the miner with `python sumominer.py`
- Start mining
```