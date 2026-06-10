"""
Verify whatweb plugin's domain-redirect detection emits the expected
recommendation when a target redirects to a different apex domain.
"""

from argparse import Namespace

from kast.plugins.whatweb_plugin import WhatWebPlugin

# Sample whatweb data with domain redirect
test_data = [
    {
        "target": "http://sanger.k12.ca.us",
        "http_status": 301,
        "request_config": {"headers": {"User-Agent": "WhatWeb/0.6.3"}},
        "plugins": {
            "Apache": {},
            "RedirectLocation": {"string": ["https://www.sanger.k12.ca.us/"]}
        }
    },
    {
        "target": "https://sanger.k12.ca.us",
        "http_status": 301,
        "request_config": {"headers": {"User-Agent": "WhatWeb/0.6.3"}},
        "plugins": {
            "Apache": {},
            "RedirectLocation": {"string": ["https://www.sanger.k12.ca.us/"]}
        }
    },
    {
        "target": "https://www.sanger.k12.ca.us/",
        "http_status": 200,
        "request_config": {"headers": {"User-Agent": "WhatWeb/0.6.3"}},
        "plugins": {
            "Apache": {},
            "WordPress": {}
        }
    }
]

def test_domain_redirect_detection():
    """Domain redirects should produce a recommendation naming both the
    redirect target and the source."""
    plugin = WhatWebPlugin(Namespace(verbose=True))
    recommendations = plugin._detect_domain_redirects(test_data)

    expected_domain = "www.sanger.k12.ca.us"
    expected_from = "sanger.k12.ca.us"

    assert any(
        expected_domain in rec and expected_from in rec
        for rec in recommendations
    ), f"No recommendation found for {expected_domain}. Got: {recommendations}"
