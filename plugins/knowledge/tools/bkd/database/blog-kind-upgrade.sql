-- Add one publisher kind. Abort if the reviewed function has changed.
-- This changes no rows, credentials, grants retained after completion, or public feed.
DO $upgrade$
DECLARE
 definition text;
 old_inherit boolean;
 old_set boolean;
 old_kinds constant text := '(''article'',''video'',''paper'',''documentation'',''book'',''other'')';
 new_kinds constant text := '(''blog'',''article'',''video'',''paper'',''documentation'',''book'',''other'')';
BEGIN
 SELECT pg_get_functiondef('bookmarkdrop_api.apply_batch(text,jsonb)'::regprocedure) INTO definition;
 IF md5(definition)<>'019a311cafbdc492c6732dc9debb256b'
    OR (length(definition)-length(replace(definition,old_kinds,'')))/length(old_kinds)<>1 THEN
  RAISE EXCEPTION 'Publisher changed; review again before upgrading';
 END IF;
 SELECT inherit_option,set_option INTO old_inherit,old_set FROM pg_auth_members
 WHERE roleid='bookmarkdrop_api_owner'::regrole AND member=current_user::regrole
 AND grantor=current_user::regrole;
 IF NOT FOUND THEN RAISE EXCEPTION 'Expected existing administrator membership'; END IF;
 EXECUTE format('GRANT bookmarkdrop_api_owner TO %I WITH INHERIT TRUE, SET TRUE',current_user);
 EXECUTE replace(definition,old_kinds,new_kinds);
 EXECUTE format('GRANT bookmarkdrop_api_owner TO %I WITH INHERIT %s, SET %s',current_user,
  CASE WHEN old_inherit THEN 'TRUE' ELSE 'FALSE' END,
  CASE WHEN old_set THEN 'TRUE' ELSE 'FALSE' END);
END $upgrade$;
