import sys

from main import debugger

path = sys.argv[1]
db = debugger()
db.run(path)
