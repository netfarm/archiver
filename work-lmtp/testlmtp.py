#!/usr/bin/env python
from sys import argv,stdin
from lmtp import LMTP

m = LMTP("unix:"+argv[1])
data = stdin.read()
#m.debuglevel = 255
#print m.helo()
#print m.lhlo()
#print m.lmtp_features
#print m.esmtp_features
#print dir(m)
m.sendmail('<sherpya@netfarm.it>', ['<sherpya@of.war>'], data)
m.close()
