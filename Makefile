DIST=archiver.tar.gz
ALL=*.py Makefile archiver.ini TODO ChangeLog structure.txt init.d sql postfix
TEST=work-lmtp/lmtp.py work-lmtp/testlmtp.py work-lmtp/checkaddr.py
all: $(DIST)

clean:
	rm -f *~ *.pyc *.pyo *.flc $(DIST)

$(DIST): $(ALL) $(TEST)
	tar czvf $(DIST) $(ALL) $(TEST)
