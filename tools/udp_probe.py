# -*- coding: utf-8 -*-
"""Raw UDP probe for streaming debug: is ANYTHING arriving on :5000?

Prints packet sizes as they come. Run this INSTEAD of udp_view.py when
debugging. Interpretation:
  sizes printing (100-120000 bytes)  -> network fine, problem is decoder
  'MJPEG oversize' warnings          -> sender uses jpegparse not rtpjpegpay
  nothing for 10 s                   -> sender down / firewall / wrong net
"""
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 5000))
sock.settimeout(10)
print('listening on udp/5000 ...')
try:
    n = 0
    while True:
        data, addr = sock.recvfrom(70000)
        n += 1
        if n <= 20 or n % 100 == 0:
            print('#%d from %s: %d bytes (first=%02x%02x)'
                  % (n, addr[0], len(data), data[0], data[1]))
except socket.timeout:
    print('NOTHING arrived in 10 s -> sender not running, or blocked '
          'by firewall, or wrong subnet')
