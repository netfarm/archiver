#!/usr/bin/env python
from mimetools import Message
m = Message(open("bug1.eml"))

print m.getaddrlist('From')
