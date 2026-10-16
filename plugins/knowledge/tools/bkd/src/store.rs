use crate::model::{Record, hash};
use anyhow::{Result, ensure};
use postgres::{Client, Config};
use postgres_native_tls::MakeTlsConnector;
use serde_json::Value;
use std::{collections::BTreeMap, time::Duration};

pub struct Store {
    dsn: String,
    pub identity: String,
}
pub struct Snapshot {
    pub records: Vec<Record>,
    pub relations: Vec<crate::graph::Relation>,
}
impl Store {
    pub fn new(dsn: String) -> Result<Self> {
        let url = url::Url::parse(&dsn)
            .map_err(|_| anyhow::anyhow!("Expected a PostgreSQL connection URL"))?;
        ensure!(
            ["postgres", "postgresql"].contains(&url.scheme())
                && !url.username().is_empty()
                && url.host_str().is_some()
                && url.path().len() > 1,
            "Database URL requires host, database and user"
        );
        let identity = hash(serde_json::to_vec(&(
            url.host_str().unwrap().to_lowercase(),
            url.port().unwrap_or(5432),
            url.path(),
            url.username(),
        ))?);
        Ok(Self { dsn, identity })
    }
    fn connect(&self) -> Result<Client> {
        let mut config: Config = self
            .dsn
            .parse()
            .map_err(|_| anyhow::anyhow!("Invalid PostgreSQL connection URL"))?;
        config
            .ssl_mode(postgres::config::SslMode::Require)
            .connect_timeout(Duration::from_secs(10))
            .options("-c statement_timeout=15000 -c lock_timeout=5000");
        let tls = native_tls::TlsConnector::builder().build()?;
        config
            .connect(MakeTlsConnector::new(tls))
            .map_err(|_| anyhow::anyhow!("Verified TLS database connection failed"))
    }
    pub fn preview(&self, records: &[Record]) -> Result<BTreeMap<String, String>> {
        let mut db = self.connect()?;
        let mut states = BTreeMap::new();
        let urls: Vec<_> = records.iter().map(|r| r.url.clone()).collect();
        for batch in urls.chunks(100) {
            let rows = db
                .query(
                    "SELECT url,status FROM bookmarkdrop_api.preview_urls($1)",
                    &[&batch.to_vec()],
                )
                .map_err(|_| anyhow::anyhow!("BookmarkDrop preview function unavailable"))?;
            for row in rows {
                states.insert(row.get(0), row.get(1));
            }
        }
        Ok(states)
    }
    pub fn apply(&self, records: &[Record], operation: &str) -> Result<Value> {
        let mut db = self.connect()?;
        let payload = serde_json::to_value(records.iter().map(Record::remote).collect::<Vec<_>>())?;
        let row = db
            .query_one(
                "SELECT bookmarkdrop_api.apply_batch($1,$2)",
                &[&operation, &payload],
            )
            .map_err(|_| {
                anyhow::anyhow!(
                    "Publication was not confirmed; retry the destination-bound pending journal"
                )
            })?;
        Ok(row.get(0))
    }
    pub fn snapshot(&self, account: &str) -> Result<Snapshot> {
        let mut db = self.connect()?;
        let mut tx = db
            .build_transaction()
            .isolation_level(postgres::IsolationLevel::RepeatableRead)
            .read_only(true)
            .start()?;
        let rows = tx
            .query(
                "SELECT a,b,kind,suppressed FROM bookmarkdrop_api.read_relations()",
                &[],
            )
            .map_err(|_| anyhow::anyhow!("Neon relationship reader unavailable"))?;
        let mut relations = Vec::new();
        for row in rows {
            let r = crate::graph::Relation {
                a: row.get(0),
                b: row.get(1),
                kind: row.get(2),
                suppressed: row.get(3),
            };
            r.validate()?;
            relations.push(r);
        }
        let mut cursor = String::new();
        let mut records = Vec::new();
        loop {
            let rows = tx
                .query(
                    "SELECT key,payload FROM bookmarkdrop_api.read_records($1,$2)",
                    &[&cursor, &500i32],
                )
                .map_err(|_| anyhow::anyhow!("Neon bookmark reader unavailable"))?;
            let count = rows.len();
            for row in rows {
                let key: String = row.get(0);
                let mut payload: Value = row.get(1);
                let origin = if payload["provider"].is_string() {
                    Some(crate::model::Origin {
                        provider: payload["provider"].as_str().unwrap().into(),
                        account: payload["account"].as_str().unwrap_or("").into(),
                        external_id: payload["external_id"].as_str().unwrap_or("").into(),
                    })
                } else {
                    None
                };
                payload["provider"] = "neon".into();
                payload["account"] = account.into();
                payload["external_id"] = key.clone().into();
                payload["imported_origin"] = serde_json::to_value(origin)?;
                let mut r: Record = serde_json::from_value(payload)?;
                r.validate()?;
                records.push(r);
                cursor = key;
            }
            if count < 500 {
                break;
            }
            ensure!(
                records.len() <= 10000000,
                "Neon pagination budget exhausted"
            );
        }
        tx.commit()?;
        Ok(Snapshot { records, relations })
    }
    pub fn write_relation(
        &self,
        a: &str,
        b: &str,
        kind: &str,
        remove: bool,
        suppressed: bool,
    ) -> Result<()> {
        let (a, b) = if a < b { (a, b) } else { (b, a) };
        self.connect()?
            .query_one(
                "SELECT bookmarkdrop_api.set_relation($1,$2,$3,$4,$5)",
                &[&a, &b, &kind, &remove, &suppressed],
            )
            .map_err(|_| anyhow::anyhow!("Neon relationship write not confirmed"))?;
        Ok(())
    }
}
