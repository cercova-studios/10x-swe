-- Administrator-reviewed PostgreSQL 16+ migration. Verify on an isolated branch first.
-- No credentials. Runtime gets function execution only; URL/title publication is explicit.
BEGIN;
DO $migration$
DECLARE
 marker constant text := 'BookmarkDrop reviewed publisher v1';
 name text; role_row record;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_class WHERE oid='public.source_links'::regclass
   AND relkind='r' AND NOT relrowsecurity AND NOT relforcerowsecurity)
   OR to_regclass('public.source_link_tombstones') IS NULL THEN
  RAISE EXCEPTION 'Review source_links and pruning tombstones before activation';
 END IF;
 IF EXISTS(
   SELECT 1 FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
   JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang
   WHERE t.tgrelid='public.source_links'::regclass AND NOT t.tgisinternal
   AND NOT coalesce(pg_get_triggerdef(t.oid)=
    'CREATE TRIGGER reading_bookmarks_changed AFTER INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.source_links FOR EACH STATEMENT EXECUTE FUNCTION bump_reading_feed_revision(''bookmarks'')'
    AND n.nspname='public' AND p.proname='bump_reading_feed_revision'
    AND l.lanname='plpgsql' AND p.prosecdef AND p.proconfig=ARRAY['search_path=pg_catalog']
    AND btrim(p.prosrc)='BEGIN UPDATE public.reading_feed_revisions SET revision=revision+1 WHERE feed=TG_ARGV[0]; RETURN NULL; END;',false)
 ) THEN RAISE EXCEPTION 'Review unknown source_links triggers before activation'; END IF;
 FOREACH name IN ARRAY ARRAY['bookmarkdrop_api_owner','bookmarkdrop_publisher'] LOOP
  SELECT * INTO role_row FROM pg_roles WHERE rolname=name;
  IF FOUND THEN
   IF shobj_description(role_row.oid,'pg_authid') IS DISTINCT FROM marker
      OR role_row.rolsuper OR role_row.rolcreatedb OR role_row.rolcreaterole
      OR role_row.rolinherit OR role_row.rolreplication OR role_row.rolbypassrls
      OR role_row.rolcanlogin<>(name='bookmarkdrop_publisher') THEN
    RAISE EXCEPTION 'Unexpected preexisting role %',name;
   END IF;
  ELSE
   EXECUTE format('CREATE ROLE %I %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
     name,CASE WHEN name='bookmarkdrop_publisher' THEN 'LOGIN' ELSE 'NOLOGIN' END);
   EXECUTE format('COMMENT ON ROLE %I IS %L',name,marker);
  END IF;
  IF EXISTS(SELECT 1 FROM pg_auth_members WHERE member=role_row.oid) THEN
   RAISE EXCEPTION 'Unexpected role membership for %',name;
  END IF;
 END LOOP;
 PERFORM set_config('bookmarkdrop.admin_inherit',coalesce((
   SELECT bool_or(inherit_option)::text FROM pg_auth_members
   WHERE roleid='bookmarkdrop_api_owner'::regrole AND member=current_user::regrole),'false'),true);
 PERFORM set_config('bookmarkdrop.admin_set',coalesce((
   SELECT bool_or(set_option)::text FROM pg_auth_members
   WHERE roleid='bookmarkdrop_api_owner'::regrole AND member=current_user::regrole),'false'),true);
 EXECUTE format('GRANT bookmarkdrop_api_owner TO %I WITH INHERIT TRUE, SET TRUE',current_user);
 IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='bookmarkdrop_api'
   AND (nspowner<>'bookmarkdrop_api_owner'::regrole
     OR obj_description(oid,'pg_namespace') IS DISTINCT FROM marker)) THEN
  RAISE EXCEPTION 'Unexpected preexisting bookmarkdrop_api schema';
 END IF;
END $migration$;
CREATE SCHEMA IF NOT EXISTS bookmarkdrop_api AUTHORIZATION bookmarkdrop_api_owner;
COMMENT ON SCHEMA bookmarkdrop_api IS 'BookmarkDrop reviewed publisher v1';
REVOKE ALL ON SCHEMA bookmarkdrop_api FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO bookmarkdrop_api_owner;
GRANT SELECT(source,url,title,notion_timestamp,first_seen_at,last_seen_at),
 INSERT(source,url,title,notion_timestamp) ON public.source_links TO bookmarkdrop_api_owner;
GRANT SELECT(url) ON public.source_link_tombstones TO bookmarkdrop_api_owner;
SET LOCAL ROLE bookmarkdrop_api_owner;
CREATE TABLE IF NOT EXISTS bookmarkdrop_api.origins (
 provider text NOT NULL,account text NOT NULL,external_id text NOT NULL,url text NOT NULL,payload jsonb NOT NULL,
 PRIMARY KEY(provider,account,external_id)
);
CREATE TABLE IF NOT EXISTS bookmarkdrop_api.receipts (
 operation text PRIMARY KEY,checksum text NOT NULL,result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bookmarkdrop_api.relationships (
 a text NOT NULL,b text NOT NULL,kind text NOT NULL,suppressed boolean NOT NULL DEFAULT false,
 PRIMARY KEY(a,b,kind),CHECK(a<b),CHECK(kind IN ('related','similar')),CHECK(kind<>'similar' OR suppressed)
);
CREATE OR REPLACE FUNCTION bookmarkdrop_api.preview_urls(p_urls text[]) RETURNS TABLE(url text,status text)
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT u,CASE WHEN EXISTS(SELECT 1 FROM public.source_links l WHERE l.url=u) THEN 'existing'
   WHEN EXISTS(SELECT 1 FROM public.source_link_tombstones t WHERE t.url=u) THEN 'pruned' ELSE 'new' END
 FROM unnest(p_urls) u WHERE cardinality(p_urls)<=100
$$;
CREATE OR REPLACE FUNCTION bookmarkdrop_api.apply_batch(p_operation text,p_items jsonb) RETURNS jsonb
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE item jsonb; field text; inserted integer; new_count integer:=0; dupe_count integer:=0; pruned_count integer:=0;
 existing bookmarkdrop_api.receipts%ROWTYPE; result jsonb;
BEGIN
 IF coalesce(p_operation !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p_items)<>'array'
   OR jsonb_array_length(p_items) NOT BETWEEN 1 AND 100,true) THEN
  RAISE EXCEPTION 'Invalid operation/batch' USING ERRCODE='22023';
 END IF;
 -- Same transaction lock as rsrch-ingest and pruning; no new coordination protocol.
 PERFORM pg_advisory_xact_lock(20771123);
 SELECT * INTO existing FROM bookmarkdrop_api.receipts WHERE operation=p_operation;
 IF FOUND THEN
  IF existing.checksum<>md5(p_items::text) THEN RAISE EXCEPTION 'Receipt mismatch' USING ERRCODE='22023'; END IF;
  RETURN existing.result;
 END IF;
 FOR item IN SELECT * FROM jsonb_array_elements(p_items) LOOP
  IF coalesce(jsonb_typeof(item)<>'object'
   OR NOT (item ?& ARRAY['schema','provider','account','external_id','url','title','excerpt','note','tags','folder','saved_at','updated_at','kind','kind_source'])
   OR item->'schema'<>'1'::jsonb
   OR EXISTS(SELECT 1 FROM jsonb_object_keys(item) k WHERE k NOT IN
    ('schema','provider','account','external_id','url','title','excerpt','note','tags','folder','saved_at','updated_at','kind','kind_source','imported_origin'))
   OR item->>'provider' NOT IN ('manual','instapaper','raindrop','neon')
   OR jsonb_typeof(item->'provider')<>'string'
   OR jsonb_typeof(item->'account')<>'string' OR octet_length(item->>'account') NOT BETWEEN 1 AND 256
   OR jsonb_typeof(item->'external_id')<>'string' OR octet_length(item->>'external_id') NOT BETWEEN 1 AND 8192
   OR jsonb_typeof(item->'url')<>'string' OR octet_length(item->>'url') NOT BETWEEN 1 AND 8192
   OR item->>'url' !~* '^https?://[^/?#@[:space:]]+([/?#].*)?$' OR item->>'url' ~ '[[:space:][:cntrl:]]'
   OR jsonb_typeof(item->'title')<>'string' OR octet_length(item->>'title')>4096
   OR jsonb_typeof(item->'excerpt')<>'string' OR octet_length(item->>'excerpt')>10000
   OR jsonb_typeof(item->'note')<>'string' OR octet_length(item->>'note')>10000
   OR jsonb_typeof(item->'folder')<>'string' OR octet_length(item->>'folder')>512
   OR jsonb_typeof(item->'saved_at') NOT IN ('string','null') OR octet_length(coalesce(item->>'saved_at',''))>100
   OR jsonb_typeof(item->'updated_at') NOT IN ('string','null') OR octet_length(coalesce(item->>'updated_at',''))>100
   OR item->>'kind' NOT IN ('blog','article','video','paper','documentation','book','other')
   OR item->>'kind_source' NOT IN ('manual','provider','url','unknown')
   OR jsonb_typeof(item->'tags')<>'array' OR jsonb_array_length(item->'tags')>100,true) THEN
    RAISE EXCEPTION 'Invalid bookmark fields' USING ERRCODE='22023';
  END IF;
  IF item->'imported_origin' IS NOT NULL AND item->'imported_origin'<>'null'::jsonb THEN
   RAISE EXCEPTION 'Restore root identity before publication' USING ERRCODE='22023';
  END IF;
  IF EXISTS(SELECT 1 FROM jsonb_array_elements(item->'tags') t
    WHERE jsonb_typeof(t)<>'string' OR octet_length(t#>>'{}')>256
      OR translate(t#>>'{}',E'\n\t','') ~ '[[:cntrl:]]') THEN
   RAISE EXCEPTION 'Invalid tags' USING ERRCODE='22023';
  END IF;
  FOREACH field IN ARRAY ARRAY['account','external_id','title','excerpt','note','folder','saved_at','updated_at'] LOOP
   IF translate(item->>field,E'\n\t','') ~ '[[:cntrl:]]' THEN
    RAISE EXCEPTION 'Invalid controls' USING ERRCODE='22023';
   END IF;
  END LOOP;
  inserted:=0;
  IF EXISTS(SELECT 1 FROM public.source_links WHERE url=item->>'url') THEN
   dupe_count:=dupe_count+1;
  ELSIF EXISTS(SELECT 1 FROM public.source_link_tombstones WHERE url=item->>'url') THEN
   pruned_count:=pruned_count+1;
  ELSE
   INSERT INTO public.source_links(source,url,title,notion_timestamp)
    VALUES('bookmarkdrop',item->>'url',nullif(item->>'title',''),NULL) ON CONFLICT DO NOTHING;
   GET DIAGNOSTICS inserted=ROW_COUNT;
   new_count:=new_count+inserted;dupe_count:=dupe_count+(1-inserted);
  END IF;
  -- Preserve every origin without overwriting existing public titles or empty annotations.
  INSERT INTO bookmarkdrop_api.origins VALUES(item->>'provider',item->>'account',item->>'external_id',item->>'url',item)
   ON CONFLICT(provider,account,external_id) DO UPDATE SET url=EXCLUDED.url,
    payload=EXCLUDED.payload || jsonb_build_object(
     'title',coalesce(nullif(EXCLUDED.payload->>'title',''),bookmarkdrop_api.origins.payload->>'title',''),
     'excerpt',coalesce(nullif(EXCLUDED.payload->>'excerpt',''),bookmarkdrop_api.origins.payload->>'excerpt',''),
     'note',coalesce(nullif(EXCLUDED.payload->>'note',''),bookmarkdrop_api.origins.payload->>'note',''),
     'folder',coalesce(nullif(EXCLUDED.payload->>'folder',''),bookmarkdrop_api.origins.payload->>'folder',''),
     'tags',CASE WHEN jsonb_array_length(EXCLUDED.payload->'tags')=0 THEN bookmarkdrop_api.origins.payload->'tags' ELSE EXCLUDED.payload->'tags' END,
     'saved_at',coalesce(nullif(EXCLUDED.payload->'saved_at','null'::jsonb),bookmarkdrop_api.origins.payload->'saved_at'),
     'updated_at',coalesce(nullif(EXCLUDED.payload->'updated_at','null'::jsonb),bookmarkdrop_api.origins.payload->'updated_at'),
     'kind',CASE WHEN EXCLUDED.payload->>'kind_source'='unknown' OR
       (bookmarkdrop_api.origins.payload->>'kind_source'='manual' AND EXCLUDED.payload->>'kind_source'<>'manual')
       THEN bookmarkdrop_api.origins.payload->>'kind' ELSE EXCLUDED.payload->>'kind' END,
     'kind_source',CASE WHEN EXCLUDED.payload->>'kind_source'='unknown' OR
       (bookmarkdrop_api.origins.payload->>'kind_source'='manual' AND EXCLUDED.payload->>'kind_source'<>'manual')
       THEN bookmarkdrop_api.origins.payload->>'kind_source' ELSE EXCLUDED.payload->>'kind_source' END);
 END LOOP;
 result:=jsonb_build_object('new',new_count,'duplicate',dupe_count,'pruned',pruned_count,'origins',jsonb_array_length(p_items));
 INSERT INTO bookmarkdrop_api.receipts VALUES(p_operation,md5(p_items::text),result,now());
 RETURN result;
END $$;
CREATE OR REPLACE FUNCTION bookmarkdrop_api.read_records(p_cursor text,p_limit integer) RETURNS TABLE(key text,payload jsonb)
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT * FROM (
  SELECT jsonb_build_array('public',source,url)::text AS key,
   jsonb_build_object('schema',1,'url',url,'title',coalesce(title,''),'excerpt','','note','','tags','[]'::jsonb,
    'folder','','saved_at',coalesce(notion_timestamp,first_seen_at)::text,'updated_at',last_seen_at::text) payload
   FROM public.source_links
  UNION ALL
  SELECT jsonb_build_array('origin',provider,account,external_id)::text,payload
   FROM bookmarkdrop_api.origins o WHERE EXISTS(SELECT 1 FROM public.source_links l WHERE l.url=o.url)
 ) records WHERE key>p_cursor ORDER BY key LIMIT least(greatest(p_limit,0),500)
$$;
CREATE OR REPLACE FUNCTION bookmarkdrop_api.set_relation(p_a text,p_b text,p_kind text,p_remove boolean,p_suppressed boolean) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF coalesce(p_a !~ '^[a-f0-9]{64}$' OR p_b !~ '^[a-f0-9]{64}$' OR p_a>=p_b
    OR p_kind NOT IN ('related','similar') OR p_remove IS NULL OR p_suppressed IS NULL
    OR (p_kind='similar' AND NOT p_suppressed AND NOT p_remove),true) THEN
  RAISE EXCEPTION 'Invalid relationship' USING ERRCODE='22023';
 END IF;
 IF p_remove THEN DELETE FROM bookmarkdrop_api.relationships WHERE a=p_a AND b=p_b AND kind=p_kind;
 ELSE INSERT INTO bookmarkdrop_api.relationships VALUES(p_a,p_b,p_kind,p_suppressed)
  ON CONFLICT(a,b,kind) DO UPDATE SET suppressed=EXCLUDED.suppressed; END IF;
 RETURN true;
END $$;
CREATE OR REPLACE FUNCTION bookmarkdrop_api.read_relations() RETURNS SETOF bookmarkdrop_api.relationships
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$ SELECT * FROM bookmarkdrop_api.relationships $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA bookmarkdrop_api FROM PUBLIC;
GRANT USAGE ON SCHEMA bookmarkdrop_api TO bookmarkdrop_publisher;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA bookmarkdrop_api TO bookmarkdrop_publisher;
ALTER DEFAULT PRIVILEGES IN SCHEMA bookmarkdrop_api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
RESET ROLE;
DO $restore$
BEGIN
 EXECUTE format('GRANT bookmarkdrop_api_owner TO %I WITH INHERIT %s, SET %s',current_user,
   current_setting('bookmarkdrop.admin_inherit'),current_setting('bookmarkdrop.admin_set'));
END $restore$;
COMMIT;
-- Provision publisher credentials through a secure administrator workflow.
-- Rollback: disable bookmarkdrop_publisher login and revoke function execution.
-- Retain receipts/origins; published rows remain public until explicitly reviewed for removal.
