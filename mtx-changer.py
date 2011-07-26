#!/usr/bin/python
# -*- coding: utf-8 -*-
# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Copyright (C) 2006 Pietro Bertera <pietro@bertera.it>

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.

# Nelle versioni recenti di bacula il comando "status storage" da console
# interroga l'interfaccia dell'autochanger (Changer Command) per sapere quale
# cassetta ècaricata tramite il comando "loaded"
# Il problema è che il vecchio script mtx-changer rispondeve al comando loadd
# interrogzndo la bconsole con "status storage", questo crea un deadlock che fa rimanere
# appeso lo storage.
# Per risolverlo occorre: 
# Rilasciare il device del tape reader se non utilizzato (Always Open = No)
# Leggere la label della cassetta nel reader tramite btape passandogli un file di
# configurazione senza il supporto per l'autoloader

SLOTS = [   ("1", "G1"), 
            ("2", "G2"),
            ("3", "S1"),
            ("4", "S2"),
            ("5", "S3"),
            ("6", "S4"),
            ("7", "M1"),
            ("8", "M2"),
            ("9", "M3"),
        ]

BCONSOLE_CONFIG = "/etc/bacula/bconsole.conf"
BCONSOLE = "/usr/bin/bconsole"
BTAPE = "/usr/sbin/btape"
SD_CONFIG = "/etc/bacula/bacula-sd-manual.conf"
MT = "/bin/mt"
LOGFILE = "/tmp/mtx-changer.log"
SMTP = "localhost"
TO = "backup"
FROM = "backup@example.com"
SUBJECT = "Cambio Cassetta"
SUBJECT_ERROR = "Cambio cassetta: errore"
TAPE_REQUEST = "Per favore inserisci la cassetta %s nel tape reader"
TAPE_THANKS = "Grazie per avere inserito la cassetta %s"
TAPE_ERROR = "Errore! hai insterito la %s. Devi inserire la %s !"
LOG_FILE = "/tmp/changer.log"
RECHECK = 120 #secondi di attesa per il tape
REMAIL = 60 #n*RECHECk : una mail ogni ora
DEBUG = True


import sys, os, re, time, smtplib, email.Message, logging
from subprocess import Popen,PIPE

def usage():
    logger.error("Usage Error")
    sys.exit(1)

def mail(serverURL=None, sender='', to='', subject='', text=''):
    global logger
    logger.info("Sending email to: %s, subject: %s" % (to, subject))
    message = email.Message.Message()
    message["To"]      = to
    message["From"]    = sender
    message["Subject"] = subject
    message.set_payload(text)
    mailServer = smtplib.SMTP(serverURL)
    mailServer.sendmail(sender, to, message.as_string())
    mailServer.quit()

def b_exec(command):
    global logger
    exe = "echo %s | %s -c %s" % (command, BCONSOLE, BCONSOLE_CONFIG)
    logger.info('executing '+exe)
    
    p = Popen(exe, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=False)
    r, w, e = (p.stdout, p.stdin, p.stderr)

def readlabel(dev, silent=False):
    global logger
    
    logger.debug("readlabel")
    exe = "echo readlabel | %s -c %s %s"  % (BTAPE, SD_CONFIG, dev)
    p = Popen(exe, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
    r, w, e = (p.stdout, p.stdin, p.stderr)
    label = None
    for a in r.readlines():
        logger.debug("btape - " + a.strip())
        ref = re.compile(r"""VolName\s+:\s(.*)\n""")
        m = ref.search(a)
        if m:
            label = m.group(1)
            logger.debug("Label: "+label)
            break
        
    if label:
       for s,l in SLOTS:
           if l == label:
               logger.debug("Slot: "+s)
               if not silent:
                   print s
               return (s,label)
    else:
        logger.debug("No tape")
        if not silent:
            print "0"
            return False 
            
def rewind(tape):
    global logger
    logger.debug("rewind and eject")
    if readlabel(tape, True):
        exe = "%s -f %s rewoffl" % (MT, tape)
        p = Popen(exe, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
        r, w, e = (p.stdout, p.stdin, p.stderr)
        time.sleep(60)
    else:
        logger.info("Device empty")

def tape_online(dev):
    global logger
    exe = "%s -f %s status" % (MT, dev)
    logger.info("Checking if tape is online")
    p = Popen(exe, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
    r, w, e = (p.stdout, p.stdin, p.stderr)
    
    for a in r.readlines():
        logger.debug(a.strip())
        ref = re.compile(r"""ONLINE""")
        m = ref.search(a)
        if m:
            logger.info("Tape is ONLINE")
            return True
    logger.info("Tape is OFFLINE")
    return False
        
def main():
    global logger
    
    logger = logging.getLogger('mtx-changer')
    logger.debug("Start") 
    if LOGFILE:
        hdlr = logging.FileHandler(LOG_FILE)
    else:
        hdlr = logging.StreamHandler()
    
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    
    if DEBUG:
        logger.setLevel(logging.DEBUG)
    else: 
        logger.setLevel(logging.INFO)
            
    command = sys.argv[1]
    tape = ''
    if not command:
        logger.error("No command specified")
        sys.exit(1)
    if len(sys.argv) >= 2:
        tape_drive = sys.argv[2]
    else:
        logger.error("No drive specified")
        sys.exit(1)
    if len(sys.argv) >= 3:
        slot = sys.argv[3]
    else:
        logger.error("No slot specified")
        sys.exit(1)
    
    logger.info("Command: %s, drive: %s, slot: %s" % (command, tape_drive, slot))
    
    label = None
    
    for s,l in SLOTS:
        if s == slot:
            label = l
            break
    
    logger.info("Label for slot %s is %s" % (slot, label))
    
    if command == "unload":
        b_exec("umount")
        rewind(tape_drive)
        sys.exit(0)

    if command == "load":
        rewind(tape_drive)
        text = TAPE_REQUEST % label
        logger.info("sending mail to: %s" % TO)
        mail(SMTP, FROM, TO, SUBJECT, text)
        count = 0
        a = None
        while True:
            time.sleep(RECHECK)
            a = tape_online(tape_drive)
            if a:
                s, l = readlabel(tape_drive, True)
                logger.info("Tape:%s" % l)
                if l == label:
                    logger.info("Tape Correct")
                    text = TAPE_THANKS % label
                    mail(SMTP, FROM, TO, SUBJECT, text) 
                    break
                else:
                    logger.error("This tape is not correct")
                    text_error = TAPE_ERROR % (l,label)
                    mail(SMTP, FROM, TO, SUBJECT_ERROR, text_error)
                    b_exec("umount")
                    rewind(tape_drive)
                    count = 0
                                    
            else:
                if count == REMAIL:
                    mail(SMTP, FROM, TO, SUBJECT, text)
                    count = 0
                    
                count = count + 1
                
        print slot
        sys.exit(0)

    elif command == "list":
        for s,l in SLOTS:
            print s+":"+l
        sys.exit(0)
    
    elif command == "loaded":
        readlabel(tape_drive)
        sys.exit(0)
    
    elif command == "slots":
        print len(SLOTS)
        sys.exit(0)
    
    elif command == "volumes":
        for v,l in SLOTS:
            print v+":"+l
        sys.exit(0)
 
if __name__ == "__main__":
	main()
    sys.exit(0)
