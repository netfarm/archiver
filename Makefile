PYTHON_VERSION=2.3
DIST=archiver.tar.gz
MODULES=backend_*.py archiver.py lmtp.py
TOOLS=Doxyfile pythfilter.py init.d sql postfix
DOC=archiver.ini TODO ChangeLog* structure.txt
ALL=Makefile $(MODULES) $(DOC) $(TOOLS)
TEST=work-lmtp/lmtp.py work-lmtp/testlmtp.py work-lmtp/checkaddr.py
all: $(DIST)

compile:
	python /usr/lib/python$(PYTHON_VERSION)/compileall.py .	
clean:
	rm -f *~ *.pyc *.pyo *.flc $(DIST)

cleandoc:
	rm -fr doc api *.log

distclean: clean cleandoc
	

pycheck:
	pychecker backend_*.py archiver.py lmtp.py

doxygen:
	@echo doxygen-ing...
	@doxygen 2>&1 | grep -v "param is not found in the argument list"

doxy:
	make doxygen >doxy.log && less doxy.log

epydoc:
	@echo launching epydoc

	epydoc --html -o api -n "Netfarm Mail Archiver" \
		--css green --private-css blue --ignore-param-mismatch \
		$(MODULES)

	epydoc --pdf -o api -n "Netfarm Mail Archiver" --ignore-param-mismatch \
		$(MODULES)

epycheck:
	@echo epycheck...

	epydoc --check --ignore-param-mismatch $(MODULES) >epy.log 2>&1

docs: doxygen epydoc


$(DIST): $(ALL) $(TEST)
	tar czvf $(DIST) $(ALL) $(TEST)
