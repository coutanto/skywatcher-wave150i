#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Sep  9 08:18:41 2025

@author: Olivier Coutant

"""
import ctypes
import time

DEBUG = True

def set_cmd(s):
    if DEBUG:
        print(s)
    return s

def h2i(x):
    return ctypes.c_int32(int(x, 16)).value

# unused for the moment, but summarizes axis1/axis2 parameters
axisParam={"axis1":        
               {
                   # set slew direction and speed according to X#000B return value
                   "slew":{"80000000":"0000000008CA96EB", "7FFFFFFF":"FFFFFFFFF7356915"},
                   # set goto motion prior to slewing
                   "delta+":215467, "delta-":430933,
                   # set origin value once mount is parked
                   "origin": "FFC4D200"
                }, 
           "axis2":
               {
                   "slew":{"80000000":"0000000007FD95D8", "7FFFFFFF":"FFFFFFFFF8026A28"},
                   "delta+":195840, "delta-":391680,
                   "origin": "0035CA00"}
                }
    
def TestStatus(resp, status):
    StatusDict = {
    "Tracking" : "((h2i(resp) & 0xF00)>>8 & 0b001) == 1",
    "Goto"     : "((h2i(resp) & 0xF00)>>8 & 0b001) == 0",
    "CCW"      : "((h2i(resp) & 0xF00)>>8 & 0b010) == 2",
    "CW"       : "((h2i(resp) & 0xF00)>>8 & 0b010) == 0",
    "Fast"     : "((h2i(resp) & 0xF00)>>8 & 0b100) == 4",
    "Slow"     : "((h2i(resp) & 0xF00)>>8 & 0b100) == 0",
    "Blocked"  : "((h2i(resp) & 0x0F0)>>4 & 0b010) == 2",
    "Normal"   : "((h2i(resp) & 0x0F0)>>4 & 0b010) == 0",
    "Running"  : "((h2i(resp) & 0x0F0)>>4 & 0b001) == 1",
    "Stopped"  : "((h2i(resp) & 0x0F0)>>4 & 0b001) == 0",
    "InitDone" : "((h2i(resp) & 0x00F)    & 0b001) == 1",
    "NotInit"  : "((h2i(resp) & 0x00F)    & 0b001) == 0"
    }
    if status not in StatusDict:
        raise ValueError ("cannot test on unknown status %s"%(status))
    return (eval(StatusDict[status]))        

def wait_for_status(client, cmd, status):
    """
    Wait for status "status" to become True by sending command f1 or f2 

    """
    cmd = set_cmd(cmd)
    ok, resp, err = client.send_and_recv(cmd)
    while not TestStatus(resp, status):
        time.sleep(client.inter_cmd_delay)
        ok, resp, err = client.send_and_recv(cmd)
        
def init_mount(client):
    """
    Initialization sequence taken from the sequence sent by 
    SynScan Pro to the Wave150i.
    The sequence was analysed using Wireshark on a Mac
    connected to the Wave150i Wifi and running SynScan Pro
    The sequence is reproduced as such

    """
    # is axis 1 initialized
    cmd = set_cmd(":f1")
    ok, resp, err = client.send_and_recv(cmd)
    if TestStatus(resp, "NotInit"):
        print('Initialize axis 1')
        cmd = set_cmd(":e1")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":q1010000")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":X10002")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":b1")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":s1")
        ok, _, err = client.send_and_recv(cmd)
        # set autoguide speed
        cmd = set_cmd(":P12")
        ok, _, err = client.send_and_recv(cmd)
        
        cmd = set_cmd(":V100")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":X10006")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":X10503")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":X10E00000000000000000000000000000000")
        ok, _, err = client.send_and_recv(cmd)
        # Set origin position
        cmd = set_cmd(":X101FFC4D200")
        ok, _, err = client.send_and_recv(cmd)
        # declared motor Initialized
        cmd = set_cmd(":F1")
        ok, _, err = client.send_and_recv(cmd)
        
    # is axis 2 initialized
    cmd = set_cmd(":f2")
    ok, resp, err = client.send_and_recv(cmd)
    if TestStatus(resp, "NotInit"):
        print('Initialize axis 2')
        cmd = set_cmd(":e2")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":X20002")
        ok, _, err = client.send_and_recv(cmd)
        # set autoguide speed
        cmd = set_cmd(":P22")
        ok, _, err = client.send_and_recv(cmd)
        cmd = set_cmd(":V200")
        ok, _, err = client.send_and_recv(cmd)
        # Set origin position
        cmd = set_cmd(":X2010035CA00")
        ok, _, err = client.send_and_recv(cmd)
        # declared motor Initialized
        cmd = set_cmd(":F2")
        ok, _, err = client.send_and_recv(cmd)                
        
    return True
    
def axis1(name, a1):
    """
    move axis 1 to parking position

    """
    print(f'start {name}')
    # make sur motor is stable
    cmd = set_cmd(":X102 00000000 00000000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    
    # reinit ?
    cmd = set_cmd(":W1080000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    
    # determine if motor is W or E
    cmd = set_cmd(":X1000B")
    ok, direction, err = a1.client.send_and_recv(cmd)
    if direction == "80000000":
        slew = "0000000008CA96EB"#"ccwise"
    elif direction == "7FFFFFFF" :
        slew = "FFFFFFFFF7356915"
         #"cwise"
    
    # position
    cmd = set_cmd(":X10003")
    ok, resp, err = a1.client.send_and_recv(cmd)
    pos = ctypes.c_int32(int(resp, 16)).value
    
    # first GOTO
    goto = pos + 215467
    cmd = set_cmd(f":X104{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    wait_for_status(a1.client, ":f1", "Stopped")
    cmd = set_cmd(":W1080000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X1000B")
    ok, resp, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X10003")
    ok, resp, err = a1.client.send_and_recv(cmd)
    pos = ctypes.c_int32(int(resp, 16)).value
    
    # second GOTO
    goto = pos - 430933
    cmd = set_cmd(f":X104{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    wait_for_status(a1.client, ":f1", "Stopped")
    cmd = set_cmd(":W1080000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X1000B")
    ok, resp, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X10003")
    ok, resp, err = a1.client.send_and_recv(cmd)
    pos = ctypes.c_int32(int(resp, 16)).value
    
    # third goto
    goto = pos + 215467
    cmd = set_cmd(f":X104{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    wait_for_status(a1.client, ":f1", "Stopped")
    cmd = set_cmd(":W1080000")
    ok, resp, err = a1.client.send_and_recv(cmd)

    # SLEW
    cmd = set_cmd(f":X102{slew}")
    ok, resp, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X1000B")
    ok, resp, err = a1.client.send_and_recv(cmd)

    while resp=="80000000" or resp=="7FFFFFFF":
        time.sleep(0.05)
        ok, resp, err = a1.client.send_and_recv(cmd)
    goto = ctypes.c_int32(int(resp, 16)).value
    cmd = set_cmd(":X1020000000000000000")
    ok, _, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X10003")
    ok, resp, err = a1.client.send_and_recv(cmd)

    # goto
    cmd = set_cmd(f":X104{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a1.client.send_and_recv(cmd)
    wait_for_status(a1.client, ":f1", "Stopped")
    
    # set position
    cmd = set_cmd(":X101FFC4D200")
    ok, _, err = a1.client.send_and_recv(cmd)
    cmd = set_cmd(":X1020000000000000000")
    ok, _, err = a1.client.send_and_recv(cmd)
    time.sleep(1.)
    
def axis2(name, a2):
    """
    move axis 2 to parking position

    """
    print(f'start {name}')
    # make sur motor is stable
    cmd = set_cmd(":X202 00000000 00000000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    
    # reinit ?
    cmd = set_cmd(":W2080000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    
    # determine if motor is W or E
    cmd = set_cmd(":X2000B")
    ok, direction, err = a2.client.send_and_recv(cmd)
    if direction == "80000000":
        slew = "0000000007FD95D8"
    elif direction == "7FFFFFFF" :
        slew = "FFFFFFFFF8026A28"
    
    # position
    cmd = set_cmd(":X20003")
    ok, resp, err = a2.client.send_and_recv(cmd)
    pos = ctypes.c_int32(int(resp, 16)).value
    
    # first GOTO
    goto = pos + 195840
    cmd = set_cmd(f":X204{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    wait_for_status(a2.client, ":f2", "Stopped")
    cmd = set_cmd(":W2080000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X2000B")
    ok, resp, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X20003")
    ok, resp, err = a2.client.send_and_recv(cmd)
    pos = ctypes.c_int32(int(resp, 16)).value
    
    # second GOTO
    goto = pos - 391680
    cmd = set_cmd(f":X204{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    wait_for_status(a2.client, ":f2", "Stopped")
    cmd = set_cmd(":W2080000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X2000B")
    ok, resp, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X20003")
    ok, resp, err = a2.client.send_and_recv(cmd)
    pos = ctypes.c_int32(int(resp, 16)).value
    
    # third goto
    goto = pos + 195840
    cmd = set_cmd(f":X204{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    wait_for_status(a2.client, ":f2", "Stopped")
    cmd = set_cmd(":W2080000")
    ok, resp, err = a2.client.send_and_recv(cmd)

    # SLEW
    cmd = set_cmd(f":X202{slew}")
    ok, resp, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X2000B")
    ok, resp, err = a2.client.send_and_recv(cmd)
    while resp=="80000000" or resp=="7FFFFFFF":                            #BUG? mettre 80000000 ou 7FFFFFFF
        time.sleep(0.05)
        ok, resp, err = a2.client.send_and_recv(cmd)
    goto = ctypes.c_int32(int(resp, 16)).value
    cmd = set_cmd(":X2020000000000000000")
    ok, _, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X20003")
    ok, resp, err = a2.client.send_and_recv(cmd)

    # goto
    cmd = set_cmd(f":X204{goto & 0xFFFFFFFF:08X}0000000000000000")
    ok, resp, err = a2.client.send_and_recv(cmd)
    wait_for_status(a2.client, ":f2", "Stopped")
    
    # set position
    cmd = set_cmd(":X2010035CA00")
    ok, goto, err = a2.client.send_and_recv(cmd)
    cmd = set_cmd(":X2020000000000000000")
    ok, _, err = a2.client.send_and_recv(cmd)
    