PYTHON_VERSION=2.3
DIST=archiver.tar.gz
ALL=*.py Makefile archiver.ini TODO ChangeLog* structure.txt init.d sql postfix
TEST=work-lmtp/lmtp.py work-lmtp/testlmtp.py work-lmtp/checkaddr.py
all: $(DIST)

compile:
	python /usr/lib/python$(PYTHON_VERSION)/compileall.py .	
clean:
	rm -f *~ *.pyc *.pyo *.flc $(DIST)

cleandoc:
	rm -fr doc

pycheck:
	pychecker *.py

doxygen:
	doxygen doxygen.cfg


$(DIST): $(ALL) $(TEST)
	tar czvf $(DIST) $(ALL) $(TEST)
