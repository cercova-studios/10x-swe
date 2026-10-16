"""Disposable real-embedding check for search and transactional index maintenance."""
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
import search_index as index


def main():
    with tempfile.TemporaryDirectory(prefix='source-insights-search-check-') as tmp:
        root=Path(tmp)
        def entry(name,claim):
            d=root/'entries'/name;d.mkdir(parents=True,exist_ok=True)
            a={'title':name,'summary':claim,'tags':[name],'coverage':{'limitations':['Synthetic fixture.']},
               'insights':[{'claim':claim,'why_it_matters':'Retrieval check.', 'application':claim,
                            'caveats':'Synthetic fixture.','status':'source-claim','evidence':[{'page':1,'kind':'text','quote':claim}]}]}
            (d/'analysis.json').write_text(json.dumps(a))
            (d/'manifest.json').write_text(json.dumps({'source':f'https://example.org/{name}','source_id':name,'kind':'pdf'}))
            return d
        fruit=entry('fruit','Bananas are yellow fruit with a peel.')
        entry('agents','Agent approval requires the worker details and original project intent.')
        index.sync(root)
        assert list(index.search(root,'yellow fruit',mode='semantic'))[0]['title']=='fruit'
        assert list(index.search(root,'worker approval',mode='keyword'))[0]['title']=='agents'
        assert len(list(index.search(root,'fruit',limit=1)))==1
        assert list(index.search(root,'zzqxunknownword',mode='keyword'))==[]
        with patch.object(index,'embed',side_effect=lambda texts,**kw: [] if not texts else (_ for _ in ()).throw(AssertionError('unchanged entries re-embedded'))):
            index.sync(root)
        old=(root/'search.sqlite').read_bytes()
        entry('fruit','Oranges are citrus fruit rich in vitamin C.')
        with patch.object(index,'embed',side_effect=RuntimeError('injected embedding failure')):
            try:index.sync(root)
            except RuntimeError:pass
            else:raise AssertionError('failure was hidden')
        assert (root/'search.sqlite').read_bytes()==old
        db=index.connect(root/'search.sqlite')
        db.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON docs BEGIN SELECT RAISE(ABORT,'injected write failure'); END")
        db.commit();db.close()
        try:index.sync(root)
        except sqlite3.Error:pass
        else:raise AssertionError('transaction failure was hidden')
        db=index.connect(root/'search.sqlite')
        assert 'Bananas' in db.execute("SELECT body FROM docs WHERE entry='fruit'").fetchone()[0]
        assert db.execute('SELECT count(*) FROM docs').fetchone()[0]==2
        db.close()
        index.sync(root,rebuild=True)
        assert list(index.search(root,'citrus',mode='keyword'))[0]['title']=='fruit'
        (fruit/'analysis.json').unlink()
        index.sync(root)
        assert not list(index.search(root,'citrus',mode='keyword'))
        db=index.connect(root/'search.sqlite')
        assert db.execute('SELECT count(*) FROM docs').fetchone()[0]==1
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        db.close()
        (root/'search.sqlite').write_bytes(b'broken database')
        index.sync(root,rebuild=True)
        assert list(index.search(root,'approval',mode='keyword'))
    print('PASS: semantic/keyword retrieval, result bounds, incremental reuse, changed/deleted entries, failed embedding preservation, transaction rollback, corrupt-index rebuild.')

if __name__=='__main__':main()
