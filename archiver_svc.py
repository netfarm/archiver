#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2004 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2004 NetFarm S.r.l.  [http://www.netfarm.it]
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTIBILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
# ======================================================================
## @file archiver_svc.py
## Netfarm Mail Archiver [NtService]

__doc__ = '''Netfarm Archiver - release 2.0.0 - Nt Service'''
__version__ = '2.0.0'
__all__ = [ 'NetfarmArchiverService' ]

from win32serviceutil import ServiceFramework, HandleCommandLine
from win32service import SERVICE_STOP_PENDING
from servicemanager import LogMsg, LogErrorMsg
from servicemanager import EVENTLOG_INFORMATION_TYPE, PYS_SERVICE_STARTED, PYS_SERVICE_STOPPED

from sys import exc_info, path
from win32api import RegOpenKey, RegQueryValueEx, RegCloseKey, ExpandEnvironmentStrings
from win32con import HKEY_LOCAL_MACHINE

##
class NetfarmArchiverService(ServiceFramework):
    """ A class representing a Windows NT service """

    _svc_name_ = r'nma'
    _svc_display_name_ = r'Netfarm Mail Archiver'

    def __init__(self, args):
        """ Costructor for The NtService class """
        ServiceFramework.__init__(self, args)
        
        ## Read Configuration
        hKey = RegOpenKey(HKEY_LOCAL_MACHINE, r'Software\Netfarm\Netfarm Mail Archiver')
        value, type = RegQueryValueEx(hKey, 'ConfigFile')
        self.config = ExpandEnvironmentStrings(value)
        value, type = RegQueryValueEx(hKey, 'InstallPath')
        RegCloseKey(hKey)

        ## Append App path to python path
        path.append(ExpandEnvironmentStrings(value))
        
        from archiver import ServiceStartup, sig_int_term
        self.ServiceStartup = ServiceStartup
        self.ServiceStop = sig_int_term

    def SvcStop(self):
        """ Stops NtService """
        self.ReportServiceStatus(SERVICE_STOP_PENDING)
        self.ServiceStop(0, 0)

    def SvcDoRun(self):
        """ Starts NtService """
        LogMsg(EVENTLOG_INFORMATION_TYPE, PYS_SERVICE_STARTED, (self._svc_name_, ' (%s)' % self._svc_display_name_))
        res = 0
        try:
            res = self.ServiceStartup(self.config)
        except:
            t, val, tb = exc_info()
            LogErrorMsg('Netfarm Mail Archiver Service cannot start: %s - %s' % (t, val))

        if res:
            if res == -3: ## Bad config file
                LogErrorMsg('Netfarm Mail Archiver Service: Invalid config file path %s' % self.config)
            else:
                LogErrorMsg('Netfarm Mail Archiver Service returned an error (%d)' % res)
        else:
            LogMsg(EVENTLOG_INFORMATION_TYPE, PYS_SERVICE_STOPPED, (self._svc_name_, ' (%s) ' % self._svc_display_name_))
            
        return res

if __name__=='__main__':
    HandleCommandLine(NetfarmArchiverService)
