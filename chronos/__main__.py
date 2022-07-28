import sys

from main import Debugger

path = sys.argv[1]
db = Debugger()
db.run(path)
