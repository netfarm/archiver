VERSION=2.0.0
PYTHON_VERSION=$(shell python -c 'import sys ; print sys.version[:3]')

DIST=archiver-$(VERSION).tar.gz
SUBDIRS=sql postfix
CONTRIB=$(wildcard sql/*.sql) $(wildcard postfix/*.cf) 
BACKENDS=$(wildcard backend_*.py)
MODULES=$(BACKENDS) archiver.py archiver_svc.py lmtp.py compress.py

CONFS=archiver.ini archiver-win32.ini .pycheckrc
TOOLS=Doxyfile pythfilter.py setup_all.py __init__.py init.d NetfarmArchiver.nsi nma.ico
DOCS=copyright.txt TODO $(wildcard ChangeLog*) structure.txt
TESTFILES=work-lmtp/lmtp.py work-lmtp/testlmtp.py work-lmtp/checkaddr.py

ALL=Makefile $(MODULES) $(DOCS) $(TOOLS) $(CONFS) $(CONTRIB)
DISTDIR=dist/archiver-$(VERSION)

all: $(DIST)

compile:
	python /usr/lib/python$(PYTHON_VERSION)/compileall.py .	
clean:
	rm -f *~ *.pyc *.pyo *.flc *.bak $(DIST) dist

cleandoc:
	rm -fr doc api *.log

distclean: clean cleandoc

pycheck:
	pychecker backend_*.py archiver.py lmtp.py || true

doxygen:
	@echo doxygen-ing...
	@doxygen 2>&1 | grep -v "param is not found in the argument list"
	@make doxygen-pdf

doxygen-pdf:
	@echo PDF-Doxygen
	@( cd doc/latex && make )

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

dist: $(DIST)
$(DIST): $(ALL)
	@rm -fr dist
	@mkdir -p $(DISTDIR)
	@for dir in $(SUBDIRS); do echo Creating $(DISTDIR)/$$dir ; install -m755 -d $(DISTDIR)/$$dir; done
	@for file in $(ALL); do echo Installing $(DISTDIR)/$$file ; install -m644 $$file $(DISTDIR)/$$file; done
	@chmod 755 $(DISTDIR)/{archiver,lmtp,pythfilter,setup_all}.py
	@chmod 755 $(DISTDIR)/init.d
	@( cd dist && tar czf ../$(DIST) archiver-$(VERSION) )
	@echo Cleaning up dist && rm -fr dist
