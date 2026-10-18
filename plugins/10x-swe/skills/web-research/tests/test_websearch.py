"""Request contracts and pipe/error behavior without credentials or external calls."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

SPEC = importlib.util.spec_from_file_location("websearch", Path(__file__).resolve().parents[1]/"scripts/websearch.py")
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


class SearchTests(unittest.TestCase):
    def invoke(self, args, responses=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        keys = {value: "fixture-key" for value in w.KEY.values()}
        with patch.dict(w.os.environ, keys, clear=True), patch.object(w, "post", side_effect=responses) as post:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    code = w.main(args)
                except SystemExit as error:
                    code = error.code
        return code, stdout.getvalue(), stderr.getvalue(), post

    def test_parallel_ga_limits_and_strict_freshness(self):
        with patch.object(w, "post", return_value={}) as post:
            w.parallel("question", "advanced", 7, ["docs.python.org"], True, "fixture-key")
        url, body, headers = post.call_args.args
        self.assertEqual(url, "https://api.parallel.ai/v1/search")
        self.assertNotIn("max_results", body)
        self.assertEqual(body["advanced_settings"], {
            "max_results": 7, "source_policy": {"include_domains": ["docs.python.org"]},
            "fetch_policy": {"max_age_seconds": 600, "disable_cache_fallback": True}})
        self.assertEqual(body["search_queries"], ["question"])

    def test_exa_deep_and_freshness(self):
        with patch.object(w, "post", return_value={}) as post:
            w.exa("question", "deep", 3, None, True, "fixture-key")
        self.assertEqual(post.call_args.args[1], {
            "query": "question", "type": "deep", "numResults": 3,
            "contents": {"highlights": True, "maxAgeHours": 0}})

    def test_publication_date_filters_are_native_and_keep_domain_policy(self):
        for provider in ['exa', 'parallel']:
            with self.subTest(provider=provider):
                code, _, _, post = self.invoke(['-p', provider, '--after-date', '2026-10-15',
                                                '-d', 'example.org', '--raw', 'question'], [{}])
                self.assertEqual(code, 0)
                body = post.call_args.args[1]
                if provider == 'exa':
                    self.assertEqual(body['startPublishedDate'], '2026-10-15T00:00:00Z')
                    self.assertEqual(body['includeDomains'], ['example.org'])
                else:
                    self.assertEqual(body['advanced_settings']['source_policy'],
                                     {'include_domains': ['example.org'], 'after_date': '2026-10-15'})

    def test_invalid_or_unsupported_publication_dates_never_request(self):
        for provider, date in [('exa', '2026-02-30'), ('parallel', '20261015'),
                               ('exa', '2026-1-5'), ('parallel', '2026-10-15T00:00:00Z'),
                               ('exa', ''), ('perplexity', '2026-10-15')]:
            code, _, _, post = self.invoke(['-p', provider, '--after-date', date, 'question'])
            self.assertEqual(code, 2)
            post.assert_not_called()

    def test_native_response_retains_evidence_and_usage(self):
        response = {"requestId": "fixture-id", "results": [{"url": "https://example.com", "highlights": ["source"]}],
                    "output": {"content": "claim", "grounding": [{"field": "content", "citations": []}]},
                    "warnings": ["partial"], "costDollars": {"total": 0.01}}
        code, stdout, _, post = self.invoke(["-p", "exa", "--raw", "question"], [response])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["exa"]["response"], response)
        post.assert_called_once()

    def test_compact_json_contract(self):
        code, stdout, _, _ = self.invoke(["-p", "parallel", "--json", "question"],
            [{"results": [{"url": "https://example.com", "title": "Example", "excerpts": ["one", "two"]}]}])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout), {"parallel": {"error": None, "results": [
            {"url": "https://example.com", "title": "Example", "excerpt": "one\ntwo"}]}})

    def test_invalid_inputs_never_request(self):
        for args in [["-p", "", "q"], ["-p", "exa,exa", "q"], ["-p", "unknown", "q"],
                     ["-p", "exa,parallel", "-m", "fast", "q"], ["-p", "parallel", "-m", "deep", "q"],
                     ["-n", "0", "q"], ["-n", "21", "q"], ["--chars", "0", "q"],
                     ["--fresh", "q"], ["-d", "", "q"], ["   "]]:
            with self.subTest(args=args):
                code, _, _, post = self.invoke(args)
                self.assertEqual(code, 2)
                post.assert_not_called()

    def test_missing_keys_do_not_discover_credentials(self):
        with patch.dict(w.os.environ, {}, clear=True), patch.object(w, "post") as post:
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as error:
                    w.main(["-p", "exa", "question"])
            self.assertEqual(error.exception.code, 2)
            self.assertIn("EXA_API_KEY", stderr.getvalue())
            self.assertNotIn("doppler", stderr.getvalue())
            post.assert_not_called()

    def test_partial_fanout_exits_nonzero_with_other_results(self):
        def respond(url, *_):
            if "exa.ai" in url:
                raise RuntimeError("HTTP 429; rate limited")
            return {"search_id": "fixture", "results": []}
        code, stdout, _, post = self.invoke(["-p", "exa,parallel", "--raw", "q"], respond)
        self.assertEqual(code, 2)
        result = json.loads(stdout)
        self.assertIsNone(result["exa"]["response"])
        self.assertEqual(result["parallel"]["response"]["search_id"], "fixture")
        self.assertEqual(post.call_count, 2)

    def test_invalid_response_is_not_success(self):
        code, stdout, _, _ = self.invoke(["-p", "exa", "--raw", "q"], [{"results": [{"title": "no URL"}]}])
        self.assertEqual(code, 2)
        self.assertIn("Invalid provider response", json.loads(stdout)["exa"]["error"])

    def test_errors_do_not_echo_provider_body(self):
        error = urllib.error.HTTPError("https://api.exa.ai/search", 403, "secret", {}, io.BytesIO(b"fixture-secret"))
        with patch.object(w.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(RuntimeError) as caught:
                w.post("https://api.exa.ai/search", {}, {"x-api-key": "fixture-secret"})
        self.assertIn("HTTP 403", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_network_timeout_is_visible_without_retry(self):
        for error in [TimeoutError(), urllib.error.URLError("fixture-secret"), ValueError("bad JSON")]:
            with self.subTest(error=type(error).__name__), patch.object(w.urllib.request, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(RuntimeError) as caught:
                    w.post("https://api.exa.ai/search", {}, {})
                self.assertNotIn("fixture-secret", str(caught.exception))
                opener.return_value.open.assert_called_once()

    def test_redirect_does_not_forward_credentials(self):
        request = urllib.request.Request("https://api.exa.ai/search", headers={"x-api-key": "fixture-secret"})
        for code in [301, 302, 303, 307, 308]:
            self.assertIsNone(w.NoRedirect().redirect_request(request, None, code, "", {}, "https://other.example"))

    def test_human_output_flags_warnings_and_truncation(self):
        code, stdout, _, _ = self.invoke(["-p", "exa", "--chars", "3", "q"],
            [{"results": [{"url": "https://example.com", "highlights": ["long text"]}], "warnings": ["partial"]}])
        self.assertEqual(code, 0)
        self.assertIn("lon…", stdout)
        self.assertIn("inspect --raw", stdout)


if __name__ == "__main__":
    unittest.main()
