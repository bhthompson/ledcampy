#! /bin/bash
fswebcam -D 1 -r 160x190 --png 9 --no-banner /tmp/test.png
scp /tmp/test.png bhthompson@192.168.1.99:/media/raid/fileserver/Other/
