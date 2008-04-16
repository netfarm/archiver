#! /bin/sh
#
#		Written by Gianluigi Tiesi <sherpya@netfarm.it>
#
# Version:	@(#)skeleton  1.8  03-Mar-1998  miquels@cistron.nl
#

PATH=/sbin:/bin:/usr/sbin:/usr/bin
DAEMON=/usr/lib/archiver/archiver.py
PIDFILE=/var/lib/archiver/archiver.pid
NAME=archiver
TIMEOUT=120
DESC="Netfarm Mail archiver"
RUNAS="cyrus"

test -f $DAEMON || exit 0

set -e

case "$1" in
  start)
	echo -n "Starting $DESC: "
	start-stop-daemon --start --exec $DAEMON -- -u $RUNAS
	echo "$NAME."
	;;
  stop)
	echo -n "Stopping $DESC: "
	start-stop-daemon --retry $TIMEOUT --pidfile $PIDFILE --stop
	echo "$NAME."
	;;
  restart|force-reload)
	$0 stop && sleep 5 && $0 start
	;;
  *)
	N=/etc/init.d/$NAME
	echo "Usage: $N {start|stop|restart|force-reload}" >&2
	exit 1
	;;
esac

exit 0
