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
	rm -fr doc *.log

distclean: clean cleandoc
	

pycheck:
	pychecker backend_*.py archiver.py lmtp.py

doxygen:
	@echo doxygen-ing...
	@doxygen 2>&1 | grep -v "param is not found in the argument list"

doxy:
	make doxygen >doxy.log && less doxy.log


$(DIST): $(ALL) $(TEST)
	tar czvf $(DIST) $(ALL) $(TEST)
