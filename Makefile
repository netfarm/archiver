VERSION=$(shell python -c 'import archiver ; print archiver.__version__')
PYTHON_VERSION=$(shell python -c 'import sys ; print sys.version[:3]')

DIST=archiver-$(VERSION).tar.gz
SUBDIRS=sql postfix
CONTRIB=$(wildcard sql/*.sql) $(wildcard postfix/*.cf) 
BACKENDS=$(wildcard backend_*.py)
MODULES=$(BACKENDS) archiver.py mtplib.py

CONFS=archiver.ini .pycheckrc
TOOLS=setup_all.py __init__.py init.d
DOCS=copyright.txt $(wildcard ChangeLog*) structure.txt

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
	pychecker backend_*.py archiver.py mtplib.py || true

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
	@chmod 755 $(DISTDIR)/{archiver,setup_all}.py
	@chmod 755 $(DISTDIR)/init.d
	@( cd dist && tar czf ../$(DIST) archiver-$(VERSION) )
	@echo Cleaning up dist && rm -fr dist
