PYTHON_VERSION=$(shell python -c 'import sys ; print sys.version[:3]')
DIST=archiver.tar.gz
MODULES=backend_*.py archiver.py archiver_svc.py lmtp.py
CONFS=archiver.ini archiver-win32.ini
TOOLS=Doxyfile pythfilter.py init.d NetfarmArchiver.nsi sql postfix
DOC=archiver.ini TODO ChangeLog* structure.txt
ALL=Makefile $(MODULES) $(DOC) $(TOOLS) $(CONFS)
TEST=work-lmtp/lmtp.py work-lmtp/testlmtp.py work-lmtp/checkaddr.py
all: $(DIST)

compile:
	python /usr/lib/python$(PYTHON_VERSION)/compileall.py .	
clean:
	rm -f *~ *.pyc *.pyo *.flc *.bak $(DIST)

cleandoc:
	rm -fr doc api *.log

distclean: clean cleandoc
	

pycheck:
	pychecker backend_*.py archiver.py lmtp.py

doxygen:
	@echo doxygen-ing...
	@doxygen 2>&1 | grep -v "param is not found in the argument list"
	@make doxygen-pdf

doxygen-pdf:
	@echo PDF-Doxygen
	@(cd doc/latex && make)

doxy:
	make doxygen >doxy.log && less doxy.log

epydoc-html:
	@echo Creating html Documentation
	epydoc --html -o api -n "Netfarm Mail Archiver" \
		--css green --private-css blue --ignore-param-mismatch \
		$(MODULES)

epydoc-pdf:
	@echo Creating pdf Documentation
	epydoc --pdf -o api -n "Netfarm Mail Archiver" --ignore-param-mismatch \
		$(MODULES)

epycheck:
	@echo epycheck...
	epydoc --check --ignore-param-mismatch $(MODULES) >epy.log 2>&1

epydoc: epydoc-html epydoc-pdf
docs: doxygen epydoc


$(DIST): $(ALL) $(TEST)
	tar czvf $(DIST) $(ALL) $(TEST)
