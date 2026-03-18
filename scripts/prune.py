import sqlite3



import time



import os







DB = os.getenv("STATE_PATH", "./data/state.sqlite")







con = sqlite3.connect(DB)



cur = con.execute("DELETE FROM candidates WHERE created_ts < ?", (int(time.time()) - 30*86400,))



con.commit()



print(f"pruned candidates: {cur.rowcount}")