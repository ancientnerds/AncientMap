# History rewrite: the raw third-party response bodies leave the repository (2026-09-21)

**Why.** The gitleaks run on 2026-09-21 found 7 live third-party API keys, all `generic-api-key`,
all inside `output/remediation/phase3_pilot/evidence/`, all introduced by the single commit below.
`.gitleaksignore`'s own header forbids allowlisting a live credential, so the remedy is removal,
not exemption. Removing them from the working tree was not enough: the blobs stayed reachable from
that commit, so the first push would have published them and the sast gate would have stayed red.

**What was done.** `git filter-branch --index-filter` over the range `b2dc450^..main`, removing
`output/remediation/phase3_pilot/evidence/` from every commit in it. The tree at HEAD is
unaffected, and that was checked rather than assumed: `git diff --stat 6cf4802 <new HEAD>` is empty,
because the path had already been unversioned at `f96d4c3` and was absent from HEAD before the
rewrite. The files themselves are untouched on disk - they remain the fetch evidence, they are now
simply not versioned.

**Backup.** `/c/PythonProjects/ancientmap-pre-rewrite-20260921-0211.bundle` (2,113,204 bytes),
created from `origin/main..HEAD` before the rewrite. Nothing has been pushed; no remote ever saw
the old hashes, so no force-push and no coordination is needed.

**Scope.** 15 commits in the unpushed range, of which 15 were rewritten and
0 kept their hash (everything before `b2dc450`).

| old | new | subject |
|---|---|---|
| `b2dc450e9af7` | `98ce0c3c4052` | G0 + wave 4: persist the computed VLM verdicts, and land the two lane trees |
| `b66fa0e65ede` | `343ea8e4a1c6` | Re-prove the mechanical lane after reformatting it, and record the sweep's rea |
| `52c2792b9beb` | `75f015efa609` | Close the two-failure gate run: the names are unrecoverable, and the tail stil |
| `c97fbafe81fb` | `9c11f014cb69` | Measure the exit-0 trap: the bounded task log held 7 bytes, one line, "EXIT=0" |
| `2862c06e8486` | `cd15c0801ddd` | Adjudicate the t02 SQL-injection advisory as a spatial-index false positive, w |
| `36ea7a99beb8` | `f93697942f2a` | Wave 5 triage: three P0 deploy blockers verified, two DEPLOY findings refuted  |
| `ccd7e8de5882` | `6ced306ff3ea` | Land the Phase-3 brief amendment, with the two corrections the worker forced o |
| `78640a890b71` | `ec9f746afd28` | Re-prove merge_rewrites after a formatter pass, version the wave-6 launcher, r |
| `fe2ce930fc5a` | `1852245c56f4` | Measure the credential finding with the real scanner, and decline to allowlist |
| `f96d4c393915` | `835653dfd08f` | Stop versioning raw third-party response bodies: the class, not just the six f |
| `2dd0a48b32c3` | `ebce45dec368` | Record the live state and the remaining plan as a recovery anchor; version the |
| `1fb41d75be86` | `5f46f806df2b` | Close the t02 SQL-injection advisory as a named instrument mismatch, with my o |
| `c10f582319ac` | `000bd1eb3810` | Measure the vision model competence the G0 audit left unverified, and version  |
| `4a7e00041779` | `cabed984e859` | Land the post-review fix wave the two timed-out fixer lanes left behind, verif |
| `6cf4802e78c5` | `a9585f518fce` | Amend the Phase-3 pilot and worklist against the measuring lens |

**Blast radius to remember.** Any recorded hash older than this rewrite is now stale. The rewritten
hashes are the ones that matter from here on; the old ones resolve only through the backup bundle.
