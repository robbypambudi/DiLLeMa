"""Source identity shared by retrieval packing and citation numbering."""

import hashlib
import json


def source_key(pair: list) -> str:
    meta = pair[2] if len(pair) > 2 else {}
    owner = str(meta.get("file_id") or meta.get("file_name") or "")
    if not owner:
        owner = hashlib.sha256(str(pair[1]).encode()).hexdigest()
    version = str(meta.get("document_version") or "")
    if meta.get("claim_id"):
        parent = ["claim", str(meta["claim_id"])]
    elif meta.get("parent_id"):
        parent = ["parent", str(meta["parent_id"])]
    elif meta.get("page") is not None:
        parent = ["page", meta["page"]]
    else:
        # Older Markdown/text indexes have no parent ID. Different sections
        # must not collapse just because both have page=None.
        parent = [
            "section",
            str(meta.get("section") or ""),
            hashlib.sha256(str(meta.get("page_text") or pair[1]).encode()).hexdigest(),
        ]
    return json.dumps([owner, version, parent], ensure_ascii=False)
