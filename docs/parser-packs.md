# Built-in parser packs

Checkorca-CE ships eight parser packs in `app/parsers/packs`: the fallback `generic-keywords` (C5-I) and seven vendor packs (C6-I). The pack format, the engine and the claim are in [parsers.md](parsers.md); this page lists the packs, what each reads, how far each is verified and how an MSP can help verify one. Source: dev-work-plan rev 35, section C6.

The worker writes the built-in packs into the `parser_pack` table on its next tick after a deploy (C5-B), and the Parsers screen (C5-F) lists them with their status badge. A built-in pack can be disabled or exported, not edited; to change one, export it, change it and import it under a new id as a custom pack.

## Packs

| Pack | Vendor | Version | Status | Mail it reads | Job name | Documentation the pack follows |
| --- | --- | --- | --- | --- | --- | --- |
| `veeam-br` | Veeam Backup & Replication | 1 | unverified-synthetic | job session report, one per job run (HTML) | the job | <https://helpcenter.veeam.com/docs/backup/vsphere/backup_job_advanced_notify_vm.html> |
| `synology-abb` | Synology Active Backup for Business | 1 | unverified-synthetic | DSM notification of a backup task (plain text) | the task | <https://kb.synology.com/en-global/DSM/help/ActiveBackup/activebackup_business_notification> |
| `synology-hyperbackup` | Synology Hyper Backup | 1 | unverified-synthetic | DSM notification of a backup task (plain text) | the task | <https://kb.synology.com/en-global/DSM/help/HyperBackup/data_backup> |
| `acronis-cp-legacy` | Acronis Cyber Protect (on-premises 15 and 16, Cyber Backup 12.5) | 1 | unverified-synthetic | backup alert of the management server, one per device | the device | <https://www.acronis.com/en-us/support/documentation/CyberProtect_16/> |
| `acronis-cp-cloud` | Acronis Cyber Protect Cloud | 1 | unverified-synthetic | backup alert per workload, and the daily recap (a digest, split per workload) | the workload | <https://www.acronis.com/en-us/support/documentation/CyberProtectionService/> |
| `nable-cove` | N-able Cove Data Protection | 1 | unverified-synthetic | session report per device, and the daily summary (a digest, split per device) | the device | <https://documentation.n-able.com/covedp/userguide/documentation/Content/home.htm> |
| `msp360` | MSP360 Backup (formerly CloudBerry) | 1 | unverified-synthetic | backup plan notification, one per plan run | the plan | <https://help.msp360.com/> |
| `generic-keywords` | Generic | 3 | unverified-synthetic | any backup or job alert no other pack claims | the subject | (none: keywords) |

**unverified-synthetic** means the pack was written from the vendor's public documentation and tested against synthetic fixtures only; no real mail of that vendor has been checked yet. **verified** means it was checked against permitted, redacted real mails of at least 3 result classes (the loader refuses `verified` without `docs_url` and fixtures of 3 classes). The documentation links are the vendor entry points each pack follows; a maintainer opens them again when the pack is verified. No pack is verified yet: wording that differs from the documentation (a localised DSM, a customised subject template, a newer product version) can leave a mail to `generic-keywords` or to Unmatched, never to a wrong success.

Not in Checkorca-CE: no Datto pack and no Veeam Backup for Microsoft 365 pack.

## What every vendor pack does

- **Claim.** Every vendor pack needs the product name in the body (`match.all`) and at least one more of its own conditions: the subject or a row of its report (`match.any`). Its own mail scores 2 or 3; `generic-keywords` scores at most 1, and the other vendor packs 0 (the product names differ: "Acronis Cyber Protect 16" is legacy, "Acronis Cyber Protect Cloud" is cloud). A tie goes to Unmatched (C5-I).
- **Failure first.** Status rules try a failure first (subject, then body), then a warning, then a running job, then success. A failure reported in the body is never read as success, whatever the subject says; "partially completed", "succeeded with warnings" and "CompletedWithErrors" are warnings, never success.
- **Changed subject.** The claim holds without the subject (product name plus a body row), so a customised or forwarded subject falls back to the body rules. A mail with no result words gives `unknown`, and unknown never becomes success.
- **Digests.** `acronis-cp-cloud` splits on `Workload:` and `nable-cove` on `Device:`; a single alert is one record, a recap one result per workload or device. The customer of an Acronis recap is read once from the whole body; Cove names the customer in every block.
- **Client hint.** The customer, tenant or company row where the vendor sends one (Acronis Cyber Protect Cloud, Cove, MSP360). Veeam, Synology and Acronis on-premises mails carry no client: bind those jobs by name, or give the client an alias (Unmatched, assign).
- **Status words** each pack maps:

| Pack | failed | warning | started | success |
| --- | --- | --- | --- | --- |
| `veeam-br` | `[Failed]`, `[Error]`; result row Failed; Error count above 0 | `[Warning]`; result row Warning; Warning count above 0 | | `[Success]`; result row Success |
| `synology-abb`, `synology-hyperbackup` | failed, cancelled, aborted; a negated completion (could not be completed, was not completed, has not succeeded) | partially completed | | has, was or is completed or succeeded |
| `acronis-cp-legacy`, `acronis-cp-cloud` | Failed, Error, Cancelled, Not started (cloud also Not run, Missed) | Succeeded with warnings (cloud also Warning) | Running, In progress | Succeeded (cloud also OK) |
| `nable-cove` | Failed, Aborted, OverQuota, Interrupted, NotStarted | CompletedWithErrors | InProcess | Completed |
| `msp360` | Failed, Failure, Error, Cancelled, Interrupted; subject Not successful, Unsuccessful | Warning, Completed with warnings or errors | Running, In progress | Success, Completed |

Fixtures are in `app/parsers/packs/fixtures/<pack id>/`: at least one success, one warning and one failed mail per vendor, and a digest for Acronis Cyber Protect Cloud and Cove. All are synthetic, written from the documentation, with R-11 names only (example.com, example.net, .test, 192.0.2.0/24, fictional companies). `tests/parsers/test_fixtures.py` checks every fixture against its expected results; `tests/parsers/test_vendor_packs.py` checks that each vendor's mail is claimed by its own pack only, that a changed subject falls back to the body rules, that neither a failed nor a warning body is hidden by a success subject, that a negated completion or a status word in a task name is never success, and that a mail without result words stays unknown.

## Sending a sample so a pack can become verified

A pack becomes `verified` from real mails its vendor sent, cleaned and permitted. If a pack misreads your mail, or you want to help verify one, open an issue in the Checkorca-CE repository with the template below and attach the redacted `.eml`. The repository is public: send only a mail you have redacted as described, never the original.

1. Save the original as `.eml` with all headers (in most mail clients: "Save as" or "Show original", then download).
2. Redact in a text editor, keeping the structure, the labels, the result words and the time formats exactly as they are:
   - company, client and person names to fictional ones (`Fictional Dental Clinic`);
   - mail addresses and domains to `example.com`, `example.net` or a `.test` name;
   - host, device, job and plan names to neutral ones (`SRV-FILES-01`, `Nightly VM Backup`);
   - IPv4 addresses to `192.0.2.x`, IPv6 to `2001:db8::`;
   - remove links with tokens or tracking, licence keys, serial numbers, account or tenant ids, and any attachment.
3. Check that nothing of a client is left: search the file for the real names once more.
4. Open the issue:

```text
Title: Parser sample: <pack id or vendor>

Vendor and product: (for example Veeam Backup & Replication)
Product version: (for example 12.3)
Kind of mail: (job report / alert / daily summary)
Result the mail reports: (success / warning / failed / running)
Subject template: (default or customised; the template if customised)
Language of the mail: (for example English)
What Checkorca-CE showed: (pack that claimed it, the status, or Unmatched)

[ ] I removed client names, addresses, hosts, IPs, tokens and links as in docs/parser-packs.md.
[ ] I may share this mail, and I agree that it is published in the
    repository as a test fixture under the MIT licence.

Attachment: <file>.eml
```

A maintainer adds the mail as a fixture with `origin: real`, adjusts the pack if needed and raises its `version`. Once real fixtures of at least 3 result classes pass, the pack's status becomes `verified`.

## Trademarks

Veeam, Veeam Backup & Replication, Synology, Active Backup for Business, Hyper Backup, DiskStation, Acronis, Acronis Cyber Protect, N-able, Cove Data Protection, MSP360 and CloudBerry are trademarks of their respective owners. They are used here only to describe compatibility. Checkorca-CE is not affiliated with, endorsed by or sponsored by them.
