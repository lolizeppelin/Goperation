from websocket import create_connection
ws = create_connection("ws://172.31.0.110:4000/gcenter-wsgi.log",
                       subprotocols=["binary"])
print "Sending 'Hello, World'..."
# ws.send("Hello, World")
print "Sent"
print "Reeiving..."
# result =  ws.recv()
# print "Received '%s'" % result
# ws.close()

import time

while True:
    result =  ws.recv()
    print result,
    time.sleep(1)