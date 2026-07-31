"""One registrable-domain normalizer, shared.

`_registered_domain` existed twice — `src/audit/checks/links.py` and
`src/audit/offsite/tools.py` — with byte-identical bodies and separate
`TLDExtract` instances. Two writers of one rule is how the rule drifts, and this
one is about to acquire a third caller: the fact-sheet generator keys a
business's identity on it (`docs/factsheet-autogen-plan.md` §12.4), so a
disagreement between copies would mean two callers deciding differently whether
two leads are the same business.

`suffix_list_urls=()` is deliberate and load-bearing: it pins tldextract to its
bundled public-suffix snapshot instead of fetching one at import time. A network
call on import would make an offline/sandboxed run fail in a module that has no
business needing the network.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import tldextract

__all__ = ["registered_domain"]

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())


def registered_domain(url_or_host: str) -> str:
    """The registrable domain of a URL or bare host, lowercased.

    ``https://www.example.co.uk/a`` and ``EXAMPLE.CO.UK`` both give
    ``example.co.uk``. Input that is not parseable as a URL is treated as a
    bare host, which is what every existing caller relied on.
    """
    host = urlsplit(url_or_host).hostname or url_or_host
    return _EXTRACT(host).top_domain_under_public_suffix.lower()
