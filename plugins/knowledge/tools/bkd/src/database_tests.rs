use crate::{model::Record, model::hash};
use postgres::{Client, NoTls};
use serde_json::json;
#[test]
#[ignore = "Requires task-owned disposable localhost PostgreSQL: BKD_TEST_POSTGRES_DSN"]
fn reviewed_publication_database_contract() {
    let dsn = std::env::var("BKD_TEST_POSTGRES_DSN").expect("Set a disposable localhost DSN");
    let u = url::Url::parse(&dsn).unwrap();
    assert_eq!(u.host_str(), Some("127.0.0.1"));
    assert!(u.path().starts_with("/bkd_test_"));
    let mut db = Client::connect(&dsn, NoTls).unwrap();
    db.batch_execute("CREATE TABLE public.source_links(source text NOT NULL,url text NOT NULL,title text,notion_timestamp timestamptz,first_seen_at timestamptz NOT NULL DEFAULT now(),last_seen_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(source,url));
      CREATE TABLE public.source_link_tombstones(source text NOT NULL,url text NOT NULL,PRIMARY KEY(source,url));
      DO $role$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='bkd_test_reader') THEN CREATE ROLE bkd_test_reader NOLOGIN; END IF; END $role$;
      GRANT SELECT ON public.source_links TO bkd_test_reader;
      CREATE TABLE public.reading_feed_revisions(feed text PRIMARY KEY,revision bigint NOT NULL);
      INSERT INTO public.reading_feed_revisions VALUES('bookmarks',0);
      CREATE FUNCTION public.bump_reading_feed_revision() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $f$BEGIN UPDATE public.reading_feed_revisions SET revision=revision+1 WHERE feed=TG_ARGV[0]; RETURN NULL; END;$f$;
      CREATE TRIGGER reading_bookmarks_changed AFTER INSERT OR DELETE OR UPDATE OR TRUNCATE ON public.source_links FOR EACH STATEMENT EXECUTE FUNCTION public.bump_reading_feed_revision('bookmarks');").unwrap();
    db.batch_execute(include_str!("../database/bookmarkdrop.sql"))
        .unwrap();
    // Idempotent migration restores administrator membership options.
    db.batch_execute(include_str!("../database/bookmarkdrop.sql"))
        .unwrap();
    let mut record =
        Record::new("raindrop", "me", "1", "https://openai.com/index/research/").unwrap();
    record.title = "Reviewed research".into();
    record.note = "Nonpublic annotation".into();
    record.tags = vec!["research".into()];
    let payload = serde_json::to_value(vec![record.clone()]).unwrap();
    let operation = hash(b"one");
    db.batch_execute("SET ROLE bookmarkdrop_publisher").unwrap();
    let call = |db: &mut Client, payload: &serde_json::Value, op: &str| {
        db.query_one(
            "SELECT bookmarkdrop_api.apply_batch($1,$2)",
            &[&op, payload],
        )
    };
    let first: serde_json::Value = call(&mut db, &payload, &operation).unwrap().get(0);
    assert_eq!(first["new"], 1);
    let mut blog = record.clone();
    blog.url = "https://huyenchip.com".into();
    blog.external_id = "blog".into();
    blog.kind.clear();
    blog.validate().unwrap();
    assert_eq!(blog.kind, "blog");
    let result: serde_json::Value = call(&mut db, &json!([blog]), &hash("blog")).unwrap().get(0);
    assert_eq!(result["new"], 1);
    assert_eq!(
        call(&mut db, &payload, &operation)
            .unwrap()
            .get::<_, serde_json::Value>(0),
        first
    );
    assert!(
        db.query("SELECT * FROM bookmarkdrop_api.origins", &[])
            .is_err()
    );
    assert!(
        db.execute(
            "INSERT INTO public.source_links(source,url) VALUES('x','https://evil.org')",
            &[]
        )
        .is_err()
    );
    let mut changed = payload.clone();
    changed[0]["title"] = "Changed".into();
    assert!(call(&mut db, &changed, &operation).is_err());
    for field in [
        "schema", "provider", "url", "title", "account", "kind", "tags",
    ] {
        let mut bad = payload.clone();
        bad[0].as_object_mut().unwrap().remove(field);
        assert!(call(&mut db, &bad, &hash(field)).is_err());
    }
    db.batch_execute("RESET ROLE").unwrap();
    assert_eq!(
        db.query_one(
            "SELECT title FROM public.source_links WHERE url=$1",
            &[&record.url]
        )
        .unwrap()
        .get::<_, String>(0),
        "Reviewed research"
    );
    assert_eq!(
        db.query_one(
            "SELECT revision FROM public.reading_feed_revisions WHERE feed='bookmarks'",
            &[]
        )
        .unwrap()
        .get::<_, i64>(0),
        1
    );
    db.batch_execute("SET ROLE bkd_test_reader").unwrap();
    assert!(
        db.query("SELECT * FROM bookmarkdrop_api.read_records('',500)", &[])
            .is_err()
    );
    db.batch_execute("RESET ROLE").unwrap();
    // Other sources' public titles survive duplicate imports.
    record.external_id = "2".into();
    record.title = "Different".into();
    let dupe = serde_json::to_value(vec![record.clone()]).unwrap();
    db.batch_execute("SET ROLE bookmarkdrop_publisher").unwrap();
    assert_eq!(
        call(&mut db, &dupe, &hash("duplicate"))
            .unwrap()
            .get::<_, serde_json::Value>(0)["duplicate"],
        1
    );
    db.batch_execute("RESET ROLE").unwrap();
    assert_eq!(
        db.query_one("SELECT title FROM public.source_links", &[])
            .unwrap()
            .get::<_, String>(0),
        "Reviewed research"
    );
    // All-source tombstones prevent import resurrection, including new provider origins.
    db.execute(
        "DELETE FROM public.source_links WHERE url=$1",
        &[&record.url],
    )
    .unwrap();
    db.execute(
        "INSERT INTO public.source_link_tombstones VALUES('bookmarkdrop',$1)",
        &[&record.url],
    )
    .unwrap();
    db.batch_execute("SET ROLE bookmarkdrop_publisher").unwrap();
    let pruned: serde_json::Value = call(&mut db, &dupe, &hash("pruned")).unwrap().get(0);
    assert_eq!(pruned["pruned"], 1);
    assert_eq!(pruned["new"], 0);
    assert!(
        db.query("SELECT * FROM bookmarkdrop_api.read_records('',500)", &[])
            .unwrap()
            .is_empty()
    );
    db.batch_execute("RESET ROLE").unwrap();
    assert_eq!(
        db.query_one("SELECT count(*) FROM public.source_links", &[])
            .unwrap()
            .get::<_, i64>(0),
        0
    );
    assert_eq!(
        db.query_one(
            "SELECT payload->>'note' FROM bookmarkdrop_api.origins WHERE external_id='1'",
            &[]
        )
        .unwrap()
        .get::<_, String>(0),
        "Nonpublic annotation"
    );
    assert_eq!(json!(pruned["origins"]), 1);
}
