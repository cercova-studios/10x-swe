-- Administrator rollback: stop future publisher access; retain data and receipts.
-- An already-running publication transaction may still finish.
BEGIN;
ALTER ROLE bookmarkdrop_publisher NOLOGIN;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA bookmarkdrop_api FROM bookmarkdrop_publisher;
REVOKE USAGE ON SCHEMA bookmarkdrop_api FROM bookmarkdrop_publisher;
COMMIT;
