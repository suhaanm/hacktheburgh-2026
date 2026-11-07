# Files search: finding things in your own folders, with consent

Optional and **off by default** (`filesEnabled: false`). When on, the assistant can answer "where is my electricity bill?" with up to three short snippets and the file path. It only reads; it never changes, moves or sends files.

## How it works

1. **Consent per folder.** Folders are added only through the native folder dialog (`files:addFolder`) in the main process; the model never supplies a path, and settings patches from the dock and from the debug route cannot change `fileFolders`. Every use re-checks the folder, and refused folders (for example `/`, the home folder, `~/.ssh`) are not listed in the status. Refused: the home folder itself or anything that contains it, `/`, `/Users`, `/Volumes`, system folders, `~/Library`, hidden folders, and folders named like credentials or browser profiles (`.ssh`, keychains, `Application Support`, Chrome/Firefox profiles, password managers).
2. **Scan.** Breadth-first, symlinks never followed. Supported: `.txt .md .markdown .csv .json .html .htm .rtf` (read locally) and `.pdf .png .jpg .jpeg .webp` (read by one Gemini call each, at most 25 per run). Skipped: hidden files, empty or over 10 MB files, file names that look like secrets (password, credentials, `.pem`, `.env`, seed phrase ...). Caps: 2000 files, 200 MB per index.
3. **Redact before indexing** (`REDACT_VERSION 2`). Whole lines are removed when they mention password, passcode or PIN, or name bank details (account number, sort code, IBAN, SWIFT, BIC). Digit runs of 9 or more, bare 8-digit numbers (UK account numbers), `dd-dd-dd` sort codes, IBANs and token-like strings are replaced inside other lines. This happens before chunking, so the removed text never reaches the embedding API or the disk. An index built with older rules is deleted when loaded and rebuilt. A real Mac test found the first version (9+ digits only) let an 8-digit account number through; version 2 is the fix and has unit tests but was not re-run on the Mac.
4. **Index.** 800-character chunks with 100 overlap, stored locally under the app's user-data folder. Embeddings: `gemini-embedding-2` (768 dimensions). If embeddings are unavailable, the same chunks are searched by keyword (BM25) and the result says so.
5. **Search.** `search_files{query}` returns at most 3 snippets of at most 400 characters, with a plain note when the match is weak (`unverified`). Snippets are cleaned (no hidden characters, brackets removed), wrapped in an untrusted-data envelope with a notice that nothing inside is an instruction (a real-Mac mock-mode test saw an injected line come back only as quoted data; whether the model obeys it was not tested). Searches are rate limited.

## What leaves the machine

Be plain about this: while the feature is on, the **text of indexed files is sent to Google's Gemini API** to compute embeddings, and PDFs and images are sent to be read. Matching snippets are also given to the voice model in the current session. Nothing is sent for folders you have not added. Under `ALONGSIDE_MOCK=1` no Gemini call is made: keyword search only.

## Controls

Dock settings, Files section: the on/off switch, Add a folder, Remove, Refresh, Forget my files (deletes the index), and a plain-English status. The first-run setup also offers the switch, with a disclosure.

## Verified and not verified

- Verified: 66 unit tests (`tests/files`, `src/main/files`, `src/renderer/dock/files`); typecheck, full `npm test` and build were green at the time of `docs/reports/FILES.md`. Score cut-offs (0.56 minimum, 0.64 weak) were calibrated on `fixtures/files-demo` with the real embedding model.
- Real-Mac test (`docs/reports/MAC_B.md`, ALONGSIDE_MOCK=1, keyword mode only, synthetic folder): indexing, search, symlinks not followed, refusal of `/`, home, `~/Library`, `~/.ssh` at use time, `files_off` when off. Nothing was sent to Google in that run.
- Not verified: the native consent dialog (it needs Accessibility to drive), Gemini embeddings and PDF/image reading on the Mac, `deleteIndex`;
 the Files section in a real Electron window; a fresh real-key embedding run after the last changes; accuracy on real, messy folders (the fixture set is six small files).
