#! /bin/sh
#
#		Written by Gianluigi Tiesi <sherpya@netfarm.it>
#
# Version:	@(#)skeleton  1.8  03-Mar-1998  miquels@cistron.nl
#

PATH=/sbin:/bin:/usr/sbin:/usr/bin
DAEMON=/var/lib/archiver/archiver.py
NAME=archiver
DESC="Netfarm Mail archiver"
RUNAS="cyrus"

test -f $DAEMON || exit 0

set -e

case "$1" in
  start)
	echo -n "Starting $DESC: "
	start-stop-daemon -c $RUNAS -b --start --exec /var/lib/archiver/archiver.py
	echo "$NAME."
	;;
  stop)
	echo -n "Stopping $DESC: "
	kill -INT `cat /var/lib/archiver/archiver.pid`
	echo "$NAME."
	;;
  restart|force-reload)
	$0 stop && $0 start
	;;
  *)
	N=/etc/init.d/$NAME
	echo "Usage: $N {start|stop|restart|force-reload}" >&2
	exit 1
	;;
esac

exit 0
