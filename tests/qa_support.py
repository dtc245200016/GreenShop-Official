"""Shared QA paths, migration identity, schema snapshots and isolation guards."""
import hashlib, json, os, re, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get('GREENSHOP_QA_DIR', str(Path(tempfile.gettempdir()) / ('greenshop-release-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]))))
PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True)
PROJECT = os.environ.get('GREENSHOP_QA_PROJECT', 'greenshop-release-qa-' + hashlib.sha256(str(PRIVATE).encode()).hexdigest()[:10])

def expected_migrations():
    files = ROOT.joinpath('backend/GreenShop.Web/Migrations').glob('*.Designer.cs')
    ids = []
    for p in files:
        match = re.search(r'\[Migration\("([^\"]+)"\)\]', p.read_text())
        assert match, 'Migration attribute missing: '+str(p)
        migration_id=match.group(1)
        assert migration_id==p.name.removesuffix('.Designer.cs'), 'Filename/attribute mismatch'
        ids.append(migration_id)
    ids.sort()
    assert ids and all(re.fullmatch(r'\d{14}_[A-Za-z0-9_]+', x) for x in ids)
    return ids

def verify_migrations(sql):
    applied = sql('SELECT MigrationId FROM __EFMigrationsHistory ORDER BY MigrationId').splitlines()
    assert applied == expected_migrations(), {'expected':expected_migrations(), 'applied':applied}
    return applied

def verify_schema(sql):
    source=(ROOT/'backend/GreenShop.Web/Data/AppDbContext.cs').read_text()
    expected=set(re.findall(r'public DbSet<[^>]+> (\w+)',source))|{'__EFMigrationsHistory'}
    actual=set(sql('SHOW TABLES').splitlines())
    assert actual==expected, {'missing':sorted(expected-actual),'unexpected':sorted(actual-expected)}
    return sorted(actual)

def table_hashes(sql):
    """Cover every table, including composite keys and future tables without Id."""
    tables = sql('SHOW TABLES').splitlines()
    result = {}
    for table in tables:
        assert re.fullmatch(r'[A-Za-z0-9_]+', table)
        rows = sorted(sql('SELECT * FROM `' + table + '`').splitlines())
        columns = sql('SHOW COLUMNS FROM `' + table + '`')
        result[table] = hashlib.sha256((columns+'\n'+'\n'.join(rows)).encode()).hexdigest()
    return result

def guard(compose, main_compose, database_only=False):
    assert PROJECT.startswith('greenshop-') and '-qa-' in PROJECT
    qa_id = compose('ps','-q','db')
    assert qa_id and qa_id != main_compose('ps','-q','db'), 'QA must use a separate DB container'
    def inspect(cid):
        return json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
    qa, main = inspect(qa_id), inspect(main_compose('ps','-q','db'))
    assert qa['Config']['Labels']['com.docker.compose.project'] == PROJECT
    def env(c): return dict(s.split('=',1) for s in c['Config']['Env'] if '=' in s)
    assert env(qa)['MYSQL_DATABASE'] == 'greenshop_order_qa'
    assert env(qa)['MYSQL_ROOT_PASSWORD'] != env(main)['MYSQL_ROOT_PASSWORD']
    assert env(qa)['MYSQL_PASSWORD'] != env(main)['MYSQL_PASSWORD']
    def networks(c):return {n['NetworkID'] for n in c['NetworkSettings']['Networks'].values()}
    assert not (networks(qa) & networks(main)), 'QA and Main DB networks must differ'
    def mounts(c): return {x['Source'] for x in c['Mounts'] if x['Type'] in ('volume','bind')}
    for service in (('db',) if database_only else ('db','web_app')):
        assert not (mounts(inspect(compose('ps','-q',service))) & mounts(inspect(main_compose('ps','-q',service)))), 'Shared Main mounts'
    if not database_only:
        web=inspect(compose('ps','-q','web_app'))
        assert web['Config']['Labels']['com.docker.compose.project']==PROJECT
        assert networks(web) & networks(qa) and not (networks(web) & networks(main))
        connection=dict(part.split('=',1) for part in env(web)['ConnectionStrings__DefaultConnection'].split(';') if '=' in part)
        assert connection.get('Server')=='db' and connection.get('Database')=='greenshop_order_qa'
        assert connection.get('Uid')=='greenshop_app' and connection.get('Pwd')==env(qa)['MYSQL_PASSWORD'], 'QA web credentials/target differ from isolated DB'
    return True
