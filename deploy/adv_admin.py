#!/usr/bin/env python3
"""Local backup/preflight; never prints credentials or changes existing tables."""
import argparse
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'/'common'))
import arscfg


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--backup-dir',required=True)
    a=p.parse_args();cp=arscfg.load(a.config);dest=Path(a.backup_dir)
    dest.mkdir(mode=0o700,parents=True,exist_ok=True)
    dump=shutil.which('mariadb-dump') or shutil.which('mysqldump')
    if not dump:raise SystemExit('Install mariadb-client first; DB backup required')
    db=arscfg.db_connect(cp)
    try:
        with db.cursor() as c:
            tables=('devices','session_logins','responses','rejected')
            c.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s', (cp['db']['name'],))
            engines={r['TABLE_NAME']:r['ENGINE'] for r in c.fetchall()}
            if any(engines.get(t)!='InnoDB' for t in tables):
                raise SystemExit('Required business tables must be InnoDB for atomic transaction/ledger')
    finally:db.close()
    def escaped(v):return '"'+str(v).replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
    fd,name=tempfile.mkstemp(prefix='ars-backup-',suffix='.cnf',dir=dest)
    raw=dest/'database-before.sql'
    try:
        with os.fdopen(fd,'w') as f:
            f.write('[client]\n')
            for key,value in [('host',cp['db']['host']),('port',cp['db'].get('port','3306')),
                              ('user',cp['db']['user']),('password',cp['db']['password'])]:
                f.write(key+'='+escaped(value)+'\n')
        with raw.open('wb') as out:
            subprocess.run([dump,'--defaults-extra-file='+name,'--single-transaction','--skip-lock-tables',
                            '--no-tablespaces','--default-character-set=utf8mb4',cp['db']['name']],stdout=out,check=True)
        os.chmod(raw,0o600)
        with raw.open('rb') as inp,gzip.open(dest/'database-before.sql.gz','wb') as out:
            shutil.copyfileobj(inp,out)
        raw.unlink()
        print('Database backup saved:',dest/'database-before.sql.gz')
    finally:Path(name).unlink(missing_ok=True)

if __name__=='__main__':main()
