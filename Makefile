DIST=archiver2.tgz
ALL=*.py Makefile archiver.ini TODO ChangeLog structure.txt init.d sql postfix
TEST=work-lmtp/lmtp.py work-lmtp/testlmtp.py work-lmtp/checkaddr.py
all: $(DIST)

clean:
	rm -f *~ *.pyc *.pyo $(DIST)

$(DIST): $(ALL) $(TEST)
	tar czvf $(DIST) $(ALL) $(TEST)

upload:	all
	scp $(DIST) sherpya@skin.netfarm.it:
