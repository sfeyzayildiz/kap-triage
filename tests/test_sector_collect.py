'''Tests moved from sector_collect.py (v1 self-test).'''
from kap_triage.collect.sectors import REQUESTS, SCHEMA, sector_rows


def test_sector_collect():
    symbols=[{'sC':'AAA','sT':'S','seI':1,'seC':'GIDA','d':False},
             {'sC':'BBB','sT':'S','seI':2,'seC':'','d':False},          # code from the sector list
             {'sC':'CCC','sT':'S','d':False},                            # no sector at all
             {'sC':'DDD','sT':'S','seI':1,'seC':'GIDA','d':True},
             {'sC':'DDD','sT':'S','seI':2,'seC':'DOKUMA','d':False},     # active entry wins
             {'sC':'XU100','sT':'I','seI':9,'seC':'X'},                  # not a stock
             {'sC':'ZZZ','sT':'S','seI':1,'seC':'GIDA'}]                 # not wanted
    sectors=[{'sI':1,'sC':'GIDA','d':'Gıda','de':'Food'},{'sI':2,'sC':'DOKUMA','d':'Dokuma','de':'Textile'}]
    rows,c=sector_rows(symbols,sectors,{'AAA','BBB','CCC','DDD','XU100','EEE'})
    assert rows==[('AAA',1,'GIDA','Gıda','Food'),('BBB',2,'DOKUMA','Dokuma','Textile'),('DDD',2,'DOKUMA','Dokuma','Textile')]
    assert c=={'wanted':6,'found':4,'missing':2,'no_sector':1,'with_sector':3,'sectors':2}
    assert REQUESTS['symbols'][1]=={'symbolType':'S'} and len(REQUESTS)==2
    import duckdb
    con=duckdb.connect()
    con.execute(SCHEMA)
    con.executemany('INSERT INTO symbol_sectors VALUES (?,?,?,?,?)',rows)
    assert con.execute('SELECT count(*) FROM symbol_sectors').fetchall()[0][0]==3
    con.close()
