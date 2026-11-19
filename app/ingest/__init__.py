"""Ingest: the raw message store and the results every channel writes.

store.py keeps received mail (store_raw) and normalised runs (record_result);
the receivers of phase C4-I (SMTP, IMAP, HTTP, upload) call them. The contract
is in docs/ingest.md.
"""
