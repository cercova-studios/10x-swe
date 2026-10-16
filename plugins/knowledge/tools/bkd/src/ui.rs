use crate::{graph, importer, index, knowledge, model, render, search, state, store::Store};
use anyhow::{Result, ensure};
use serde_json::{Value, json};
use std::{collections::BTreeMap, io::Read, path::Path};
use tiny_http::{Header, Response, Server, StatusCode};

const INDEX: &str = include_str!("../web/index.html");
const JS: &str = include_str!("../web/app.js");
const CSS: &str = include_str!("../web/style.css");
fn random() -> Result<String> {
    let mut b = [0u8; 32];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut b)?;
    Ok(model::hash(b))
}
fn header(name: &str, value: &str) -> Header {
    Header::from_bytes(name, value).unwrap()
}
pub fn run(
    home: &Path,
    open: bool,
    config: &knowledge::Config,
    include_knowledge: bool,
) -> Result<()> {
    let server = Server::http("127.0.0.1:0")
        .map_err(|_| anyhow::anyhow!("Cannot bind local browser server"))?;
    let address = server
        .server_addr()
        .to_ip()
        .ok_or_else(|| anyhow::anyhow!("Missing loopback address"))?;
    let host = address.to_string();
    let origin = format!("http://{host}");
    let mut launch = Some(random()?);
    let session = random()?;
    let url = format!("{origin}/start?token={}", launch.as_ref().unwrap());
    eprintln!("BookmarkDrop browser: {url}\nCtrl+C stops the local server.");
    if open {
        std::process::Command::new("open").arg(&url).spawn()?;
    }
    for mut request in server.incoming_requests() {
        let mut headers = BTreeMap::new();
        let mut duplicate = false;
        for h in request.headers() {
            let key = h.field.as_str().as_str().to_ascii_lowercase();
            if headers.insert(key, h.value.as_str().to_owned()).is_some() {
                duplicate = true;
            }
        }
        let method = request.method().as_str().to_string();
        let mut code = 200;
        let mut cookie = false;
        let mut location = None;
        let mut kind = "application/json";
        let response = (|| -> Result<Vec<u8>> {
            ensure!(
                !duplicate && headers.get("host") == Some(&host),
                "Invalid request host/headers"
            );
            ensure!(
                ["GET", "POST"].contains(&method.as_str()),
                "Unsupported method"
            );
            if let Some(o) = headers.get("origin") {
                ensure!(o == &origin, "Invalid request origin");
            }
            let u = url::Url::parse(&format!("{origin}{}", request.url()))?;
            if method == "GET" && u.path() == "/start" {
                let token = u
                    .query_pairs()
                    .find(|(k, _)| k == "token")
                    .map(|(_, v)| v.into_owned());
                ensure!(launch.is_some() && token == launch, "Expired launch token");
                launch = None;
                cookie = true;
                location = Some("/");
                code = 303;
                return Ok(Vec::new());
            }
            ensure!(
                headers.get("cookie").is_some_and(|c| c
                    .split(';')
                    .any(|p| p.trim() == format!("bkd_session={session}"))),
                "Browser session required"
            );
            if method == "POST" {
                ensure!(
                    headers.get("origin") == Some(&origin),
                    "POST requires same origin"
                );
                ensure!(
                    headers
                        .get("content-type")
                        .is_some_and(|v| v.split(';').next() == Some("application/json")),
                    "Expected JSON"
                );
                let mut bytes = Vec::new();
                request.as_reader().take(16385).read_to_end(&mut bytes)?;
                ensure!(bytes.len() <= 16384, "Save request exceeds 16 KiB");
                ensure!(
                    ["/api/save", "/api/reader"].contains(&u.path()),
                    "Unknown POST route"
                );
                let payload: Value = serde_json::from_slice(&bytes)?;
                if u.path() == "/api/reader" {
                    ensure!(
                        payload
                            .as_object()
                            .is_some_and(|o| o.len() == 1 && o.contains_key("url")),
                        "Reader requires one URL"
                    );
                    let url = payload["url"]
                        .as_str()
                        .ok_or_else(|| anyhow::anyhow!("Missing reader URL"))?;
                    return match crate::reader::fetch(url) {
                        Ok(value) => Ok(serde_json::to_vec(&value)?),
                        Err(error) => {
                            code = 400;
                            Ok(serde_json::to_vec(
                                &json!({"error":model::clean(&error.to_string())}),
                            )?)
                        }
                    };
                }
                ensure!(
                    payload.as_object().is_some_and(|o| o.keys().all(|k| [
                        "url",
                        "title",
                        "kind",
                        "confirm_public"
                    ]
                    .contains(&k.as_str())))
                        && payload.get("title").is_none_or(|v| v.is_string())
                        && payload.get("kind").is_none_or(|v| v.is_string()),
                    "Invalid save fields"
                );
                ensure!(
                    payload["confirm_public"] == true,
                    "Explicit public-save confirmation required"
                );
                let url = payload["url"]
                    .as_str()
                    .ok_or_else(|| anyhow::anyhow!("Missing URL"))?;
                let mut r = model::Record::new(
                    "manual",
                    &state::account(home, "neon")?,
                    &model::hash(url),
                    url,
                )?;
                r.title = payload["title"].as_str().unwrap_or("").into();
                if let Some(k) = payload["kind"].as_str().filter(|k| !k.is_empty()) {
                    r.kind = k.into();
                    r.kind_source = "manual".into();
                }
                r.validate()?;
                let store = Store::new(state::credential(home, "neon")?)?;
                let mut plan = importer::preview(
                    index::merge(vec![r], &[], &[], None),
                    json!({"action":"browser-public-save"}),
                    &store,
                    json!({}),
                )?;
                plan.candidates[0].selected = true;
                let result = importer::apply(home, &plan, &plan.id()?, &store)?;
                let totals = result["batches"]
                    .as_array()
                    .ok_or_else(|| anyhow::anyhow!("Invalid publication receipt"))?;
                ensure!(
                    totals.iter().all(|b| b["pruned"].as_u64() == Some(0)),
                    "URL was archived before commit; publication blocked"
                );
                let saved = totals
                    .iter()
                    .any(|b| b["new"].as_u64().is_some_and(|n| n > 0));
                return Ok(serde_json::to_vec(
                    &json!({"status":if saved{"saved"}else{"already_saved"},"result":result}),
                )?);
            }
            match u.path() {
                "/" => {
                    kind = "text/html; charset=utf-8";
                    return Ok(INDEX.as_bytes().to_vec());
                }
                "/app.js" => {
                    kind = "text/javascript; charset=utf-8";
                    return Ok(JS.as_bytes().to_vec());
                }
                "/style.css" => {
                    kind = "text/css; charset=utf-8";
                    return Ok(CSS.as_bytes().to_vec());
                }
                _ => {}
            }
            let params: BTreeMap<_, _> = u
                .query_pairs()
                .map(|(k, v)| (k.into_owned(), v.into_owned()))
                .collect();
            let mut filter = search::Filter {
                sources: params
                    .get("source")
                    .map(|s| vec![s.clone()])
                    .unwrap_or_default(),
                kinds: params
                    .get("kind")
                    .map(|k| vec![k.clone()])
                    .unwrap_or_default(),
                domain: params.get("domain").cloned(),
            };
            filter.validate()?;
            let mut db = state::db(home)?;
            let combined = config.enabled() && params.get("knowledge").is_some_and(|v| v == "1");
            let value = match u.path() {
                "/api/bookmarks" => {
                    let mut books = filter.books(&db)?;
                    books.sort_by_cached_key(|b| (b.title.to_lowercase(), b.url.clone()));
                    let offset = params
                        .get("offset")
                        .map(|s| s.parse::<usize>())
                        .transpose()?
                        .unwrap_or(0);
                    ensure!(offset <= books.len(), "Invalid bookmark offset");
                    let results: Vec<_> = books.iter().skip(offset).take(100).map(|b| {
                        let excerpt = b.origins.iter().map(|r| format!("{}\n\n{}", r.excerpt, r.note)).collect::<Vec<_>>().join("\n\n");
                        json!({"id":b.id,"title":b.title,"url":b.url,"kind":b.kind,"sources":b.sources(),"excerpt_html":render::html(&excerpt)})
                    }).collect();
                    json!({"results":results,"total":books.len(),"offset":offset})
                }
                "/api/status" => {
                    json!({"bookmarks":search::Filter::default().books(&db)?.len(),"pending_batches":std::fs::read_dir(home.join("pending")).map(|i|i.count()).unwrap_or(0),"knowledge_default":include_knowledge})
                }
                "/api/graph" => {
                    let tx = db.transaction()?;
                    let books = filter.books(&tx)?;
                    let mut graph = graph::derive(&tx, &books, true)?;
                    tx.rollback()?;
                    if combined {
                        graph = knowledge::Snapshot::load(home, config)?.enrich(home, graph)?;
                    }
                    serde_json::to_value(graph)?
                }
                "/api/inspect" => {
                    let id = params
                        .get("id")
                        .ok_or_else(|| anyhow::anyhow!("Missing entity ID"))?;
                    let snapshot = knowledge::Snapshot::load(home, config)?;
                    snapshot.inspect(&mut db, home, &filter, id)?
                }
                "/api/search" => {
                    let query = params
                        .get("q")
                        .ok_or_else(|| anyhow::anyhow!("Missing query"))?;
                    let snapshot = if combined {
                        Some(knowledge::Snapshot::load(home, config)?)
                    } else {
                        None
                    };
                    let mut external = snapshot
                        .as_ref()
                        .map(|s| knowledge::search(s, config, query, 20))
                        .transpose()?;
                    let result = search::search(&mut db, query, &filter, 20, true, true)?;
                    if let Some(ref mut external) = external {
                        let g = snapshot.as_ref().unwrap().enrich(
                            home,
                            graph::bookmarks(
                                result.generation,
                                result.hits.iter().map(|h| &h.book),
                            ),
                        )?;
                        let ids = result.hits.iter().map(|h| h.book.id.clone()).collect();
                        knowledge::contextualize(external, &g, &ids, 20);
                    }
                    let results=result.hits.into_iter().map(|h|{
                        let sources=h.book.sources();let excerpt=h.book.origins.iter().map(|r|format!("{}\n\n{}",r.excerpt,r.note)).collect::<Vec<_>>().join("\n\n");
                        json!({"id":h.book.id,"title":h.book.title,"url":h.book.url,"kind":h.book.kind,"rank":h.rank,"sources":sources,"excerpt_html":render::html(&excerpt),"passage":h.passage,"matched_by":h.matched_by,"graph_path":h.graph_path.map(|edges|json!({"edges":edges}))})
                    }).collect::<Vec<_>>();
                    let mut q = db.prepare("SELECT provider FROM sources ORDER BY provider")?;
                    let coverage = q
                        .query_map([], |r| Ok(json!({"provider":r.get::<_,String>(0)?})))?
                        .collect::<std::result::Result<Vec<_>, _>>()?;
                    drop(q);
                    let mut response = json!({"results":results,"total":result.total,"generation":result.generation,"coverage":coverage,"strategy":result.strategy,"passage_index":result.passage_index});
                    if let Some(ref mut external) = external {
                        response["connections"] = external["connections"].take();
                        response["linked_context"] = external["linked_context"].take();
                        response["insights"] = external["insights"].take();
                        response["skills"] = external["skills"].take();
                        response["sessions"] = external["sessions"].take();
                        response["knowledge"] = external["knowledge"].take();
                    }
                    response
                }
                _ => {
                    code = 404;
                    json!({"error":"Unknown route"})
                }
            };
            Ok(serde_json::to_vec(&value)?)
        })();
        let body = match response {
            Ok(b) => b,
            Err(_) => {
                code = 400;
                br#"{"error":"Request rejected or operation not confirmed; inspect bkd doctor and pending journals."}"#.to_vec()
            }
        };
        let mut response=Response::from_data(body).with_status_code(StatusCode(code))
            .with_header(header("Content-Type",kind)).with_header(header("Cache-Control","no-store"))
            .with_header(header("Referrer-Policy","no-referrer")).with_header(header("X-Content-Type-Options","nosniff"))
            .with_header(header("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src https: http:; img-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"));
        if cookie {
            response.add_header(header(
                "Set-Cookie",
                &format!("bkd_session={session}; HttpOnly; SameSite=Strict; Path=/"),
            ));
        }
        if let Some(path) = location {
            response.add_header(header("Location", path));
        }
        let _ = request.respond(response);
    }
    Ok(())
}
