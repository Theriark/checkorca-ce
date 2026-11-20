# Design direction

Checkorca-CE is an operations tool a lead technician opens every morning with coffee in hand. The question it answers is one line long: which clients are verified, failed or silent. The design serves that question: numbers first, a calm page, one signature visual that makes silence visible, and status that is always icon plus word plus colour.

Written by the Frontend Developer in phase C2 (THE-1986). Sources: rnd-report-2 section 4, the Brand chapter of the dev-work-plan, the brand guide (`/Theriark/Checkorca/Brand/checkorca-brand-guide.pdf`), `references/ui-standard.md`. The implementation lives in `frontend/src` (`styles/tokens.css`, `components/ui`, `charts`, `ribbon`, `shell`, `routes`).

## 1. Signature visual: the Night Ribbon

The night, on one line. A horizontal overnight timeline from about 18:00 to 12:00 the next day, one per client:

- every expected run is a **ring** at its planned time;
- a received result **fills** the ring: green verified, amber warning, red failed;
- a run that never reported stays a **hollow ring** that slowly breathes and is joined to its deadline by a **dotted gap line**. A hollow ring *is* silence; the key feature of the product is visible at a glance;
- a vertical **morning line** in signal red marks the digest time.

Phase C2 ships the ribbon as a static mark (`ribbon/NightRibbonMark.tsx`): on the sign-in and first-run panel as the hero, in empty states and on the 404 page in a quiet variant. Phase C8 builds the live ribbon from `dashboard/ribbon` (SVG, problems-only filter, per-client chips at 390 px, pulse stops under reduced motion). The job detail reuses it over 30 days; EE prints it in the PDF report. 2D only: a 3D scene adds nothing to an operations tool.

Rules for the ribbon: the pulse is opacity and scale only, 2.4 s, and stops under `prefers-reduced-motion`; rings never rely on colour alone (hollow versus filled is a shape difference, and the list beside the ribbon carries the words); the morning line is the only red line on the page.

## 2. Palette roles

From the brand guide. Tokens in `styles/tokens.css`; components never use raw hex.

| Role | Hex | Used for | Never for |
| --- | --- | --- | --- |
| Signal red | `#D0202A` | logo, failed and missed, critical counts, destructive confirm fills, the morning line | primary buttons, links, headings |
| Ink | `#121417` | text and primary buttons on light; the dark background | |
| Steel | `#9FB3C8` | borders and secondary text on dark, gridlines, paused | text on light (4.5:1 fails) |
| Off-white | `#F7F7F5` | light background; text and primary buttons on dark; the tile behind the mark on dark | |

Surfaces: light pages sit on off-white with white cards and `#DADFE5` borders; dark pages sit on ink with `#1B1F24` cards, `#22272E` raised surfaces and `#2C333B` borders. Shadows are soft and rare (cards, menus, dialogs).

**Status tokens** (light / dark): success `#1E7B4F` / `#3FB37A`; warning `#9A5B00` / `#E0A030`; danger `#D0202A` / `#F4585F` for text with `#D0202A` fills; muted `#5B6B7C` / `#9FB3C8`. Every status text passes 4.5:1 on the page and on a card in its theme (checked for `#F7F7F5`, `#FFFFFF`, `#EEEEEA`, `#121417`, `#1B1F24`, `#22272E`). One deviation from the guide, recorded here: dark danger text is `#F4585F` instead of `#F0444C`, because the guide's value reads 4.4:1 on a raised dark surface, below the guide's own contrast rule; fills keep `#D0202A`.

**Theme.** Light and dark. The app follows the system until the user picks one (toggle in the header, the user menu and the phone sheet); the choice is stored and written as `data-theme` on `<html>`, and the CSS also follows `prefers-color-scheme` when no choice exists, so there is no flash.

## 3. Type

Inter (variable, 400 to 700) for everything; JetBrains Mono (variable, 400 and 600) for cron expressions, logs, raw mail and request ids. Both self-hosted through `@fontsource-variable` (no CDN, legal R-10; OFL-1.1 recorded in `licence-exceptions.toml`, legal R-5).

Scale: 12, 14, 16, 20, 24, 32 px. Headings 600, never red. Tables and times use tabular figures (`.tabular`). Body 16 px at 1.5; UI chrome 14 px; captions and column headers 12 px uppercase with 0.06 em tracking. Voice: short, numbers first, no exclamation marks.

## 4. Space, shape, motion

A 4 px grid (`--space-1` to `--space-16`). Radii 6, 10, 14 px (controls, cards, dialogs) and a pill for badges. Controls are 40 px high (32 px small). Content is at most 1280 px wide.

Motion is functional and short: 120 ms for colour, 180 ms for overlays, 320 ms for the coverage ring. Skeletons shimmer; nothing bounces. All animation collapses under `prefers-reduced-motion`.

Focus is always visible: a 2 px outline in the text colour with a soft halo (`:focus-visible`), the same on every control, link and row.

## 5. Components and their states

`components/ui` is the only place controls are styled; routes compose them.

- **Button** primary (ink on light, off-white on dark), secondary, ghost, danger (red fill, destructive confirms only); loading keeps the width and sets `aria-busy`; icon-only buttons keep their label as the accessible name.
- **Input** and **Select** with label, hint and error (announced, `aria-invalid`, described by id); mono inputs for cron and tokens.
- **Dialog** (Radix) labelled by its title, with one sentence of description, focus on the first control, Escape and overlay close; the danger tone adds a red band.
- **Toast** (Radix) bottom right (above the bottom bar at phone width), with a word and an icon per tone: Done, Failed, Note.
- **DataTable**: sticky header, click-to-sort with `aria-sort`, density switch, saved views (sort plus density under a name, per table, in localStorage), loading rows, a designed empty state and an error state with retry and request id.
- **SeverityBadge**: icon plus word plus colour for Verified, Warning, Failed, Overdue, Missed, Silent, Unmatched, Paused, Maintenance. Status is never colour alone.
- **StatCard**: the number, the change against yesterday with an arrow and the words "vs yesterday", and a 14-day sparkline; whether a rise is good depends on the card. The sparkline is fluid (up to 120 px, redrawn at the width of its box) and the foot wraps, so five cards in a row at 1440 px with the sidebar open, or one card at 390 px, never spill past their border; the loading skeleton uses percentages for the same reason.
- **CoverageRing**: the posture visual, the verified share of the runs expected in the last 24 hours, with the percentage in the centre; green from 95 percent, amber from 80, red below; "No runs expected" when empty.
- **Skeleton**, **EmptyState** (first-run checklist, ribbon or mark), **ErrorState** (retry, request id, offline wording), **CommandSearch** (Ctrl K, combobox and listbox, sections and actions).
- **Charts** on visx: tested with many points, one point and none; a flat series sits mid-height; no fake history.

Every screen has a designed empty, loading, error and success state. A section whose phase is not built yet shows a placeholder page: its title, the phase that brings it, what it will hold and a quiet layout preview, never a blank page.

The component gallery (`/_gallery`, every component in every state for the Playwright axe and screenshot run) exists only in the test build (`VITE_GALLERY=1`): the route loads it on demand, its words and stylesheet live with it, and `scripts/check-product-bundle.mjs` fails the product build if any of it reaches `dist/`.

## 6. Shell and screens

- **Header**: the horizontal lockup (180 px, 144 px at phone width; the files carry 2x copies) on a header in the page colour so the logo tile disappears; command search; theme toggle; account menu with e-mail, role and sign out. Sign out ends the server session first: if the server cannot be reached the user stays signed in and a toast says so, so a shared workstation never shows a signed-out screen in front of a live session.
- **Sidebar** from 1024 px: Morning check, Clients, Jobs, Unmatched, Inboxes, Parsers, Notifications, System, Settings (admin only, by address as well as in the menu: a technician at `/settings` gets the 404 page with "This section is for admins."), with the current section marked by weight and an ink bar. From 640 to 1023 px it becomes an icon rail with labels under the icons.
- **Bottom bar** under 640 px: the four primary sections plus More, which opens a sheet with the others, the theme toggle and sign out. Every label stays on one line.
- **Sign-in** and **first run**: a split layout with the ribbon hero on an ink panel at 1024 px and up (filled rings reported, the hollow ring stayed silent: the difference is shape, not only colour); on the right the stacked lockup on the page colour (the brand file carries an opaque tile in that colour, so it never sits on a card), then a card with the centred title, the lead and the form, edition and version under it; one sentence per failure (wrong credentials, locked with the wait the server gave in Retry-After, rate limited, offline); the first-run page becomes the 404 state once an account exists. A visitor sent to sign-in from a deep link comes back to it afterwards: the router keeps only a same-origin path (never `//host` or a backslash), and the page goes there only when it is a known section or plugin route, otherwise to the morning check.
- **404**: the ribbon mark, the address in mono, a link back to the morning check or to sign in. An unknown address is a 404 for everyone, never a sign-in prompt.

Widths: 1440, 768 and 390 px are the reference widths; nothing overflows horizontally at any of them.

## 7. Deep links on the current backend

The FastAPI app answers every path that no route matched and that is not a built file, outside `/api/`, with HTTP 200 and `index.html` (`app/web.py`, phase C3-B), so a deep link such as `/login` or `/clients/ID` boots the app and the router renders the right screen (or its own 404 page). Unknown paths under `/api/` answer 404 as `application/problem+json`, never HTML. The `404.html` second entry of phase C2 is gone; the build has one entry, `index.html`.

## 8. Clients and jobs (phase C3-F)

The first working screens follow the same frame: a page header (icon, title, one line with the count, actions on the right), a DataTable with its filters in the toolbar, designed loading, empty and error states, and dialogs or a drawer for the work.

- **/clients**: name with aliases under it, job count, the worst state as a SeverityBadge (icon plus word), notes and creation date; search (sent to the server after 300 ms), a worst-state filter (applied to the loaded rows: the API lists by name) and the archived switch. A row or the name link opens the client.
- **/clients/:id**: crumbs back to the list, the name with its worst-state badge and an Archived chip, actions (Edit, Export jobs, Archive or Restore, Delete, New job), a summary card (jobs, worst state, counts by state, created, aliases, notes), then tabs: Jobs, plus whatever plugins add to `clientTabs` (empty in CE). Archive asks once; Delete asks for the typed name and sends it as `confirm_name`; the button refuses locally what the server would refuse (runs of spaces collapse, case stays).
- **/jobs**: job and client, kind, the schedule as kind plus a mono expression with the zone under it, the state badge with "until …" for a timed pause and an Archived chip, last success ("Not yet" until the evaluator of C7 fills it), and a row action menu (Edit, Pause or Resume, Copy ping URL, Archive or Restore). Filters by client, kind and state, search, the archived switch; Import CSV and Export CSV in the header.
- **Job drawer** (create and edit): a right-anchored panel, 640 px, 880 px from 1024 px so the schedule fields and the **live preview** sit side by side; full width on a phone. Sections Job, Schedule, Deadlines, Alerts, Ping URL. The schedule editor offers Daily (a list of native time inputs), Cron and Interval (a mono expression) and an IANA zone with the browser's list as suggestions. The preview asks `schedule/preview` 400 ms after the last change, keeps the last good answer on screen while the next loads, and shows an unusable schedule as the server's own sentence under the field it names and in the panel. The ping URL is a read-only mono field with a copy button; a null value (API tokens) is explained, never an empty field.
- **Pause** is a small dialog with an optional native datetime-local input (local time, must be in the future); **Archive** a confirm. Resume and Restore act at once; every outcome is a toast with a word and an icon.
- **CSV import** happens in two steps inside one dialog: Check the file (a dry run) shows the counts and the rows left out, by row number with the server's message; Import N rows then saves the rows that passed. An unusable file is an alert; a changed file has to be checked again.
- **Tables under 768 px** keep a minimum width and scroll sideways inside their wrap, so a name never breaks into one letter per line; under 360 px the toolbar stacks and every control takes a full line.

New controls in `components/ui`: Alert (icon plus coloured edge), Switch (a native checkbox over a drawn track), Tabs (the tablist pattern with arrow, Home and End), Drawer (Radix Dialog as a side panel), CopyField, FileField (a native file input drawn as a button), ActionMenu (Radix DropdownMenu), Textarea. Native date, time and datetime inputs keep the field look and follow the theme through `color-scheme`, so the picker is never light on light in dark. Their value is written by the browser in its own locale (an en-US browser shows 11:00 PM where the preview and the tables show 23:00); that is browser behaviour, not a defect, and the server always receives the ISO value.

## 9. Inboxes and messages (phase C4-F)

- **/inboxes**: label with what the sender needs under it in mono (the SMTP address, the webhook URL, the IMAP host and user), the kind as a chip with an icon and the word (SMTP, IMAP, Webhook, Upload), the sender rules (how many allowed senders, a DKIM chip), the last message time and the creation date; a kind filter; a row action menu (Edit, Copy address, Copy ingest URL, Rotate token, Upload .eml, Delete). A row opens the editor.
- **Inbox drawer** (create and edit): on create a kind picker of four cards (the kind never changes later), then the label, the mailbox fields for IMAP (host and port side by side, TLS, user name, password, folder, poll seconds) and the sender rules. On edit the Access section shows the SMTP address and ingest URL as copy fields, the webhook token state ("A token is set", never the value) with a Rotate button, and the IMAP password as a masked hint with an empty field that keeps the stored one. A new host, port, TLS setting or user name asks for the password again before anything is sent (a warning in the Mailbox section and a field error on Save); the API's own 422 lands on the same field and above the form.
- **Inbox ready** and **New token** dialogs: what the sender needs right after create or rotate; the webhook token appears here only, under a "Shown once" warning, and nowhere else afterwards.
- **/messages** (under Inboxes in the sidebar, with a crumb back): subject with the Message-ID under it and a Duplicate chip when another loaded message carries the same Message-ID (the same mail in two inboxes; the API keeps one row per inbox), sender, inbox as kind chip plus label, received, the parse state as icon plus word (Pending, Parsed, Unmatched, Error), the linked client as a link; filters by inbox and parse state; the Upload .eml button.
- **Message detail**: the subject as the title with the parse state beside it, the sender and time as the lead, a summary card, then the body and the headers as escaped text in JetBrains Mono inside focusable scrolling boxes (React escapes every string; no dangerouslySetInnerHTML, no iframe), the 256 KB cut as a note, and the results the parser read.
- **Upload .eml**: inbox select and a file field; a file over the API's 5 MiB cap is refused in the browser with its size; the server's 413 and 422 are one sentence under "The file was not stored"; a stored file opens the message, a duplicate says so and offers to open the earlier one.
- **Stale-heartbeat banner**: the signal red block above every signed-in screen while system/status (polled once a minute) says the worker is stale: the title, the minutes without a heartbeat and the last heartbeat time; nothing while the status loads or cannot be read. It is the one red block of the page, so the rule of section 10 still holds.

## 10. What later phases keep

- Red stays rare. If a page has more than the morning line, failed counts and destructive buttons in red, something is wrong.
- Numbers first, then the ribbon, then lists. The morning check (C8) opens with five stat cards and the coverage ring above the fold at 1440 px.
- Raw mail is escaped mono text in a scrolling box, never HTML.
- The product name appears in one constant (`strings.ts`, `PRODUCT_NAME`); a test fails when another source file spells it out.
